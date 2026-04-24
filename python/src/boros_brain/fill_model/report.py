"""Periodic operator-facing rollup of fill_model_fits rows.

Aggregates the latest fit per (market, side) from state.fill_model_fits and
writes a JSON payload + optional Markdown table. Degraded rows are sorted first
so operator attention is immediately drawn to degraded markets.

[[rolling-14-day-refit-cadence-and-staleness]]
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..state.writers.fill_model_fits import get_latest_fit

log = structlog.get_logger(__name__)

__all__ = ["write_fill_model_report"]


def write_fill_model_report(
    config: BotConfig,
    out_json_path: Path,
    *,
    out_markdown_path: Path | None = None,
) -> dict[str, object]:
    """Aggregate fit rows across config.markets × (long, short); write JSON (+ Markdown).

    Returns the payload dict (for inline display in the force-degrade smoke path).
    Degraded rows sort first so the operator sees them at the top.
    """
    fits: list[dict[str, object]] = []
    for mkt in config.markets:
        for side in ("long", "short"):
            fit = get_latest_fit(Path(config.infra.sqlite_path), mkt.market_id, side)
            if fit is not None:
                fits.append(
                    {
                        "market_id": fit.market_id,
                        "side": fit.side,
                        "fit_window_end_ts": fit.fit_window_end_ts,
                        "fit_status": fit.fit_status,
                        "n_observations": fit.n_observations,
                        "converged": fit.converged,
                        "log_likelihood": fit.log_likelihood,
                        "aic": fit.aic,
                        "event_index_coverage": fit.event_index_coverage,
                    }
                )
    # Sort degraded rows first
    fits.sort(key=lambda f: (f["fit_status"] != "degraded", f["market_id"], f["side"]))

    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "total_count": len(fits),
        "degraded_count": sum(1 for f in fits if f["fit_status"] == "degraded"),
        "fits": fits,
    }

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(payload, indent=2))

    if out_markdown_path is not None:
        out_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = [
            f"# Fill Model Report — {datetime.now(UTC).strftime('%Y-%m-%d')}",
            "",
            f"Total fits: {payload['total_count']}, Degraded: {payload['degraded_count']}",
            "",
            "| Market | Side | Status | N | Converged | LogLik | AIC | EI cov |",
            "|--------|------|--------|---|-----------|--------|-----|--------|",
        ]
        for f in fits:
            ll = f["log_likelihood"]
            aic = f["aic"]
            ll_str = f"{ll:.2f}" if isinstance(ll, int | float) and ll == ll else "nan"  # NaN check
            aic_str = f"{aic:.2f}" if isinstance(aic, int | float) and aic == aic else "nan"
            lines.append(
                f"| {f['market_id']} | {f['side']} | {f['fit_status']} | {f['n_observations']} | "
                f"{f['converged']} | {ll_str} | {aic_str} | {f['event_index_coverage']} |"
            )
        out_markdown_path.write_text("\n".join(lines) + "\n")

    log.info("fill_model.report_written", total=payload["total_count"], degraded=payload["degraded_count"])
    return payload
