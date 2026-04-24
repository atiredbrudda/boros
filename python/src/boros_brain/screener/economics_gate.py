"""DATA-09 economics kill-switch.

Formula (verbatim per 01-RESEARCH.md §Pattern 10):
    R_apr_on_collateral = R_share_per_epoch * epochs_per_year / required_collateral
    R_share_per_epoch = E_liq_per_epoch * side_split * (Q_me * t_frac) / (Sigma_others + Q_me * t_frac)
    epochs_per_year = 52 (PROJECT.md L63, weekly epochs Fri 00:00 UTC -> Thu 23:59 UTC)
    Kill: drop(market) iff R_apr_on_collateral < alt_yield + fill_loss_coarse_bound

Per checker issue #06 (Option A): computed in PENDLE-units to avoid introducing a
`pendle_price_usd` knob in Phase 1 without a price oracle. USD conversion is a Phase-3
concern (see <deferred> block in 01-12-PLAN.md). Because BOTH alt_yield and
fill_loss_coarse_bound are decimal-fraction APRs (unitless), and `r_apr_pendle` is also
a decimal-fraction APR, they compare directly -- the decision
"drop(market) iff r_apr < alt_yield + fill_loss_coarse_bound" is unit-safe.

[[Economics kill-switch v0.5]]
[[fill_loss_coarse_bound v0.5]]
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ..config.loader import load_config, load_raw_yaml
from .kill_report import write_kill_report

log = structlog.get_logger(__name__)

# PROJECT.md L63 -- weekly epochs (Fri 00:00 UTC -> Thu 23:59 UTC). Locked constant.
EPOCHS_PER_YEAR = 52


class ConfigError(RuntimeError):
    """Raised when a required kill-switch knob is missing or out of range."""


class ProjectHalt(SystemExit):
    """Signals Phase 1 economics-gate halt: empty shortlist after DATA-09 filter.

    CLI converts this to exit code 1. Inherits SystemExit so bare `except Exception`
    does NOT accidentally swallow it.
    """


def _assert_knobs_explicit(raw_yaml: dict[str, Any]) -> None:
    """Per locked decision (T-01-12-01): kill-switch refuses silent defaults.

    Both `alt_yield` and `fill_loss_coarse_bound` MUST be present as explicit keys
    under `screener:` in the operator-authored YAML. Pydantic applies defaults if a
    key is absent; this pre-validation step catches that case BEFORE Pydantic runs.
    """
    screener = raw_yaml.get("screener", {}) or {}
    if "alt_yield" not in screener:
        raise ConfigError("knob alt_yield missing -- kill-switch refuses to run with silent default")
    if "fill_loss_coarse_bound" not in screener:
        raise ConfigError("knob fill_loss_coarse_bound missing -- kill-switch refuses to run with silent default")


def _assert_knobs_in_range_raw(raw_yaml: dict[str, Any]) -> None:
    """Unit-confusion guard on raw YAML values (T-01-12-02).

    Runs BEFORE Pydantic validation so we emit our own diagnostic ConfigError rather
    than letting Pydantic's generic ValidationError surface first.

    Caps: alt_yield in (0.0, 0.5) -- 50% max. fill_loss_coarse_bound in (0.0, 0.2) -- 20% max.
    If operator truly wants > 50% alt-yield or > 20% fill-loss, they must override the cap
    explicitly (indicating intentional choice, not a typo of 5.0 for 0.05).
    """
    screener = raw_yaml.get("screener", {}) or {}
    alt_yield = screener.get("alt_yield")
    fill_loss = screener.get("fill_loss_coarse_bound")
    if alt_yield is not None and not (0.0 < float(alt_yield) < 0.5):
        raise ConfigError(
            f"alt_yield out of range (0.0, 0.5) -- got {alt_yield}; "
            f"likely unit confusion (use decimal fraction: 0.05 = 5% APR, not 5.0)"
        )
    if fill_loss is not None and not (0.0 < float(fill_loss) < 0.2):
        raise ConfigError(
            f"fill_loss_coarse_bound out of range (0.0, 0.2) -- got {fill_loss}; "
            f"likely unit confusion (use decimal fraction: 0.02 = 2% APR, not 2.0)"
        )


def _assert_knobs_in_range(config: Any) -> None:
    """Unit-confusion guard post-Pydantic (belt-and-suspenders, T-01-12-02).

    Called after _assert_knobs_in_range_raw; provides a second check in case the raw
    YAML values slipped through (e.g., borderline values exactly at 0.5 that Pydantic
    would have accepted via le=1.0 but we want to reject).
    """
    if not (0.0 < config.screener.alt_yield < 0.5):
        raise ConfigError(
            f"alt_yield out of range (0.0, 0.5) -- got {config.screener.alt_yield}; "
            f"likely unit confusion (use decimal fraction: 0.05 = 5% APR, not 5.0)"
        )
    if not (0.0 < config.screener.fill_loss_coarse_bound < 0.2):
        raise ConfigError(
            f"fill_loss_coarse_bound out of range (0.0, 0.2) -- got {config.screener.fill_loss_coarse_bound}; "
            f"likely unit confusion (use decimal fraction: 0.02 = 2% APR, not 2.0)"
        )


def compute_r_apr_on_collateral_pendle(
    *,
    e_liq_per_epoch: float,  # PENDLE/epoch from reward_budget_history.e_liq_per_epoch
    side_split: float,  # long_budget_share or short_budget_share (0.0..1.0)
    q_me: float,  # operator-committed size (same units as sigma_others)
    sigma_others: float,  # aggregate competing size in range (same units as q_me)
    t_frac: float,  # time-frac of epoch posted (v0.5: 1.0)
    required_collateral_pendle: float,  # required collateral expressed in PENDLE-units
) -> float:
    """Returns R_apr_on_collateral as a decimal-fraction APR in PENDLE-units.

    Formula verbatim from 01-RESEARCH.md §Pattern 10:
        R_share_per_epoch_pendle = e_liq * side_split * (q_me * t_frac) / (sigma_others + q_me * t_frac)
        R_apr_pendle = R_share_per_epoch_pendle * EPOCHS_PER_YEAR / required_collateral_pendle

    Per checker issue #06 (Option A): computed in PENDLE-units to avoid a pendle_price_usd
    knob in Phase 1. USD conversion deferred to Phase 3 (see 01-12-PLAN.md <deferred> block).
    """
    denominator = sigma_others + q_me * t_frac
    if denominator == 0.0:
        return 0.0
    r_share_per_epoch_pendle = e_liq_per_epoch * side_split * (q_me * t_frac) / denominator
    r_apr_pendle = r_share_per_epoch_pendle * EPOCHS_PER_YEAR / required_collateral_pendle
    return r_apr_pendle


def run_economics_gate(
    config_path: str,
    screener_metrics_path: str = "var/reports/screener_metrics.json",
) -> list[str]:
    """Apply DATA-09 economics kill-switch.

    Returns the shortlist (market_ids passing the gate). Raises ProjectHalt if the
    shortlist is empty after filtering. Raises ConfigError on missing or out-of-range
    knobs (T-01-12-01, T-01-12-02).

    Exit-code contract (for CLI wrapper):
        ConfigError  -> exit 2  (operator error, not a strategy halt)
        ProjectHalt  -> exit 1  (economics gate empty shortlist)
        normal return -> exit 0
    """
    # T-01-12-01: assert explicit keys BEFORE Pydantic applies defaults
    raw = load_raw_yaml(config_path)
    _assert_knobs_explicit(raw)

    # T-01-12-02: assert decimal-fraction range on raw values BEFORE Pydantic validation
    # so our ConfigError fires instead of Pydantic's generic ValidationError.
    _assert_knobs_in_range_raw(raw)

    config = load_config(config_path)
    # Belt-and-suspenders post-Pydantic range check
    _assert_knobs_in_range(config)

    metrics = json.loads(Path(screener_metrics_path).read_text())
    threshold = config.screener.alt_yield + config.screener.fill_loss_coarse_bound

    rows: list[dict[str, Any]] = []
    shortlist: list[str] = []

    for mr in metrics.get("results", []):
        if not mr.get("filter_pass", False):
            continue  # already rejected by DATA-08; DATA-09 only re-evaluates passers

        r_apr = mr.get("r_apr_potential")
        if r_apr is None:
            log.warning("economics_gate.no_r_apr", market_id=mr.get("market_id"))
            continue

        delta = r_apr - threshold
        passes = delta >= 0.0

        rows.append(
            {
                "market_id": mr["market_id"],
                "r_apr_on_collateral": r_apr,
                "alt_yield_used": config.screener.alt_yield,
                "fill_loss_used": config.screener.fill_loss_coarse_bound,
                "threshold": threshold,
                "delta": delta,
                "halt_reason": "" if passes else f"R_apr {r_apr:.4f} < threshold {threshold:.4f}",
            }
        )
        if passes:
            shortlist.append(mr["market_id"])

    # Write per-market decisions to audit trail (non-halt path too)
    Path("var/reports").mkdir(parents=True, exist_ok=True)
    Path("var/reports/economics_gate.json").write_text(
        json.dumps(
            {"threshold": threshold, "rows": rows, "shortlist": shortlist},
            indent=2,
        )
    )

    if not shortlist:
        # T-01-12-04: write kill-report BEFORE raising halt
        write_kill_report(rows, config=config, threshold=threshold)
        today = datetime.now(UTC).strftime("%Y%m%d")
        raise ProjectHalt(f"DATA-09 empty shortlist. Threshold {threshold:.4f}. " f"See docs/kill-report-{today}.md")

    log.info(
        "economics_gate.pass",
        shortlist=shortlist,
        threshold=threshold,
        markets_evaluated=len(rows),
    )
    return shortlist
