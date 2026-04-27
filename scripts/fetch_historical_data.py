#!/usr/bin/env python3
"""Phase 05.1 — historical-data fetcher.

Operator-invoked one-shot. Downloads ZIP/NDJSON archives from
https://historical-data.boros.finance into data/ndjson/ for the Phase-1 ingester.

Idempotent: skips files whose (url, sha256, content_length) tuple already appears
in the per-file manifest at var/fetcher/manifest.json AND whose local sha256
still matches.

Emits RUN_MANIFEST as first log line + sidecar JSON + state.run_manifests row
(PROTO-01 / CLAUDE.md Engineering Protocol #3).

Usage:
    # Build symbol → archive-marketId mapping (run before --run):
    python scripts/fetch_historical_data.py \\
        --build-mapping \\
        --base-url https://historical-data.boros.finance \\
        --markets BINANCE-ETHUSDT-29MAY2026 ... \\
        --mapping-out var/fetcher/market_id_mapping.json \\
        --config strategy/v0.5-default.yaml

    # Bulk fetch:
    python scripts/fetch_historical_data.py \\
        --base-url https://historical-data.boros.finance \\
        --markets BINANCE-ETHUSDT-29MAY2026 ... \\
        --kinds market-trades order-book-raw order-book-combined underlying-apr settlement market-data \\
        --since 2026-02-26 --until 2026-04-26 \\
        --concurrency 6 \\
        --out data/ndjson \\
        --manifest var/fetcher/manifest.json \\
        --config strategy/v0.5-default.yaml

    # DNS workaround (local resolver broken — use --resolve HOST:IP):
    python scripts/fetch_historical_data.py \\
        --resolve historical-data.boros.finance:104.20.17.156 \\
        ...same args...
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import socket
import sys
import tempfile
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import zipfile

import httpx
import structlog

from boros_brain.config.loader import load_config
from boros_brain.logging.structlog_setup import configure_logging
from boros_brain.manifest.writer import build_run_manifest, write_manifest

# ── Constants ────────────────────────────────────────────────────────────────

MAX_DECOMPRESSED_BYTES = 10 * 1024**3  # 10 GB ZIP-bomb cap (RESEARCH.md §Security)

ALL_KINDS = [
    "market-trades",
    "order-book-raw",
    "order-book-combined",
    "underlying-apr",
    "settlement",
    "market-data",
]

# Archive kind → ndjson output subdir mapping
# Note: order-book has sub-structure (raw/ and combined_<tick>/)
ARCHIVE_KIND_TO_DIR = {
    "market-trades": "market-trades",
    "market-data": "market-data",
    "settlement": "settlement",
    "order-book": "order-book",  # covers both raw and combined
    "underlying-apr": "underlying-apr",
    "ohlcv": "ohlcv",
}


# ── DNS resolution workaround ─────────────────────────────────────────────────


def _install_resolve_override(host_ip_pairs: list[tuple[str, str]]) -> None:
    """Monkey-patch socket.getaddrinfo to map host → IP for broken local DNS.

    This is a last-resort workaround when the local DNS resolver is broken
    (e.g., TCP failure on port 53). The archive IPs are Cloudflare Anycast
    and stable across sessions.

    Logs a structured warning for each override installed.
    """
    if not host_ip_pairs:
        return

    mapping = {host: ip for host, ip in host_ip_pairs}
    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(
        host: str,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[Any]:
        if host in mapping:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (mapping[host], port))]
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = patched_getaddrinfo  # type: ignore[assignment]


# ── Idempotency manifest helpers (Pattern 6) ─────────────────────────────────


def _load_manifest(path: Path) -> dict[str, Any]:
    """Load the idempotency manifest JSON, or return empty structure if absent."""
    if not path.exists():
        return {"fetched": []}
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def _is_already_fetched(manifest: dict[str, Any], *, url: str, local_path: Path) -> bool:
    """Skip rule: file exists locally AND manifest has matching (url, sha256, length) AND on-disk sha matches."""
    if not local_path.exists():
        return False
    for entry in manifest["fetched"]:
        if entry["url"] != url:
            continue
        if entry["local_path"] != str(local_path):
            continue
        # Re-hash the on-disk file — if tampered or partially overwritten, refetch.
        if _sha256_file(local_path) != entry["sha256"]:
            return False
        if local_path.stat().st_size != entry["content_length_bytes"]:
            return False
        return True
    return False


def _record_fetched(
    manifest: dict[str, Any],
    *,
    url: str,
    local_path: Path,
    content_length: int,
    sha256: str,
    run_id: str,
) -> None:
    """Append a successfully-fetched file record to the in-memory manifest dict."""
    manifest["fetched"].append({
        "url": url,
        "local_path": str(local_path),
        "content_length_bytes": content_length,
        "sha256": sha256,
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
    })


def _save_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Atomically persist the manifest JSON (tmp + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    os.replace(tmp, path)


# ── File I/O helpers (Pattern 5) ─────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file using 1 MiB streaming chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write(local_path: Path, body: bytes) -> None:
    """Atomically write body to local_path (tmp + os.replace); creates parent dirs."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = local_path.with_suffix(local_path.suffix + ".tmp")
    tmp.write_bytes(body)
    os.replace(tmp, local_path)


