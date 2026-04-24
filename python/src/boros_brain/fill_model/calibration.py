"""FILL-06: Rosenblatt time-change GoF + bootstrap threshold + decile calibration plot.

Methodology (Daley & Vere-Jones, standard):
    Under correct λ(t), the integrated compensator at event times forms a
    unit-rate Poisson process. Equivalently, the differences of compensators
    at consecutive events are i.i.d. Exp(1). KS-test the transformed
    inter-arrivals against Exp(1).

Threshold calibration:
    `gof_ks_pval_threshold` default is 0.0 (disabled at v0.5 first-fit). After
    first fit, `bootstrap_gof_threshold(...)` is run to populate it with the
    5th percentile of LR across 100 in-sample resamples. Operator-visible
    value, NOT intuition-picked.

[[fill-model-goodness-of-fit-rosenblatt-time-change]]
[[rolling-14-day-refit-cadence-and-staleness]]
"""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
import structlog
from scipy import stats

from ..config.schema import BotConfig
from .fit import fit_market_side
from .predict import predict
from .schemas import PredictInput

log = structlog.get_logger(__name__)

__all__ = [
    "gof_rosenblatt",
    "bootstrap_gof_threshold",
    "run_calibration",
    "CalibrationReport",
]


@dataclass(frozen=True)
class CalibrationReport:
    market_id: str
    side: str
    holdout_n_events: int
    deciles: list[dict[str, float]] = field(default_factory=list)
    ks_pval: float = 1.0
    ks_stat: float = 0.0
    lr_vs_null: float = 0.0
    fit_status: str = "ok"
    plot_path: str | None = None


def _integrate_step(
    t_prev: float,
    t_curr: float,
    sorted_bins: list[float],
    bin_lambda: dict[float, float],
) -> float:
    """Exact integral of step-function λ from t_prev to t_curr.

    Splits the integration interval at bin boundaries so that each segment
    uses the constant rate for that bin, rather than a single midpoint
    evaluation that misses rate changes at bin edges.
    """
    total = 0.0
    # Find the bin index containing t_prev
    lo = bisect.bisect_right(sorted_bins, t_prev) - 1
    lo = max(lo, 0)
    t = t_prev
    while t < t_curr:
        bin_end = sorted_bins[lo + 1] if lo + 1 < len(sorted_bins) else t_curr
        seg_end = min(bin_end, t_curr)
        lam = bin_lambda.get(sorted_bins[lo], 0.0)
        total += lam * (seg_end - t)
        t = seg_end
        lo += 1
    return total


def gof_rosenblatt(
    event_times_s: np.ndarray,
    lambda_fn: Callable[[float], float],
    *,
    sorted_bins: list[float] | None = None,
    bin_lambda: dict[float, float] | None = None,
) -> dict[str, float]:
    """Null: λ is the true intensity. Reject ⇒ fit is bad.

    lambda_fn: callable(t: float) -> float (intensity at time t). Used as
        fallback when sorted_bins/bin_lambda are not provided.
    event_times_s: sorted event times in seconds.
    sorted_bins: if provided alongside bin_lambda, uses exact piecewise
        integration via _integrate_step (correct for step-function λ).
    bin_lambda: dict mapping bin start time → constant λ for that bin.

    Returns dict with keys: ks_stat, ks_pval, n_gaps.
    If fewer than 2 events: returns trivially perfect fit (no over-alarm).
    """
    if len(event_times_s) < 2:
        return {"ks_stat": 0.0, "ks_pval": 1.0, "n_gaps": 0.0}

    use_step = sorted_bins is not None and bin_lambda is not None

    # Integrate λ from first event to each subsequent event
    compensator: list[float] = [0.0]
    for i in range(1, len(event_times_s)):
        t_prev = float(event_times_s[i - 1])
        t_curr = float(event_times_s[i])
        if use_step:
            # Exact piecewise integration — splits at bin boundaries so that
            # inter-arrival gaps straddling two bins are handled correctly.
            integral = _integrate_step(t_prev, t_curr, sorted_bins, bin_lambda)  # type: ignore[arg-type]
        else:
            # Midpoint fallback for non-step-function λ.
            mid = 0.5 * (t_prev + t_curr)
            integral = lambda_fn(mid) * (t_curr - t_prev)
        compensator.append(compensator[-1] + integral)
    gaps = np.diff(np.array(compensator))
    # Filter out tiny/zero gaps (integration artifact)
    gaps = gaps[gaps > 0]
    if len(gaps) < 2:
        return {"ks_stat": 0.0, "ks_pval": 1.0, "n_gaps": float(len(gaps))}
    ks_stat, ks_pval = stats.kstest(gaps, "expon", args=(0, 1))
    return {"ks_stat": float(ks_stat), "ks_pval": float(ks_pval), "n_gaps": float(len(gaps))}


