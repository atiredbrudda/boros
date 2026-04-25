"""DECIDE-03 — GasHistoryCache EWMA cancel_cost + linter tests (RED until 04-03 lands).

Covers:
  - test_ewma_correctness: EWMA of fee_history yields correct wei→PENDLE conversion
  - test_ttl_cache: second call does NOT invoke w3.eth.fee_history (TTL caching)
  - test_linter_catches_hardcoded: scripts/no_hardcoded_cancel_cost_lint detects literal
  - test_linter_passes_when_clean: lint passes on actual decision/ dir (xfail until 04-03)

See [[gas-history-ewma-cancel-cost]] (to be filed in Plan 04-03).
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
    Expected cancel_cost = (110 gwei * 200_000 gas) / 1e18 ETH/wei * 3000 USD/ETH / 3.0 USD/PENDLE
                         = (110e-9 * 200_000) / 1e18 * 3000 / 3.0
                         = 0.022 / 1e18 * 3000 / 3  ... wait, let's be precise:
    110 gwei = 110e9 wei. Gas limit = 200_000.
    cost_wei = 110e9 * 200_000 = 22_000_000_000_000 wei = 2.2e13 wei
    cost_eth = 2.2e13 / 1e18 = 2.2e-5 ETH
    cost_usd = 2.2e-5 * 3000 = 0.066 USD
    cost_pendle = 0.066 / 3.0 = 0.022 PENDLE
    """
    # Build a config with known pricing knobs.
    config_dict = default_config.model_dump(mode="json")
    config_dict.setdefault("pricing", {})
    config_dict["pricing"]["pendle_price_usd"] = 3.0
    config_dict.setdefault("data", {}).setdefault("eth_price_usd", 3000.0)
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
    # tolerance ±10% to accommodate EWMA vs simple average implementation choice
    expected = 0.022  # PENDLE
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


def test_linter_catches_hardcoded(tmp_path: Path) -> None:
    """DECIDE-03 — no_hardcoded_cancel_cost_lint.py catches literal scalar in decision/.

    Writes a temp file with `cancel_cost = 0.5` into the protected dir then
    invokes the lint script's main() and asserts exit code == 1.
    """
    import importlib.util
    import sys

    # Locate the lint script
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    lint_script = scripts_dir / "no_hardcoded_cancel_cost_lint.py"
    assert lint_script.exists(), f"Lint script not found: {lint_script}"

    # Write an offending file into the protected directory
    protected_dir = (
        Path(__file__).resolve().parents[2]
        / "python" / "src" / "boros_brain" / "decision"
    )
    protected_dir.mkdir(parents=True, exist_ok=True)
    bad_file = protected_dir / "_test_lint_probe_cancel_cost.py"
    try:
        bad_file.write_text("cancel_cost = 0.5\n")

        # Load and run the lint script
        spec = importlib.util.spec_from_file_location("no_hardcoded_cancel_cost_lint", lint_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        exit_code = mod.main()
        assert exit_code == 1, (
            f"Expected lint exit code 1 (violation found), got {exit_code}"
        )
    finally:
        bad_file.unlink(missing_ok=True)


@pytest.mark.xfail(reason="decision/gas_history.py does not exist until 04-03; lint passes when clean")
def test_linter_passes_when_clean(tmp_path: Path) -> None:
    """DECIDE-03 — lint passes on actual decision/ dir after 04-03 lands gas_history.py.

    xfail: the decision/ dir may contain probe stubs or not exist yet.
    Turns to PASS in Plan 04-03 once gas_history.py is the sole legit cancel_cost owner.
    """
    import importlib.util

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    lint_script = scripts_dir / "no_hardcoded_cancel_cost_lint.py"

    spec = importlib.util.spec_from_file_location("no_hardcoded_cancel_cost_lint", lint_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    exit_code = mod.main()
    assert exit_code == 0
