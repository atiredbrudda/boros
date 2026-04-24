"""REWARD-03 / REWARD-04 — Sizer subsystem.

REWARD-03: q_me_target() composes fill_model.predict + loss_model.expected_loss +
reward_model.r_capped_curve to maximize EV under the constraint
Q_min ≤ Q_me ≤ min(Q_max, Q_cap). Grid-search + scipy.optimize.minimize_scalar
polish.

REWARD-04: Q_cap boundary (imported from reward_model.q_cap.compute_q_cap and
applied as the upper bound of the optimizer's bracket).

At $100 collateral the optimizer returns Q_min trivially (collateral-constrained
sub-cap regime). At $5000+ collateral the cap binds and the optimizer returns
an interior Q_me_target < Q_cap in the cap_binding regime.

[[sizing-optimizer-sub-cap-regime-v05]]
"""