def bootstrap_gof_threshold(
    features_df: pl.DataFrame,
    config: BotConfig,
    market_id: str,
    side: str,
    run_id: str,
    sqlite_path: Path,
    *,
    n_bootstrap: int = 100,
    percentile: float = 5.0,
) -> float:
    """Bootstrap-calibrated threshold for gof_lr_ratio_threshold.

    Resample features with replacement n_bootstrap times, compute LR per resample,
    return the <percentile>-th percentile. Passes `persist=False` on every
    fit_market_side call — this skips both the SQLite write and the parquet
    sidecar so bootstrap resamples never pollute state.fill_model_fits. Without
    this guard, 100 resample rows per invocation would enter get_latest_fit()
    lookups and silently degrade predict() outputs.
    """
    lrs: list[float] = []
    rng = np.random.default_rng(42)
    for i in range(n_bootstrap):
        seed = int(rng.integers(0, 2**32 - 1))
        resampled = features_df.sample(n=features_df.height, with_replacement=True, seed=seed)
        try:
            art = fit_market_side(
                resampled,
                market_id=market_id,
                side=side,  # type: ignore[arg-type]
                config=config,
                run_id=f"{run_id}-bs{i}",
                sqlite_path=sqlite_path,
                persist=False,
            )
            if art.converged and not np.isnan(art.deviance):
                # LR vs null ≈ -2 * (ll_null - ll_model); statsmodels exposes `.llr`
                # which we stored as gof_lr_vs_null if available. Fallback: use -deviance
                # as a monotone proxy.
                lrs.append(float(art.gof_lr_vs_null or -art.deviance))
        except Exception as exc:  # noqa: BLE001
            log.warning("fill_model.bootstrap_resample_failed", i=i, err=str(exc))
    if not lrs:
        return 0.0
    return float(np.percentile(lrs, percentile))


