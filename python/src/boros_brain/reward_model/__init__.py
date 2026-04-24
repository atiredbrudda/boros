"""REWARD-01/02/04 — Reward share model.

REWARD-01: closed-form capped pro-rata reward share with regime classification.
REWARD-02: CompetitionTracker (REST + parquet) — Q_me + Σ_others composition.
REWARD-04: Q_cap algebra (where R_uncapped first hits cap_budget).

LOCKED D-01 (2026-04-24): operator-manual calibration of E_liq_per_epoch +
side-splits via the `calibrate` CLI subcommand. See
[[market-reward-calibration-operator-workflow]].
"""
