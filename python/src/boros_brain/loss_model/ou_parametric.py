"""OU-on-basis parametric loss scaffold — v1.0 drop-in point.

v0.5 uses the empirical loss-grid (see [[empirical-loss-grid-v05]]).
v1.0 will replace this scaffold with:
  1. MLE fit of B(t) = Implied_APR - Underlying_Funding_APR as OU(kappa, theta, sigma)
     on rolling 14-day windows via scipy.optimize.minimize (see STACK.md §OU).
  2. Closed-form E[loss | fill at X, tau] = E[integral_t^{t+tau} (Realized_Funding - X) du]
     with Tang-Chen bias correction (see STACK.md §OU).
  3. Optional 2-sigma OU-vs-empirical divergence breaker (absorbs PITFALLS B5 OU-fit-degraded).

DO NOT replace NotImplementedError with a partial implementation in v0.5.
The LOSS-03 contract is 'scaffold only' — partial implementation creates two
truth sources for E[loss|fill] that will diverge.

CRITICAL: OU is for E[loss|fill], NOT for P(fill). CLOB price is a step function;
continuous diffusion models it incorrectly for fills. P(fill) stays on the NHPP
side ([[fill-model-predict-contract]]).

See [[ou-on-basis-loss-scaffold]].
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..config.schema import BotConfig
    from .schemas import ExpectedLossInput, ExpectedLossOutput


class OUBasisLossModel(Protocol):
    """v1.0 interface. expected_loss(...) signature MUST match
    brain.loss_model.expected_loss.expected_loss() exactly, so Phase 4
    DecisionEngine can swap the empirical backend for the OU backend via
    config without code changes.
    """

    def expected_loss(
        self,
        req: ExpectedLossInput,
        *,
        sqlite_path: Path,
        config: BotConfig,
    ) -> ExpectedLossOutput: ...


def fit_ou_basis(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError(
        "LOSS-03 scaffold — v1.0 drop-in point. " "See [[ou-on-basis-loss-scaffold]] for the implementation plan."
    )