def run_calibration(
    features_df: pl.DataFrame,
    config: BotConfig,
    market_id: str,
    side: str,
    sqlite_path: Path,
    *,
    holdout_fraction: float = 0.20,
    emit_plot: bool = False,
    run_id: str = "calibration-default",
) -> CalibrationReport:
    """Fit on train (first 1 - holdout_fraction), evaluate calibration on holdout."""
    df = features_df.filter((pl.col("market_id") == market_id) & (pl.col("side") == side)).sort("bin_start")
    n = df.height
    if n < 50:
        log.warning(
            "fill_model.calibration_insufficient_data",
            market_id=market_id,
            side=side,
            n_rows=n,
        )
        return CalibrationReport(market_id=market_id, side=side, holdout_n_events=0, fit_status="degraded")

    split_idx = int(n * (1.0 - holdout_fraction))
    train = df.head(split_idx)
    holdout = df.tail(n - split_idx)

    artifact = fit_market_side(
        train,
        market_id=market_id,
        side=side,  # type: ignore[arg-type]
        config=config,
        run_id=run_id,
        sqlite_path=sqlite_path,
    )

    # Predicted p_fill per holdout bin (using the persisted fit via predict())
    predicted_probs: list[float] = []
    realized_fills: list[int] = []
    whitelist = list(config.fill_model.covariate_whitelist)
    for row in holdout.iter_rows(named=True):
        try:
            feats = {name: float(row.get(name, 0.0)) for name in whitelist}
            bin_start_val = row["bin_start"]
            current_ts = int(bin_start_val.timestamp()) if hasattr(bin_start_val, "timestamp") else int(bin_start_val)
            req = PredictInput(
                market_id=market_id,
                side=side,  # type: ignore[arg-type]
                depth_from_mark_ticks=0,
                queue_ahead_wei=0,
                current_features=feats,
                time_to_epoch_end_s=float(config.fill_model.bin_duration_s),
                current_chain_ts=current_ts,
            )
            out = predict(req, sqlite_path=sqlite_path, config=config)
            predicted_probs.append(out.p_fill_this_epoch)
            realized_fills.append(1 if int(row.get("trade_count", 0)) > 0 else 0)
        except Exception as exc:  # noqa: BLE001
            # Degraded row — skip
            log.debug("calibration.row_skip", err=str(exc))
            continue

    # Decile calibration
    deciles: list[dict[str, float]] = []
    if predicted_probs:
        predicted = np.array(predicted_probs)
        realized = np.array(realized_fills)
        cutpoints = np.linspace(0, 1, 11)
        for i in range(10):
            lo, hi = cutpoints[i], cutpoints[i + 1]
            mask = (predicted >= lo) & (predicted < hi) if i < 9 else (predicted >= lo) & (predicted <= hi)
            if mask.sum() > 0:
                deciles.append(
                    {
                        "decile": float(i),
                        "predicted_mean": float(predicted[mask].mean()),
                        "realized_freq": float(realized[mask].mean()),
                        "n": float(mask.sum()),
                    }
                )

    # GoF: Rosenblatt time-change on holdout event arrivals.
    # Reconstruct proxy event times from holdout bins with trade_count > 0.
    # λ(t) = exp(β₀ + β·x_bin) / bin_duration_s (piece-wise constant intensity).
    # This is the v0.5 approximation (step-function λ); documented in
    # [[fill-model-goodness-of-fit-rosenblatt-time-change]].
    ks_pval: float = artifact.gof_ks_pval if artifact.gof_ks_pval is not None else 1.0
    ks_stat: float = 0.0
    lr_vs_null = artifact.gof_lr_vs_null if artifact.gof_lr_vs_null is not None else 0.0
    fit_status = artifact.fit_status

    if artifact.converged and len(artifact.beta) >= 1:
        import math as _math

        beta = list(artifact.beta)
        fit_whitelist = list(artifact.covariate_whitelist)
        bin_dur = float(config.fill_model.bin_duration_s)

        # Build sorted array of event arrival proxy times (mid-bin + sub-bin spacing)
        event_times_list: list[float] = []
        for row in holdout.iter_rows(named=True):
            cnt = int(row.get("trade_count", 0))
            if cnt > 0:
                bin_start_val = row["bin_start"]
                t0 = float(bin_start_val.timestamp() if hasattr(bin_start_val, "timestamp") else bin_start_val)
                # Spread events uniformly within the bin (v0.5 approximation)
                for k in range(cnt):
                    event_times_list.append(t0 + (k + 0.5) * bin_dur / max(cnt, 1))
        event_times_arr = np.sort(np.array(event_times_list))

        # λ_fn from the fitted GLM: λ(t) = exp(β₀ + β·x) / bin_duration_s
        # For a step-function model, λ is constant within each bin.
        # Build a lookup: bin_start_val → λ
        bin_lambda: dict[float, float] = {}
        for row in holdout.iter_rows(named=True):
            bin_start_val = row["bin_start"]
            t0 = float(bin_start_val.timestamp() if hasattr(bin_start_val, "timestamp") else bin_start_val)
            x = [float(row.get(name, 0.0)) for name in fit_whitelist]
            linear = beta[0] + sum(b * xi for b, xi in zip(beta[1:], x, strict=False))
            linear = max(-30.0, min(linear, 30.0))
            bin_lambda[t0] = _math.exp(linear) / bin_dur

        if len(event_times_arr) >= 2 and bin_lambda:
            sorted_bins = sorted(bin_lambda.keys())

            def _step_lambda(t: float) -> float:
                # Step function: find the bin that contains t
                lo, hi = 0, len(sorted_bins) - 1
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if sorted_bins[mid] <= t:
                        lo = mid
                    else:
                        hi = mid - 1
                return bin_lambda.get(sorted_bins[lo], 0.0)

            gof_result = gof_rosenblatt(
                event_times_arr,
                _step_lambda,
                sorted_bins=sorted_bins,
                bin_lambda=bin_lambda,
            )
            ks_pval = float(gof_result["ks_pval"])
            ks_stat = float(gof_result["ks_stat"])
        else:
            ks_stat = 0.0

    # Threshold check (only if threshold > 0)
    if config.fill_model.gof_ks_pval_threshold > 0.0 and ks_pval < config.fill_model.gof_ks_pval_threshold:
        log.warning(
            "fill_model.fit_degraded",
            market_id=market_id,
            side=side,
            reason="gof_below_threshold",
            ks_pval=ks_pval,
            threshold=config.fill_model.gof_ks_pval_threshold,
        )
        fit_status = "degraded"

    plot_path: str | None = None
    if emit_plot:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots()
            if deciles:
                xs = [d["predicted_mean"] for d in deciles]
                ys = [d["realized_freq"] for d in deciles]
                ax.plot([0, 1], [0, 1], "k--", label="ideal")
                ax.scatter(xs, ys, label="deciles")
                ax.set_xlabel("predicted p_fill_this_epoch")
                ax.set_ylabel("realized fill frequency")
                ax.set_title(f"Calibration — {market_id} {side}")
                ax.legend()
            out_dir = Path("python/docs/fill_model")
            out_dir.mkdir(parents=True, exist_ok=True)
            plot_path_obj = out_dir / f"calibration-{datetime.now(UTC).strftime('%Y-%m-%d')}.png"
            fig.savefig(plot_path_obj)
            plt.close(fig)
            plot_path = str(plot_path_obj)
        except ImportError:
            log.warning("fill_model.calibration_matplotlib_unavailable")

    return CalibrationReport(
        market_id=market_id,
        side=side,
        holdout_n_events=int(np.sum(realized_fills)),
        deciles=deciles,
        ks_pval=ks_pval,
        ks_stat=ks_stat,
        lr_vs_null=lr_vs_null,
        fit_status=fit_status,
        plot_path=plot_path,
    )
