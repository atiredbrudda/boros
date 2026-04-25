"""DECIDE-03 — GasHistoryCache EWMA cancel_cost + linter tests (RED until 04-03 lands).

Covers:
  - test_ewma_correctness: EWMA of fee_history yields correct wei→PENDLE conversion
  - test_ttl_cache: second call does NOT invoke w3.eth.fee_history (TTL caching)
  - test_linter_catches_hardcoded: scripts/no_hardcoded_cancel_cost_lint detects literal
  - test_linter_passes_when_clean: lint passes on actual decision/ dir (xfail until 04-03)

See [[gas-history-ewma-cancel-cost]] and [[ev-cancel-rule-implementation-v05]].
PITFALLS §C5: hardcoded cancel_cost scalar is a DECIDE-03 invariant violation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# RED state guard: gas_history module lands in Plan 04-03.
gas_mod = pytest.importorskip("boros_brain.decision.gas_history")

from boros_brain.config.schema import BotConfig  # noqa: E402

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.asyncio
async def test_ewma_correctness(default_config: BotConfig) -> None:
    """DECIDE-03 — EWMA over fee_history yields correct wei→PENDLE conversion.

    Mocked fee_history returns baseFeePerGas=100 gwei, reward=[[10 gwei]] for 101 blocks.
    Expected cancel_cost calculation (Rule 1 fix — original comment had arithmetic error):
      110 gwei = 110 * 10^9 wei/gas (1 gwei = 10^9 wei)
      gas_units = 200_000
      cost_wei = 110 * 10^9 * 200_000 = 2.2 * 10^16 wei
      cost_eth = 2.2e16 / 1e18 = 0.022 ETH
      cost_usd = 0.022 * 3000 = 66 USD
      cost_pendle = 66 / 3.0 = 22.0 PENDLE
    """
    # Build a config with known pricing knobs.
    # [Rule 1 fix] The pricing knobs are at config.pricing.* not config.data.*
    config_dict = default_config.model_dump(mode="json")
    config_dict.setdefault("pricing", {})
    config_dict["pricing"]["pendle_price_usd"] = 3.0
    config_dict["pricing"]["eth_price_usd"] = 3000.0
    patched_config = BotConfig.model_validate(config_dict)

    # Mock w3 — fee_history returns 101 blocks at 100 gwei base + 10 gwei tip.
    mock_w3 = AsyncMock()
    fee_history_result = type("FH", (), {
        "baseFeePerGas": [100 * 10**9] * 101,
        "reward": [[10 * 10**9]] * 100,
    })()
    mock_w3.eth.fee_history = AsyncMock(return_value=fee_history_result)

    cache = gas_mod.GasHistoryCache()
    cost = await cache.cancel_cost_pendle(w3=mock_w3, config=patched_config)

    # Median priority fee over 100 samples at 10 gwei → base 100 + tip 10 = 110 gwei
    # All 100 samples are identical (110 gwei), so EWMA = 110 gwei exactly.
    # tolerance ±15% to accommodate EWMA seeding vs simple average
    expected = 22.0  # PENDLE (Rule 1 fix: original value 0.022 had a 1000x arithmetic error)
    assert abs(cost - expected) / expected < 0.15, (
        f"cancel_cost_pendle={cost:.6f} deviates >15% from expected {expected}"
    )


@pytest.mark.asyncio
async def test_ttl_cache(default_config: BotConfig) -> None:
    """DECIDE-03 — second call within TTL must NOT invoke w3.eth.fee_history.

    This proves the GasHistoryCache respects its TTL and does not make redundant
    RPC calls on every decision loop tick.
    """
    mock_w3 = AsyncMock()
    fee_history_result = type("FH", (), {
        "baseFeePerGas": [100 * 10**9] * 101,
        "reward": [[10 * 10**9]] * 100,
    })()
    mock_w3.eth.fee_history = AsyncMock(return_value=fee_history_result)

    cache = gas_mod.GasHistoryCache()
    # First call — should invoke fee_history
    await cache.cancel_cost_pendle(w3=mock_w3, config=default_config)
    # Second call — must use cache (TTL not expired)
    await cache.cancel_cost_pendle(w3=mock_w3, config=default_config)

    assert mock_w3.eth.fee_history.call_count == 1, (
        f"fee_history called {mock_w3.eth.fee_history.call_count} times; "
        "expected exactly 1 (TTL cache should suppress second call)"
    )


def _load_lint_mod(lint_script: Path):
    """Load a lint script module from path, isolated from any cached module state."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(lint_script.stem + "_fresh", lint_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_linter_catches_hardcoded(tmp_path: Path) -> None:
    """DECIDE-03 — no_hardcoded_cancel_cost_lint.py catches literal scalar in decision/.

    Writes a temp file with `cancel_cost = 0.5` into the protected dir then
    invokes the lint script's main() and asserts exit code == 1.

    [Rule 1 fix]: lint script uses relative PROTECTED_DIRS so must be invoked
    from the repo root (not from python/ subdir where pytest runs).
    """
    import os

    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "scripts"
    lint_script = scripts_dir / "no_hardcoded_cancel_cost_lint.py"
    assert lint_script.exists(), f"Lint script not found: {lint_script}"

    # Write an offending file into the protected directory
    protected_dir = repo_root / "python" / "src" / "boros_brain" / "decision"
    protected_dir.mkdir(parents=True, exist_ok=True)
    bad_file = protected_dir / "_test_lint_probe_cancel_cost.py"
    old_cwd = os.getcwd()
    try:
        bad_file.write_text("cancel_cost = 0.5\n")
        # Change to repo root so the lint script's relative PROTECTED_DIRS resolve
        os.chdir(repo_root)
        mod = _load_lint_mod(lint_script)
        exit_code = mod.main()
        assert exit_code == 1, (
            f"Expected lint exit code 1 (violation found), got {exit_code}"
        )
    finally:
        os.chdir(old_cwd)
        bad_file.unlink(missing_ok=True)


def test_linter_passes_when_clean() -> None:
    """DECIDE-03 — lint passes on actual decision/ dir after 04-03 lands gas_history.py.

    gas_history.py uses `self.last_value_pendle = float(pendle)` which does NOT
    match the cancel_cost literal pattern.
    """
    import os

    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "scripts"
    lint_script = scripts_dir / "no_hardcoded_cancel_cost_lint.py"

    old_cwd = os.getcwd()
    try:
        os.chdir(repo_root)
        mod = _load_lint_mod(lint_script)
        exit_code = mod.main()
        assert exit_code == 0, (
            f"no_hardcoded_cancel_cost_lint exited {exit_code} (expected 0 on a clean tree)"
        )
    finally:
        os.chdir(old_cwd)
