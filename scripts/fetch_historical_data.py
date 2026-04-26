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
    python scripts/fetch_historical_data.py \\
        --base-url https://historical-data.boros.finance \\
        --markets BINANCE-ETHUSDT-29MAY2026 ... \\
        --kinds market-trades order-book-raw underlying-apr settlement market-data \\
        --since 2026-02-26 --until 2026-04-26 \\
        --concurrency 6 \\
        --out data/ndjson \\
        --manifest var/fetcher/manifest.json \\
        --config strategy/v0.5-default.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
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


# ── Fetch loop stub (Wave 1 fills this in) ─────────────────────────────────


def _run_fetch_loop(args: argparse.Namespace, run_id: str) -> int:
    """Wave 1 implements: iterate files.json, filter by markets/kinds/window, fetch + extract."""
    raise NotImplementedError("Wave 1 implements")


# ── CLI entry ─────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — argparse → RUN_MANIFEST preamble → fetch loop (or --no-fetch short-circuit)."""
    p = argparse.ArgumentParser(
        description="Boros historical-data fetcher — Phase 05.1 ship-gate bootstrap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url", required=True, help="Archive root, e.g. https://historical-data.boros.finance")
    p.add_argument("--markets", nargs="+", required=True, help="Market IDs to fetch")
    p.add_argument(
        "--kinds",
        nargs="+",
        default=ALL_KINDS,
        choices=ALL_KINDS,
    )
    p.add_argument("--since", required=True, help="Inclusive ISO-8601 date, e.g. 2026-02-26")
    p.add_argument("--until", required=True, help="Inclusive ISO-8601 date, e.g. 2026-04-26")
    p.add_argument("--concurrency", type=int, default=6, help="Parallel HTTP fetches (cap 8)")
    p.add_argument("--out", required=True, type=Path, help="NDJSON root (e.g. data/ndjson)")
    p.add_argument("--manifest", required=True, type=Path, help="Idempotency manifest (e.g. var/fetcher/manifest.json)")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("strategy/v0.5-default.yaml"),
        help="BotConfig YAML (default: strategy/v0.5-default.yaml)",
    )
    p.add_argument(
        "--no-fetch",
        action="store_true",
        help="Test-only: emit RUN_MANIFEST + exit 0 without HTTP",
    )
    args = p.parse_args(argv)

    if args.concurrency > 8:
        p.error("--concurrency must be <= 8 (CONTEXT.md cap)")

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

    return _run_fetch_loop(args, manifest.run_id)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
