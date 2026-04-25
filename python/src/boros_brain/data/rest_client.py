"""Shared httpx AsyncClient factory for Boros REST.

Used by:
  - /markets poller (DATA-06, plan 01-09)
  - E_liq poller (DATA-11, Wave 2)
  - Margin poller (DATA-13, Plan 04-02) — post_get_net_margin

Security note (T-01-09-04): /markets requires no auth. Wallet addresses for
per-account endpoints are a Phase 6 concern. structlog redaction (plan 01-06)
covers any future drift.

Error shape (Open API): {"errorCode": "...", "message": "...", "data": null}
"""

from __future__ import annotations

from typing import Any

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


class BorosRestClient:
    """Typed REST client wrapping httpx.AsyncClient for Boros API calls.

    Provides typed async methods for each endpoint the brain calls. The
    underlying httpx client is passed in (use make_boros_rest_client to build it).

    Each method raises BorosApiError on well-formed API errors and lets httpx
    exceptions propagate for transport-level failures (callers handle retry).
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get_markets(self) -> list[dict[str, Any]]:
        """GET /markets — returns the list of active market objects."""
        resp = await self._client.get("/markets")
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]

    async def post_get_net_margin(self, account_id: int) -> dict[str, Any]:
        """POST /accounts/get-net-margin — returns per-account margin data.

        SAFE-01 data source. Assumed response shape (verify in Plan 04-04):
          {"netMargin": <float, USD>, "maintenanceMargin": <float, USD>,
           "availableCollateral": <float, USD>}

        [[boros-rest-api-margin-endpoint]]: endpoint contract + assumed field shape
        """
        resp = await self._client.post(
            "/accounts/get-net-margin",
            json={"accountId": account_id},
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]
