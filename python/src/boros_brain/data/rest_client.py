"""Shared httpx AsyncClient factory for Boros REST.

Used by:
  - /markets poller (DATA-06, plan 01-09)
  - E_liq poller (DATA-11, Wave 2)

Security note (T-01-09-04): /markets requires no auth. Wallet addresses for
per-account endpoints are a Phase 6 concern. structlog redaction (plan 01-06)
covers any future drift.

Error shape (Open API): {"errorCode": "...", "message": "...", "data": null}
"""

from __future__ import annotations

import httpx
import structlog

from boros_brain.config.schema import BotConfig

log = structlog.get_logger(__name__)


class BorosApiError(RuntimeError):
    """Open-API-shape error: {errorCode, message, data}.

    Raised when the Boros REST API returns a well-formed error body.
    For transport-level errors (5xx, timeout), httpx exceptions propagate directly.
    """

    def __init__(self, *, status: int, error_code: str | None, message: str) -> None:
        super().__init__(f"BorosApiError[{status}]: {error_code}: {message}")
        self.status = status
        self.error_code = error_code
        self.message = message


def make_boros_rest_client(config: BotConfig, timeout_s: float = 10.0) -> httpx.AsyncClient:
    """Return an httpx.AsyncClient pre-configured with base_url + timeout.

    Usage:
        async with make_boros_rest_client(config) as http:
            resp = await http.get("/markets")
    """
    return httpx.AsyncClient(
        base_url=config.data.boros_rest_base,
        timeout=httpx.Timeout(timeout_s, connect=3.0),
        follow_redirects=False,
    )
