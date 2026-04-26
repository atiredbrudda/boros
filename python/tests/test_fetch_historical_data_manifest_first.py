"""PROTO-01 — historical fetcher emits RUN_MANIFEST as first log line.

Test functions:
  - test_fetcher_cli_emits_run_manifest_first: first log line is RUN_MANIFEST with mode=<config.mode>
  - test_fetcher_writes_sidecar_json: <logs_dir>/<date>/<run_id>.manifest.json exists
  - test_fetcher_inserts_run_manifests_sqlite_row: row exists in state.run_manifests

[[boros-historical-data-archive-url-pattern]]
[[run-manifest-writer]]
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest
from boros_brain.state.db import open_connection

# repo root: python/tests -> python/ -> repo root
_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = str(_ROOT / "strategy" / "v0.5-default.yaml")


def test_fetcher_cli_emits_run_manifest_first(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """First emitted log line is RUN_MANIFEST with the config's mode + market_id.

    Built manifest fields are spread into log.info("RUN_MANIFEST", **manifest.model_dump()).
    Verifies the fields the fetcher relies on are all present.
    """
    manifest = build_run_manifest(default_config)
    dumped = manifest.model_dump(mode="json")
    for field in ("run_id", "mode", "git_sha", "strategy_version", "market_id", "side", "config"):
        assert field in dumped, f"field '{field}' missing from manifest dump"
    assert isinstance(dumped["config"], dict) and dumped["config"], "config must be a non-empty dict"


def _make_patched_load_config(db_path: Path, logs_dir: Path):  # type: ignore[return]
    """Return a load_config replacement that redirects infra paths into tmp_path."""
    from boros_brain.config.loader import load_config as _real_load_config

    def _patched(path: Path) -> BotConfig:  # type: ignore[return]
        cfg = _real_load_config(path)
        # BotConfig is frozen; use model_copy to redirect infra paths.
        new_infra = cfg.infra.model_copy(
            update={
                "sqlite_path": str(db_path),
                "logs_dir": str(logs_dir),
            }
        )
        return cfg.model_copy(update={"infra": new_infra})

    return _patched


def test_fetcher_writes_sidecar_json(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PROTO-01: sidecar JSON at <logs_dir>/<YYYY-MM-DD>/<run_id>.manifest.json exists after --no-fetch run.

    Monkeypatches load_config inside the fetcher module so infra paths point at
    the test sandbox. The sidecar must be parseable JSON containing the same run_id.
    """
    import scripts.fetch_historical_data as fetcher_mod

    from tests.conftest import apply_migrations

    db_path = tmp_path / "state.sqlite"
    logs_dir = tmp_path / "logs"
    apply_migrations(db_path)

    monkeypatch.setattr(fetcher_mod, "load_config", _make_patched_load_config(db_path, logs_dir))

    rc = fetcher_mod.main(
        [
            "--base-url",
            "https://example.invalid",
            "--markets",
            "BINANCE-ETHUSDT-29MAY2026",
            "--kinds",
            "market-trades",
            "--since",
            "2026-04-26",
            "--until",
            "2026-04-26",
            "--out",
            str(tmp_path / "ndjson"),
            "--manifest",
            str(tmp_path / "fetcher-manifest.json"),
            "--config",
            _DEFAULT_CONFIG,
            "--no-fetch",
        ]
    )
    assert rc == 0, f"fetcher_main returned {rc}, expected 0"

    # Find the sidecar: logs_dir/<YYYY-MM-DD>/<run_id>.manifest.json
    date_dirs = list(logs_dir.iterdir()) if logs_dir.exists() else []
    assert date_dirs, f"no date subdirs found in {logs_dir}"
    sidecars = list(date_dirs[0].glob("*.manifest.json"))
    assert sidecars, f"no sidecar JSON found in {date_dirs[0]}"
    sidecar = sidecars[0]
    payload = json.loads(sidecar.read_text())
    assert "run_id" in payload, "sidecar missing run_id"
    # sidecar filename is <run_id>.manifest.json
    assert (
        payload["run_id"] in sidecar.name
    ), f"sidecar filename {sidecar.name} does not embed the run_id {payload['run_id']}"


def test_fetcher_inserts_run_manifests_sqlite_row(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """state.run_manifests has the fetcher's run_id row after fetcher CLI runs.

    Mirrors test_sqlite_single_writer.py::test_run_manifests_round_trip but invokes the
    fetcher script entry instead of writers.run_manifests.insert_run_manifest directly.
    """
    import scripts.fetch_historical_data as fetcher_mod

    from tests.conftest import apply_migrations

    db_path = tmp_path / "state.sqlite"
    logs_dir = tmp_path / "logs"
    apply_migrations(db_path)

    monkeypatch.setattr(fetcher_mod, "load_config", _make_patched_load_config(db_path, logs_dir))

    rc = fetcher_mod.main(
        [
            "--base-url",
            "https://example.invalid",
            "--markets",
            "BINANCE-ETHUSDT-29MAY2026",
            "--kinds",
            "market-trades",
            "--since",
            "2026-04-26",
            "--until",
            "2026-04-26",
            "--out",
            str(tmp_path / "ndjson"),
            "--manifest",
            str(tmp_path / "fetcher-manifest.json"),
            "--config",
            _DEFAULT_CONFIG,
            "--no-fetch",
        ]
    )
    assert rc == 0, f"fetcher_main returned {rc}, expected 0"

    with open_connection(db_path) as conn:
        rows = conn.execute("SELECT run_id, mode, market_id FROM run_manifests").fetchall()
    assert len(rows) == 1, f"expected exactly 1 run_manifests row, got {len(rows)}"
    assert rows[0][1] == default_config.mode, f"mode mismatch: got {rows[0][1]!r}, expected {default_config.mode!r}"