# ── ZIP safety helper (Pattern 4) ─────────────────────────────────────────────


def _safe_extract_zip(zip_path: Path, *, out_root: Path) -> list[Path]:
    """Extract a ZIP archive with path-traversal guard and ZIP-bomb cap.

    Security invariants (T-FETCH-PATH-TRAVERSAL, T-FETCH-ZIP-BOMB):
    - Each entry is checked: (out_root / entry).resolve() must be relative to out_root.resolve().
      Raises ValueError('path traversal blocked: <entry>') on violation.
    - Each entry's uncompressed size is checked against MAX_DECOMPRESSED_BYTES.
      Raises ValueError('zip bomb: entry <entry> exceeds max decompressed bytes cap <N>') on overflow.

    Returns list of extracted Path objects.
    """
    out_root_resolved = out_root.resolve()
    extracted_paths: list[Path] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for entry in zf.namelist():
            extracted = (out_root_resolved / entry).resolve()
            if not extracted.is_relative_to(out_root_resolved):
                raise ValueError(f"path traversal blocked: {entry}")
            info = zf.getinfo(entry)
            if info.file_size > MAX_DECOMPRESSED_BYTES:
                raise ValueError(
                    f"zip bomb: entry {entry} exceeds max decompressed bytes cap {MAX_DECOMPRESSED_BYTES}"
                )
            out_root.mkdir(parents=True, exist_ok=True)
            zf.extract(entry, path=out_root)
            extracted_paths.append(out_root / entry)

    return extracted_paths


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _fetch_with_retry(
    client: httpx.Client,
    url: str,
    *,
    backoff: list[int] | None = None,
    log: Any = None,
    **log_kwargs: Any,
) -> httpx.Response:
    """GET url with 3-attempt linear backoff on connection errors / 5xx / 429.

    Raises RuntimeError on 401/403 (auth surprise — halt, do not retry).
    Returns the response on 200.
    """
    if backoff is None:
        backoff = [1, 3, 9]

    attempts = len(backoff) + 1
    for attempt in range(1, attempts + 1):
        try:
            resp = client.get(url)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            if attempt <= len(backoff):
                wait = backoff[attempt - 1]
                if log:
                    log.warning(
                        "historical_fetcher.fetch_retry",
                        url=url,
                        attempt=attempt,
                        wait_s=wait,
                        error=str(exc),
                        **log_kwargs,
                    )
                time.sleep(wait)
                continue
            raise

        if resp.status_code in (401, 403):
            raise RuntimeError(
                f"URL appears to require auth — wave-0 probe was wrong; halting. "
                f"status={resp.status_code} url={url}"
            )

        if resp.status_code == 429:
            wait = backoff[attempt - 1] if attempt <= len(backoff) else 30
            if log:
                log.warning(
                    "historical_fetcher.fetch_rate_limited",
                    url=url,
                    attempt=attempt,
                    wait_s=wait,
                    **log_kwargs,
                )
            time.sleep(wait)
            continue

        if resp.status_code >= 500:
            if attempt <= len(backoff):
                wait = backoff[attempt - 1]
                if log:
                    log.warning(
                        "historical_fetcher.fetch_http_error",
                        url=url,
                        status=resp.status_code,
                        attempt=attempt,
                        wait_s=wait,
                        **log_kwargs,
                    )
                time.sleep(wait)
                continue
            raise RuntimeError(f"Server error after {attempt} attempts: {resp.status_code} {url}")

        if resp.status_code == 404:
            raise RuntimeError(f"404 Not Found: {url}")

        return resp

    raise RuntimeError(f"Failed after {attempts} attempts: {url}")


# ── Market-ID mapping (Task 1.5) ─────────────────────────────────────────────


