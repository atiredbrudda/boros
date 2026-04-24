"""DATA-08 screener report writer.

Writes ``var/reports/screener_metrics.json`` with the full metric tree for all
evaluated markets plus the ranked shortlist (capped at 4).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .filter import MarketScreeningResult

_SHORTLIST_MAX = 4


def write_screener_metrics_report(
    results: list[MarketScreeningResult],
    out: str | Path,
) -> None:
    """Write the screener results to a JSON file.

    Parameters
    ----------
    results:
        Full list of ``MarketScreeningResult`` objects (pass + fail markets).
    out:
        Output path (e.g. ``var/reports/screener_metrics.json``). Parent
        directories are created if they do not exist.
    """
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Shortlist: passing markets ranked by r_apr_potential desc, capped at 4
    shortlist = sorted(
        [r for r in results if r.filter_pass],
        key=lambda r: r.r_apr_potential or 0.0,
        reverse=True,
    )[:_SHORTLIST_MAX]

    payload = {
        "results": [asdict(r) for r in results],
        "shortlist": [r.market_id for r in shortlist],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
