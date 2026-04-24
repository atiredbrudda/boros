"""LOSS-03 — OU scaffold raises NotImplementedError with stable interface surface.

Test IDs: T-03-OU-01..03 (Plan 03-01, Task 1).
"""
from __future__ import annotations

import inspect

import pytest


def test_ou_scaffold_raises_not_implemented() -> None:
    """fit_ou_basis must raise NotImplementedError with 'LOSS-03 scaffold' + wiki marker."""
    from boros_brain.loss_model.ou_parametric import fit_ou_basis

    with pytest.raises(NotImplementedError) as exc_info:
        fit_ou_basis(market_id="BINANCE-ETHUSDT-29MAY2026", side="long")
    msg = str(exc_info.value)
    assert "LOSS-03 scaffold" in msg, msg
    assert "[[ou-on-basis-loss-scaffold]]" in msg, msg


def test_ou_scaffold_protocol_surface_stable() -> None:
    """OUBasisLossModel.expected_loss signature MUST be (self, req, *, sqlite_path, config).

    Locked for v1.0 drop-in. Any change here is a Phase-4 breaking change.
    """
    from boros_brain.loss_model.ou_parametric import OUBasisLossModel

    sig = inspect.signature(OUBasisLossModel.expected_loss)
    params = list(sig.parameters.keys())
    # Drop 'self' → remaining must be exactly ["req", "sqlite_path", "config"]
    assert params[0] == "self"
    assert params[1:] == ["req", "sqlite_path", "config"], params


def test_ou_scaffold_protocol_matches_empirical_expected_loss() -> None:
    """Once Task 2 lands expected_loss.py, its signature must match the Protocol.

    Skip cleanly until Task 2 lands the module.
    """
    try:
        from boros_brain.loss_model.expected_loss import expected_loss
        from boros_brain.loss_model.ou_parametric import OUBasisLossModel
    except ImportError:
        pytest.skip("expected_loss module lands in Task 2 of this plan")

    sig_protocol = inspect.signature(OUBasisLossModel.expected_loss)
    sig_empirical = inspect.signature(expected_loss)
    # Protocol has 'self', empirical doesn't. Compare params[1:] on protocol vs params[:] on empirical.
    assert (
        list(sig_protocol.parameters.keys())[1:]
        == list(sig_empirical.parameters.keys())
    ), f"signature drift: protocol={sig_protocol}, empirical={sig_empirical}"