def build_market_id_mapping(
    *,
    base_url: str,
    local_market_ids: list[str],
    out_path: Path,
    run_id: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Resolve local human market_ids to archive {N}-... directory names.

    The Boros historical-data archive uses numeric on-chain ID prefixes that
    are absent from local clo_history.market_id. Same human name can map to
    multiple deployments — e.g. ``108-HYPERLIQUID-BTC-29MAY2026`` and
    ``109-HYPERLIQUID-BTC-29MAY2026`` are distinct on-chain markets.

    Strategy (no REST call needed — purely string-matching against the
    archive's master manifest):

    1. GET ``{base_url}/files.json`` once.
    2. Extract distinct directory roots under ``market-trades/``.
    3. For each root, parse ``"{N}-{rest}"`` where ``{N}`` is a leading
       integer. Group ``rest`` → list of ``{N}`` variants.
    4. For each local human market_id, look up ``rest == market_id``.
       Recommend the HIGHEST ``{N}`` (most recent deployment) but
       persist all variants for audit.
    5. Atomic write to ``out_path`` with shape:
       {
         "mapping": {
           "HYPERLIQUID-BTC-29MAY2026": {
             "recommended": "109-HYPERLIQUID-BTC-29MAY2026",
             "all_variants": ["108-...", "109-..."]
           },
           ...
         },
         "unresolved": [...],
         "manifest_etag": "<from response>",
         "resolved_at_utc": "<iso>",
         "run_id": run_id
       }

    Idempotent: if ``out_path`` exists and the manifest ETag is unchanged
    since last run, return cached mapping (skip re-fetch).
    """
    log = structlog.get_logger("historical_fetcher.mapping")
    files_url = f"{base_url}/files.json"

    own_client = client is None
    if client is None:
        client = httpx.Client(timeout=httpx.Timeout(30.0))

    try:
        # Check cache: if out_path exists and ETag matches, return cached
        if out_path.exists():
            cached = json.loads(out_path.read_text())
            cached_etag = cached.get("manifest_etag")
            if cached_etag:
                head_resp = client.head(files_url)
                current_etag = head_resp.headers.get("etag", "").strip('"')
                if current_etag and current_etag == cached_etag.strip('"'):
                    log.info(
                        "historical_fetcher.mapping_cache_hit",
                        etag=current_etag,
                        run_id=run_id,
                    )
                    return cached  # type: ignore[return-value]

        # Fetch the master manifest
        log.info("historical_fetcher.mapping_fetch_start", url=files_url, run_id=run_id)
        resp = _fetch_with_retry(client, files_url, log=log, run_id=run_id)
        etag = resp.headers.get("etag", "").strip('"')
        files_list: list[dict[str, Any]] = resp.json()

        log.info(
            "historical_fetcher.mapping_manifest_fetched",
            entries=len(files_list),
            etag=etag,
            run_id=run_id,
        )

        # Extract distinct market dirs from market-trades/ prefix
        # Path format: market-trades/{N}-{EXCHANGE}-{ASSET}-{MATURITY}/{YYYY-MM}.ndjson.zip
        archive_variants: dict[str, list[str]] = {}  # rest → list of full archive IDs
        for entry in files_list:
            path = entry["path"]
            if not path.startswith("market-trades/"):
                continue
            parts = path.split("/")
            if len(parts) < 2:
                continue
            archive_market_id = parts[1]  # e.g. "109-HYPERLIQUID-BTC-29MAY2026"
            # Parse {N}-{rest}: N is the leading integer prefix
            dash_idx = archive_market_id.find("-")
            if dash_idx < 0:
                continue
            prefix = archive_market_id[:dash_idx]
            if not prefix.isdigit():
                continue
            rest = archive_market_id[dash_idx + 1:]  # e.g. "HYPERLIQUID-BTC-29MAY2026"
            if rest not in archive_variants:
                archive_variants[rest] = []
            if archive_market_id not in archive_variants[rest]:
                archive_variants[rest].append(archive_market_id)

        log.info(
            "historical_fetcher.mapping_archive_parsed",
            distinct_markets=len(archive_variants),
            run_id=run_id,
        )

        # Build mapping: for each local market_id, find archive variants
        mapping: dict[str, Any] = {}
        unresolved: list[str] = []

        for local_id in local_market_ids:
            variants = archive_variants.get(local_id)
            if not variants:
                unresolved.append(local_id)
                log.warning(
                    "historical_fetcher.mapping_unresolved",
                    market_id=local_id,
                    run_id=run_id,
                )
                continue

            # Sort by numeric prefix (descending) — highest N = most recent deployment
            def _numeric_prefix(v: str) -> int:
                return int(v.split("-")[0])

            sorted_variants = sorted(variants, key=_numeric_prefix, reverse=True)
            recommended = sorted_variants[0]

            mapping[local_id] = {
                "recommended": recommended,
                "all_variants": sorted_variants,
            }

            if len(sorted_variants) > 1:
                log.info(
                    "historical_fetcher.mapping_multiple_deployments",
                    market_id=local_id,
                    recommended=recommended,
                    all_variants=sorted_variants,
                    run_id=run_id,
                )

        result: dict[str, Any] = {
            "mapping": mapping,
            "unresolved": unresolved,
            "manifest_etag": etag,
            "resolved_at_utc": datetime.now(UTC).isoformat(),
            "run_id": run_id,
        }

        # Atomic write
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(json.dumps(result, indent=2))
        os.replace(tmp, out_path)

        log.info(
            "historical_fetcher.mapping_complete",
            resolved=len(mapping),
            unresolved=len(unresolved),
            out_path=str(out_path),
            run_id=run_id,
        )
        return result

    finally:
        if own_client:
            client.close()


# ── Fetch loop (Task 2) ───────────────────────────────────────────────────────


def _months_in_window(since_str: str, until_str: str) -> list[str]:
    """Return list of 'YYYY-MM' strings for all months between since and until (inclusive)."""
    since_dt = datetime.strptime(since_str, "%Y-%m-%d").replace(tzinfo=UTC)
    until_dt = datetime.strptime(until_str, "%Y-%m-%d").replace(tzinfo=UTC)
    months = []
    # Walk month-by-month from since to until
    y, m = since_dt.year, since_dt.month
    while True:
        months.append(f"{y:04d}-{m:02d}")
        if y == until_dt.year and m == until_dt.month:
            break
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _fetch_one_file(
    *,
    client: httpx.Client,
    url: str,
    local_path: Path,
    out_root: Path,
    manifest: dict[str, Any],
    run_id: str,
    log: Any,
    log_kwargs: dict[str, Any],
) -> bool:
    """Fetch one archive file, extract if ZIP, record in manifest. Returns True if fetched."""
    if _is_already_fetched(manifest, url=url, local_path=local_path):
        log.info(
            "historical_fetcher.fetch_skip_existing",
            url=url,
            local_path=str(local_path),
            **log_kwargs,
        )
        return False

    log.info("historical_fetcher.fetch_start", url=url, **log_kwargs)

    try:
        resp = _fetch_with_retry(client, url, log=log, **log_kwargs)
    except RuntimeError as exc:
        msg = str(exc)
        if "404" in msg:
            log.info("historical_fetcher.fetch_not_found", url=url, **log_kwargs)
            return False
        raise

    body = resp.content
    sha = hashlib.sha256(body).hexdigest()
    content_type = resp.headers.get("content-type", "")
    fname = url.split("/")[-1].split("?")[0]

    if fname.endswith(".zip") or "application/zip" in content_type or "application/octet-stream" in content_type:
        # Write ZIP to a temp location, extract into local_path's parent directory.
        # Archive ZIPs contain a single flat file (e.g. "2026-04.ndjson") without
        # subdirectory structure — use local_path.parent as the extraction root so
        # the NDJSON lands at the correct path.
        extract_root = local_path.parent
        extract_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f:
            tmp_zip = Path(tmp_f.name)
        try:
            tmp_zip.write_bytes(body)
            try:
                extracted = _safe_extract_zip(tmp_zip, out_root=extract_root)
            except ValueError as exc2:
                log.error(
                    "historical_fetcher.fetch_zip_unsafe",
                    url=url,
                    error=str(exc2),
                    **log_kwargs,
                )
                return False  # Skip — don't record_fetched so re-run retries

            # Record the extracted NDJSON file(s) against this URL
            for ex_path in extracted:
                if ex_path.is_file():
                    ex_sha = _sha256_file(ex_path)
                    _record_fetched(
                        manifest,
                        url=url,
                        local_path=ex_path,
                        content_length=ex_path.stat().st_size,
                        sha256=ex_sha,
                        run_id=run_id,
                    )
                    log.info(
                        "historical_fetcher.fetch_complete",
                        url=url,
                        local_path=str(ex_path),
                        bytes=ex_path.stat().st_size,
                        sha256=ex_sha,
                        **log_kwargs,
                    )
        finally:
            tmp_zip.unlink(missing_ok=True)

    elif fname.endswith(".ndjson.gz") or fname.endswith(".gz"):
        decompressed = gzip.decompress(body)
        _atomic_write(local_path, decompressed)
        ex_sha = hashlib.sha256(decompressed).hexdigest()
        _record_fetched(
            manifest,
            url=url,
            local_path=local_path,
            content_length=len(decompressed),
            sha256=ex_sha,
            run_id=run_id,
        )
        log.info(
            "historical_fetcher.fetch_complete",
            url=url,
            local_path=str(local_path),
            bytes=len(decompressed),
            sha256=ex_sha,
            **log_kwargs,
        )

    else:
        # Raw NDJSON
        _atomic_write(local_path, body)
        _record_fetched(
            manifest,
            url=url,
            local_path=local_path,
            content_length=len(body),
            sha256=sha,
            run_id=run_id,
        )
        log.info(
            "historical_fetcher.fetch_complete",
            url=url,
            local_path=str(local_path),
            bytes=len(body),
            sha256=sha,
            **log_kwargs,
        )

    return True


def _run_fetch_loop(args: argparse.Namespace, run_id: str) -> int:
    """Implement the bulk download loop.

    1. Load idempotency manifest.
    2. Load market_id_mapping.json (Task 1.5 output).
    3. GET {base_url}/files.json (master archive manifest).
    4. Build desired path set from (kind, archive_market_id, period) cross-product.
    5. Submit fetch jobs to ThreadPoolExecutor(max_workers=args.concurrency).
    6. Atomic write updated manifest at end.
    """
    log = structlog.get_logger("historical_fetcher.loop")

    # Load manifest
    manifest = _load_manifest(args.manifest)

    # Load market_id_mapping — always look next to the manifest file (args.manifest is an
    # absolute path when provided via CLI, so this is CWD-independent)
    mapping_path = args.manifest.parent / "market_id_mapping.json"
    if not mapping_path.exists():
        log.error(
            "historical_fetcher.loop_mapping_missing",
            mapping_path=str(mapping_path),
            run_id=run_id,
        )
        return 1

    mapping_data = json.loads(mapping_path.read_text())
    market_mapping: dict[str, Any] = mapping_data.get("mapping", {})
    unresolved_markets: list[str] = mapping_data.get("unresolved", [])

    if unresolved_markets:
        log.warning(
            "historical_fetcher.loop_unresolved_markets",
            unresolved=unresolved_markets,
            run_id=run_id,
        )

    # Determine months window
    months = _months_in_window(args.since, args.until)
    log.info(
        "historical_fetcher.loop_window",
        since=args.since,
        until=args.until,
        months=months,
        run_id=run_id,
    )

    # Fetch master files.json manifest (cache-aware)
    # Cache lives next to the manifest file (args.manifest.parent is always absolute or
    # caller-controlled, so this is safe regardless of CWD)
    files_json_cache = args.manifest.parent / "files.json.cache"
    client = httpx.Client(timeout=httpx.Timeout(30.0))

    try:
        files_url = f"{args.base_url}/files.json"
        cached_etag = None
        if files_json_cache.exists():
            try:
                cached_data = json.loads(files_json_cache.read_text())
                cached_etag = cached_data.get("_etag")
                files_list = cached_data.get("files", [])
            except Exception:
                files_list = []
        else:
            files_list = []

        # Re-fetch if no cache or ETag check
        do_fetch = not files_list
        if not do_fetch and cached_etag:
            head_resp = client.head(files_url)
            current_etag = head_resp.headers.get("etag", "").strip('"')
            if current_etag and current_etag != cached_etag.strip('"'):
                do_fetch = True
                log.info("historical_fetcher.loop_manifest_stale", run_id=run_id)

        if do_fetch:
            log.info("historical_fetcher.loop_manifest_fetch", url=files_url, run_id=run_id)
            resp = _fetch_with_retry(client, files_url, log=log, run_id=run_id)
            files_list = resp.json()
            etag = resp.headers.get("etag", "").strip('"')
            # Cache with ETag
            files_json_cache.parent.mkdir(parents=True, exist_ok=True)
            cache_tmp = files_json_cache.with_suffix(".cache.tmp")
            cache_tmp.write_text(json.dumps({"_etag": etag, "files": files_list}, indent=2))
            os.replace(cache_tmp, files_json_cache)
            log.info(
                "historical_fetcher.loop_manifest_cached",
                entries=len(files_list),
                etag=etag,
                run_id=run_id,
            )

        # Build an index: path → entry for efficient lookup
        archive_index: dict[str, dict[str, Any]] = {e["path"]: e for e in files_list}

        # Resolve order-book tick sizes: default raw + combined_0.01
        ob_tick_sizes = getattr(args, "order_book_tick_sizes", None) or ["0.01"]

        # Normalize requested kinds to archive directory names
        # CLI kinds: market-trades, order-book-raw, order-book-combined, underlying-apr, settlement, market-data
        # Archive dirs: market-trades, order-book, underlying-apr, settlement, market-data
        requested_kinds = set(args.kinds)

        # Build fetch job list: (url, local_path, log_kwargs)
        fetch_jobs: list[tuple[str, Path, dict[str, Any]]] = []

        def _add_job(path_in_archive: str, local_path: Path, log_kw: dict[str, Any]) -> None:
            url = f"{args.base_url}/{urllib.parse.quote(path_in_archive, safe='/')}"
            fetch_jobs.append((url, local_path, log_kw))

        for human_market_id in args.markets:
            if human_market_id in unresolved_markets:
                log.warning(
                    "historical_fetcher.loop_skip_unresolved_market",
                    market_id=human_market_id,
                    run_id=run_id,
                )
                continue

            if human_market_id not in market_mapping:
                log.warning(
                    "historical_fetcher.loop_skip_unmapped_market",
                    market_id=human_market_id,
                    run_id=run_id,
                )
                continue

            archive_market_id = market_mapping[human_market_id]["recommended"]

            # market-trades
            if "market-trades" in requested_kinds:
                for month in months:
                    p = f"market-trades/{archive_market_id}/{month}.ndjson.zip"
                    if p in archive_index:
                        local = args.out / "market-trades" / archive_market_id / f"{month}.ndjson"
                        _add_job(
                            p,
                            local,
                            {
                                "market_id": human_market_id,
                                "archive_market_id": archive_market_id,
                                "kind": "market-trades",
                                "period": month,
                            },
                        )

            # market-data
            if "market-data" in requested_kinds:
                for month in months:
                    p = f"market-data/{archive_market_id}/{month}.ndjson.zip"
                    if p in archive_index:
                        local = args.out / "market-data" / archive_market_id / f"{month}.ndjson"
                        _add_job(
                            p,
                            local,
                            {
                                "market_id": human_market_id,
                                "archive_market_id": archive_market_id,
                                "kind": "market-data",
                                "period": month,
                            },
                        )

            # settlement
            if "settlement" in requested_kinds:
                for month in months:
                    p = f"settlement/{archive_market_id}/{month}.ndjson.zip"
                    if p in archive_index:
                        local = args.out / "settlement" / archive_market_id / f"{month}.ndjson"
                        _add_job(
                            p,
                            local,
                            {
                                "market_id": human_market_id,
                                "archive_market_id": archive_market_id,
                                "kind": "settlement",
                                "period": month,
                            },
                        )

            # order-book-raw
            if "order-book-raw" in requested_kinds:
                for month in months:
                    p = f"order-book/{archive_market_id}/raw/{month}.ndjson.zip"
                    if p in archive_index:
                        local = args.out / "order-book" / archive_market_id / "raw" / f"{month}.ndjson"
                        _add_job(
                            p,
                            local,
                            {
                                "market_id": human_market_id,
                                "archive_market_id": archive_market_id,
                                "kind": "order-book-raw",
                                "period": month,
                            },
                        )

            # order-book-combined
            if "order-book-combined" in requested_kinds:
                for tick in ob_tick_sizes:
                    for month in months:
                        p = f"order-book/{archive_market_id}/combined_{tick}/{month}.ndjson.zip"
                        if p in archive_index:
                            local = args.out / "order-book" / archive_market_id / f"combined_{tick}" / f"{month}.ndjson"
                            _add_job(
                                p,
                                local,
                                {
                                    "market_id": human_market_id,
                                    "archive_market_id": archive_market_id,
                                    "kind": f"order-book-combined_{tick}",
                                    "period": month,
                                    "tick_size": tick,
                                },
                            )

        # underlying-apr — FLAT (no per-month split, one file per Exchange-Asset pair)
        # Archive format: "underlying-apr/{Exchange}-{Asset}.ndjson.zip"
        # where Exchange is title-cased (Binance, Hyperliquid, OKX, Bybit, Lighter)
        # and Asset is a short symbol (BTC, ETH, XAG, XAU, etc.) — NOT the full USDT symbol.
        # We enumerate ALL underlying-apr files from the archive index to avoid derivation errors.
        if "underlying-apr" in requested_kinds:
            # Build set of archive underlying-apr keys from the files.json index
            all_apr_keys = {
                p.replace("underlying-apr/", "").replace(".ndjson.zip", ""): p
                for p in archive_index
                if p.startswith("underlying-apr/")
            }

            # For each requested market, determine which underlying-apr key to fetch.
            # Strategy: for each archive market ID, look for a matching underlying-apr entry.
            # Archive market: "{N}-{EXCHANGE}-{ASSET}-{MATURITY}"
            # Underlying-apr key: "{TitleCaseExchange}-{ShortAsset}"
            # Matching heuristic:
            #   - exchange part: BINANCE → Binance, HYPERLIQUID → Hyperliquid, etc.
            #   - asset part: strip trailing USDT/USDC/USD, then try title-case match
            needed_apr_keys: set[str] = set()
            for human_market_id in args.markets:
                if human_market_id not in market_mapping:
                    continue
                archive_id = market_mapping[human_market_id]["recommended"]
                # Parse: {N}-{EXCHANGE}-{ASSET}-{MATURITY}
                # Remove leading N-
                rest_parts = archive_id.split("-")
                if len(rest_parts) < 4 or not rest_parts[0].isdigit():
                    continue
                exchange_upper = rest_parts[1]  # e.g. BINANCE, HYPERLIQUID, OKX
                asset_upper = rest_parts[2]      # e.g. ETHUSDT, BTC, xyzGOLD

                # Normalize exchange to title-case as used in archive
                exchange_title = exchange_upper.capitalize()  # BINANCE → Binance, OKX → Okx
                # Special case: OKX stays OKX, Hyperliquid has specific casing
                if exchange_upper == "OKX":
                    exchange_title = "OKX"
                elif exchange_upper == "HYPERLIQUID":
                    exchange_title = "Hyperliquid"
                elif exchange_upper == "BYBIT":
                    exchange_title = "Bybit"
                elif exchange_upper == "LIGHTER":
                    exchange_title = "Lighter"

                # Normalize asset: strip USDT/USDC/USD suffix, keep core
                asset_core = asset_upper
                for suffix in ("USDT", "USDC", "USD"):
                    if asset_core.endswith(suffix) and len(asset_core) > len(suffix):
                        asset_core = asset_core[: -len(suffix)]
                        break

                # Handle xyz* synthetic assets — strip the xyz prefix to get the core symbol.
                # The archive uses the underlying key name without the xyz prefix:
                #   xyzGOLD → XAU (Gold = XAU in commodity notation)
                #   xyzSILVER → XAG (Silver = XAG)
                #   xyzXYZ100 → XYZ100
                #   xyzSP500 → no underlying-apr exists (synthetic index, skip)
                # Build a small normalization table for known xyz aliases.
                XYZ_ALIAS: dict[str, str] = {
                    "xyzGOLD": "XAU",
                    "xyzSILVER": "XAG",
                    "xyzBRENTOIL": "BRENTOIL",
                    "xyzCL": "CLOIL",
                    "xyzXYZ100": "XYZ100",
                    "xyzSP500": None,  # no underlying-apr in archive
                }
                if asset_core in XYZ_ALIAS:
                    resolved = XYZ_ALIAS[asset_core]
                    if resolved is None:
                        # Known to have no underlying-apr — skip silently
                        continue
                    asset_core = resolved

                candidate_key = f"{exchange_title}-{asset_core}"
                if candidate_key in all_apr_keys:
                    needed_apr_keys.add(candidate_key)
                else:
                    log.warning(
                        "historical_fetcher.loop_underlying_apr_missing",
                        market_id=human_market_id,
                        candidate_key=candidate_key,
                        available_keys=sorted(all_apr_keys.keys()),
                        run_id=run_id,
                    )

            for apr_key in sorted(needed_apr_keys):
                p = all_apr_keys[apr_key]
                local = args.out / "underlying-apr" / f"{apr_key}.ndjson"
                _add_job(
                    p,
                    local,
                    {
                        "exchange_asset": apr_key,
                        "kind": "underlying-apr",
                    },
                )

        log.info(
            "historical_fetcher.loop_jobs_planned",
            total_jobs=len(fetch_jobs),
            run_id=run_id,
        )

        if not fetch_jobs:
            log.warning(
                "historical_fetcher.loop_no_jobs",
                markets=args.markets,
                kinds=args.kinds,
                months=months,
                run_id=run_id,
            )
            _save_manifest(manifest, args.manifest)
            return 0

        # Execute fetch jobs with ThreadPoolExecutor
        errors: list[str] = []
        completed = 0
        skipped = 0

        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            future_to_job = {
                executor.submit(
                    _fetch_one_file,
                    client=client,
                    url=url,
                    local_path=local_path,
                    out_root=args.out,
                    manifest=manifest,
                    run_id=run_id,
                    log=log,
                    log_kwargs=log_kwargs,
                ): (url, local_path)
                for url, local_path, log_kwargs in fetch_jobs
            }

            for future in as_completed(future_to_job):
                url, local_path = future_to_job[future]
                try:
                    fetched = future.result()
                    if fetched:
                        completed += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    errors.append(f"{url}: {exc}")
                    log.error(
                        "historical_fetcher.fetch_error",
                        url=url,
                        error=str(exc),
                        run_id=run_id,
                    )

        # Atomic manifest write at end of run
        _save_manifest(manifest, args.manifest)

        log.info(
            "historical_fetcher.loop_done",
            total_jobs=len(fetch_jobs),
            fetched=completed,
            skipped=skipped,
            errors=len(errors),
            run_id=run_id,
        )

        if errors:
            for err in errors:
                log.error("historical_fetcher.loop_error", error=err, run_id=run_id)
            return 1

        return 0

    finally:
        client.close()


# ── CLI entry ─────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — argparse → RUN_MANIFEST preamble → fetch loop (or --no-fetch short-circuit)."""
    p = argparse.ArgumentParser(
        description="Boros historical-data fetcher — Phase 05.1 ship-gate bootstrap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url", required=True, help="Archive root, e.g. https://historical-data.boros.finance")

    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--build-mapping",
        action="store_true",
        help="Build market_id_mapping.json (run before --run)",
    )
    mode_group.add_argument(
        "--no-fetch",
        action="store_true",
        help="Test-only: emit RUN_MANIFEST + exit 0 without HTTP",
    )

    p.add_argument("--markets", nargs="+", required=True, help="Market IDs to fetch (local human IDs)")
    p.add_argument(
        "--kinds",
        nargs="+",
        default=ALL_KINDS,
        choices=ALL_KINDS,
    )
    p.add_argument("--since", help="Inclusive ISO-8601 date, e.g. 2026-02-26 (required for fetch run)")
    p.add_argument("--until", help="Inclusive ISO-8601 date, e.g. 2026-04-26 (required for fetch run)")
    p.add_argument("--concurrency", type=int, default=6, help="Parallel HTTP fetches (cap 8)")
    p.add_argument("--out", type=Path, help="NDJSON root (e.g. data/ndjson)")
    p.add_argument(
        "--manifest",
        type=Path,
        help="Idempotency manifest (e.g. var/fetcher/manifest.json)",
    )
    p.add_argument(
        "--mapping-out",
        dest="mapping_out",
        type=Path,
        default=Path("var/fetcher/market_id_mapping.json"),
        help="Where to write market_id_mapping.json (for --build-mapping mode)",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=Path("strategy/v0.5-default.yaml"),
        help="BotConfig YAML (default: strategy/v0.5-default.yaml)",
    )
    p.add_argument(
        "--resolve",
        nargs="+",
        default=[],
        metavar="HOST:IP",
        help="Override DNS for HOST with IP (e.g. historical-data.boros.finance:104.20.17.156). "
             "Workaround for broken local DNS resolvers.",
    )
    p.add_argument(
        "--order-book-tick-sizes",
        dest="order_book_tick_sizes",
        nargs="+",
        default=["0.01"],
        metavar="TICK",
        help="Tick sizes to fetch for order-book-combined (default: 0.01)",
    )
    args = p.parse_args(argv)

    if args.concurrency > 8:
        p.error("--concurrency must be <= 8 (CONTEXT.md cap)")

    # ── DNS resolve override (workaround for broken local DNS) ────────────────
    if args.resolve:
        pairs: list[tuple[str, str]] = []
        for item in args.resolve:
            if ":" in item:
                host, ip = item.rsplit(":", 1)
                pairs.append((host, ip))
        _install_resolve_override(pairs)

    # ── RUN_MANIFEST — must be emitted before first log line (PROTO-01) ──────
    config = load_config(args.config)
    manifest = build_run_manifest(config)
    logs_dir = Path(config.infra.logs_dir)
    sqlite_path = Path(config.infra.sqlite_path)
    try:
        write_manifest(manifest, logs_dir=logs_dir, sqlite_path=sqlite_path)
    except Exception:
        # If SQLite isn't initialised yet (e.g. bare scratch run), write sidecar only
        logs_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        from datetime import UTC as _UTC, datetime as _datetime

        date_dir = logs_dir / _datetime.now(_UTC).strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        sidecar = date_dir / f"{manifest.run_id}.manifest.json"
        sidecar.write_text(_json.dumps(manifest.model_dump(mode="json"), indent=2))

    configure_logging(run_id=manifest.run_id, tier="historical_fetcher", logs_dir=logs_dir)
    log = structlog.get_logger("historical_fetcher.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump(mode="json"))

    if args.no_fetch:
        log.info("historical_fetcher.cli.no_fetch_short_circuit")
        return 0

    if args.build_mapping:
        result = build_market_id_mapping(
            base_url=args.base_url,
            local_market_ids=args.markets,
            out_path=args.mapping_out,
            run_id=manifest.run_id,
        )
        resolved_count = len(result.get("mapping", {}))
        unresolved_count = len(result.get("unresolved", []))
        log.info(
            "historical_fetcher.cli.mapping_done",
            resolved=resolved_count,
            unresolved=unresolved_count,
            out_path=str(args.mapping_out),
        )
        # Pre-flight assertion: at least 15 of 25 must resolve
        if resolved_count < 15:
            log.error(
                "historical_fetcher.cli.mapping_sanity_fail",
                resolved=resolved_count,
                threshold=15,
                msg="Less than 15 markets resolved — investigate archive or input market list",
            )
            return 1
        return 0

    # Validate required args for fetch run
    if not args.since:
        p.error("--since is required for fetch run")
    if not args.until:
        p.error("--until is required for fetch run")
    if not args.out:
        p.error("--out is required for fetch run")
    if not args.manifest:
        p.error("--manifest is required for fetch run")

    return _run_fetch_loop(args, manifest.run_id)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
