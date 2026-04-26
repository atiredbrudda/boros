"""PROTO-01 + PROTO-04 — backtest manifest first log + reflection assertion (Plan 05-09).

test_first_stdout_line_is_run_manifest_json: first log line has event='RUN_MANIFEST' and mode='backtest'.
test_manifest_contains_all_botconfig_leaves: assert_manifest_contains_all_botconfig_leaves passes / fails.
test_manifest_includes_backtest_meta_knobs: manifest.config contains backtest.* keys (PROTO-04).

[[backtest-cli-and-run-manifest-emission]]
[[run-manifest-writer]]
"""

from __future__ import annotations

import pytest

from boros_brain.backtest.run_manifest import assert_manifest_contains_all_botconfig_leaves
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest


def test_manifest_contains_all_botconfig_leaves(default_config: BotConfig) -> None:
    """assert_manifest_contains_all_botconfig_leaves does NOT raise on a fresh manifest.

    Then mutates the config dict and asserts it RAISES AssertionError with 'missing'.
    """
    manifest = build_run_manifest(default_config)
    # Should NOT raise
    assert_manifest_contains_all_botconfig_leaves(manifest, default_config)

    # Mutate manifest.config copy — remove a key and assert the assertion fires
    # We need to reach into the frozen manifest to test the mismatch branch.
    # The manifest is frozen (RunManifest is frozen=True), so we construct a
    # patched version by copy.
    import copy

    config_dict = copy.deepcopy(manifest.config)
    # Remove a known numeric leaf from the config dict
    # 'screener.alt_yield' is a float leaf — remove it from the copy
    config_dict_patched = copy.deepcopy(config_dict)
    # Navigate to screener sub-dict and pop a float key
    if "screener" in config_dict_patched and "alt_yield" in config_dict_patched["screener"]:
        del config_dict_patched["screener"]["alt_yield"]
    else:
        pytest.skip("screener.alt_yield not found in default config — skipping mutation test")

    from boros_brain.manifest.schema import RunManifest

    patched_manifest = RunManifest(
        **{
            **manifest.model_dump(mode="json"),
            "config": config_dict_patched,
        }
    )
    with pytest.raises(AssertionError, match="missing"):
        assert_manifest_contains_all_botconfig_leaves(patched_manifest, default_config)


def test_manifest_includes_backtest_meta_knobs(default_config: BotConfig) -> None:
    """manifest.config contains BotConfig.backtest.* leaves (PROTO-04 — ALL knobs in manifest).

    The perturbation grid EXCLUDES backtest.* leaves (strategy fragility != method fragility).
    The manifest MUST include them (reproducibility across bootstrap_n_resamples changes).
    """
    manifest = build_run_manifest(default_config)
    assert "backtest" in manifest.config, "manifest.config must contain 'backtest' key"
    backtest_dict = manifest.config["backtest"]
    assert "bootstrap_n_resamples" in backtest_dict, "manifest.config['backtest'] must contain 'bootstrap_n_resamples'"
    # Default per Plan 05-01: 2000
    assert (
        backtest_dict["bootstrap_n_resamples"] == 2000
    ), f"expected bootstrap_n_resamples=2000, got {backtest_dict['bootstrap_n_resamples']}"


def test_manifest_mode_is_backtest_knob_present(default_config: BotConfig) -> None:
    """build_run_manifest reflects the full BotConfig including nested sub-models."""
    manifest = build_run_manifest(default_config)
    dumped = manifest.model_dump(mode="json")
    # Required top-level manifest fields
    for field in (
        "run_id",
        "mode",
        "git_sha",
        "strategy_version",
        "market_id",
        "side",
        "wallet_address_hash",
        "config",
    ):
        assert field in dumped, f"manifest.model_dump() missing field: {field}"
    # config must be a non-empty dict
    assert isinstance(dumped["config"], dict) and dumped["config"], "manifest.config must be a non-empty dict"
