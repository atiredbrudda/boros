"""INFRA-06 / PROTO-01 / T-03-01 — RUN_MANIFEST reflects over BotConfig.

These tests enforce PITFALLS §D2: any knob added in code without being reachable
via `BotConfig.model_dump(mode='json')` is a bug. The reflection-based manifest
writer walks the entire sub-model tree, so adding a new StrictBase field surfaces
automatically in `manifest['config']`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from pydantic import BaseModel

from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest
from boros_brain.state.db import open_connection

_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


def _upgrade(db_path: Path) -> None:
    """Apply the `run_manifests` table migration to a fresh sqlite file."""
    with open_connection(db_path):
        pass
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


_EXPECTED_TOP_LEVEL_FIELDS = {
    "run_id",
    "parent_run_id",
    "started_at",
    "mode",
    "strategy_version",
    "git_sha",
    "git_dirty",
    "market_id",
    "side",
    "wallet_address_hash",
    "config",
    "chain_time_drift_at_start_seconds",
    "agent_wallet_gas_balance_at_start",
}


def _collect_leaf_paths(model_cls: type[BaseModel], prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Walk every nested Pydantic sub-model recursively, returning leaf field paths.

    A leaf is a field whose annotation is NOT a BaseModel subclass (list, scalar, etc).
    For the BotConfig schema every non-model field is either a scalar or a list of
    MarketCalibration (handled by walking the list item's model_fields).
    """
    leaves: set[tuple[str, ...]] = set()
    for name, info in model_cls.model_fields.items():
        ann = info.annotation
        # Recurse into nested Pydantic models.
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            leaves |= _collect_leaf_paths(ann, prefix + (name,))
            continue
        # Recurse into list[Model] (MarketCalibration list case).
        origin = getattr(ann, "__origin__", None)
        args = getattr(ann, "__args__", ())
        if origin in (list, tuple) and args:
            inner = args[0]
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                leaves.add(prefix + (name,))  # list itself is a leaf in the manifest dict
                continue
        leaves.add(prefix + (name,))
    return leaves


def _walk_dict_paths(d: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, dict):
                # Always record the dict-field path itself as a leaf so that
                # dict[str, scalar] BotConfig knobs (e.g.
                # underlying_stale.expected_cadence_s_per_exchange) are found
                # by the missing-knob assertion even when _collect_leaf_paths
                # treats them as a single leaf rather than per-key leaves.
                paths.add(prefix + (k,))
                paths |= _walk_dict_paths(v, prefix + (k,))
            else:
                paths.add(prefix + (k,))
    return paths


def test_manifest_contains_all_knobs(default_config: BotConfig) -> None:
    """T-03-01 guard: every BotConfig leaf field appears in manifest['config']."""
    manifest = build_run_manifest(default_config)
    knob_tree = manifest.config

    expected_leaves = _collect_leaf_paths(BotConfig)
    actual_leaves = _walk_dict_paths(knob_tree)

    missing = expected_leaves - actual_leaves
    assert not missing, f"knobs missing from manifest: {sorted(missing)}"


def test_manifest_has_all_required_top_level_fields(default_config: BotConfig) -> None:
    manifest = build_run_manifest(default_config)
    actual = set(manifest.model_dump(mode="json").keys())
    assert actual == _EXPECTED_TOP_LEVEL_FIELDS, (
        f"top-level manifest fields drifted: missing={_EXPECTED_TOP_LEVEL_FIELDS - actual} "
        f"extra={actual - _EXPECTED_TOP_LEVEL_FIELDS}"
    )


def test_wallet_address_hash_is_deterministic(default_config: BotConfig) -> None:
    m1 = build_run_manifest(default_config)
    m2 = build_run_manifest(default_config)
    assert m1.wallet_address_hash == m2.wallet_address_hash
    assert len(m1.wallet_address_hash) == 16


def test_fill_model_leaves_surfaced(default_config: BotConfig) -> None:
    """T-02-R-01: PROTO-04 — every fill_model.* knob auto-surfaces via reflection.

    Adding a FillModelConfig field without this test passing is a signal that the
    field is not reachable via BotConfig.model_dump(mode='json') reflection —
    which would mean it silently disappears from the RUN_MANIFEST.
    """
    leaves = _collect_leaf_paths(BotConfig)
    fill_model_leaves = [".".join(leaf) for leaf in leaves if leaf and leaf[0] == "fill_model"]
    # 11 knobs; covariate_whitelist is a list-leaf (counted as 1) per the existing collector
    assert len(fill_model_leaves) >= 11, (
        f"expected >=11 fill_model leaves, got {len(fill_model_leaves)}: {fill_model_leaves}"
    )
    # Spot-check specific knobs
    assert "fill_model.window_days" in fill_model_leaves
    assert "fill_model.queue_tracker_bias_mode" in fill_model_leaves
    assert "fill_model.covariate_whitelist" in fill_model_leaves


def test_phase3_leaves_surfaced(default_config: BotConfig) -> None:
    """PROTO-04 (Plan 03-04): every Phase-3 knob auto-surfaces via reflection.

    Covers loss_model (incl. nested fees.*), reward_share_model, pricing, sizer.
    Expected leaf count: ~35 (8 fees + 12 loss_model leaves + 5 reward_share_model
    + 4 pricing + 6 sizer). The reflection collector counts the nested
    ``loss_model.fees`` sub-model leaves under their full ``loss_model.fees.*``
    path, so 11 LossModelConfig fields + 8 FeesConfig fields = 19 loss_model
    leaves total (the ``fees`` field itself is not a leaf because it's a
    StrictBase sub-model).
    """
    leaves = _collect_leaf_paths(BotConfig)
    leaf_strs = [".".join(leaf) for leaf in leaves]

    loss_leaves = [s for s in leaf_strs if s.startswith("loss_model.")]
    reward_share_leaves = [s for s in leaf_strs if s.startswith("reward_share_model.")]
    pricing_leaves = [s for s in leaf_strs if s.startswith("pricing.")]
    sizer_leaves = [s for s in leaf_strs if s.startswith("sizer.")]

    assert len(loss_leaves) >= 12, (
        f"expected >=12 loss_model leaves (incl. fees.*), got {len(loss_leaves)}: {loss_leaves}"
    )
    assert len(reward_share_leaves) >= 5, (
        f"expected >=5 reward_share_model leaves, got {reward_share_leaves}"
    )
    assert len(pricing_leaves) >= 4, (
        f"expected >=4 pricing leaves, got {pricing_leaves}"
    )
    assert len(sizer_leaves) >= 6, (
        f"expected >=6 sizer leaves, got {sizer_leaves}"
    )

    # Aggregate count: 11 LossModelConfig leaves (depth_bucket_edges,
    # tau_bucket_edges_days, min_samples_per_cell, knn_k, knn_max_distance,
    # aggregation_metric, window_days, refit_cadence_s, fit_warn_staleness_s,
    # fit_max_staleness_s, close_latency_budget_s — `fees` itself is a
    # StrictBase sub-model so does NOT count as a leaf) + 8 FeesConfig leaves
    # (taker_fee_rate, settlement_fee_rate, settlement_period_s,
    # market_entrance_fee_usd, gas_place_gwei, gas_cancel_gwei, gas_close_gwei,
    # gas_price_gwei) + 5 RewardShareModelConfig + 4 PricingConfig + 6
    # SizerConfig = 34 total. Plan 03-04 acceptance criterion §6 stated 35 as
    # a rough upper-bound; the actual leaf count is 34 (Plan 03-04 plan-prose
    # off-by-one — see SUMMARY.md Deviations §1).
    phase3_leaves = loss_leaves + reward_share_leaves + pricing_leaves + sizer_leaves
    assert len(phase3_leaves) >= 34, (
        f"expected >=34 total Phase-3 leaves, got {len(phase3_leaves)}: {phase3_leaves}"
    )

    # Spot-check specific critical knobs (one from each sub-model + fees nested).
    assert "loss_model.depth_bucket_edges" in loss_leaves
    assert "loss_model.fees.taker_fee_rate" in loss_leaves
    assert "loss_model.fees.settlement_fee_rate" in loss_leaves
    assert "loss_model.fees.gas_price_gwei" in loss_leaves
    assert "reward_share_model.competition_poll_interval_s" in reward_share_leaves
    assert "reward_share_model.cap_apr_multiple" in reward_share_leaves
    assert "pricing.pendle_price_usd" in pricing_leaves
    assert "pricing.price_source" in pricing_leaves
    assert "sizer.collateral_usd" in sizer_leaves
    assert "sizer.q_min_pendle" in sizer_leaves
    assert "sizer.notional_per_yu_usd" in sizer_leaves


def test_git_sha_and_dirty_captured(default_config: BotConfig) -> None:
    m = build_run_manifest(default_config)
    assert isinstance(m.git_sha, str) and len(m.git_sha) >= 7
    assert isinstance(m.git_dirty, bool)


def test_first_log_line_is_manifest_and_sidecar_written(default_config: BotConfig, tmp_path: Path, monkeypatch) -> None:
    """Dry-run subprocess — manifest first log line + sidecar JSON parity.

    Uses the library functions directly (not the subprocess) to stay fast and
    dependency-free; the end-to-end subprocess smoke is covered by
    test_tracer_bullet.test_manifest_writer_emits_first_line.
    """
    import json

    from boros_brain.logging.structlog_setup import configure_logging
    from boros_brain.manifest.writer import write_manifest

    logs_dir = tmp_path / "logs"
    sqlite_path = tmp_path / "state.sqlite"
    _upgrade(sqlite_path)

    # Build + write manifest (sidecar + SQLite row).
    manifest = build_run_manifest(default_config)
    sidecar_path = write_manifest(manifest, logs_dir=logs_dir, sqlite_path=sqlite_path)

    # Configure logging with manifest-first invariant, then close all handlers so
    # the file is flushed for read-back.
    configure_logging(
        run_id=manifest.run_id,
        tier="brain",
        logs_dir=logs_dir,
        first_manifest_line=manifest.model_dump(mode="json"),
    )

    # Find the log file.
    brain_logs = list(logs_dir.rglob(f"{manifest.run_id}.brain.log.jsonl"))
    assert brain_logs, f"no brain log file found under {logs_dir}"
    log_path = brain_logs[0]
    first_line_raw = log_path.read_text().splitlines()[0]
    first = json.loads(first_line_raw)
    assert first["event"] == "RUN_MANIFEST"
    assert first["run_id"] == manifest.run_id

    # Sidecar parity.
    side = json.loads(sidecar_path.read_text())
    assert side["run_id"] == manifest.run_id
    assert side["config"] == manifest.config
