"""Tests for the Pydantic v2 /markets response schema (DATA-06).

Source of truth: docs/samples/markets-response.json (captured 2026-04-24).
All field names are verified against the REAL response, not planning assumptions.

See docs/samples/markets-schema-notes.md for the full reconciliation:
  - Response is {results: [...], total, skip, syncStatus} — NOT a bare list
  - CLO thresholds are nested under config.cloLowerThresh / config.cloUpperThresh
  - fIndexOracle is nested under config.fIndexOracle
  - marketId is int; imData.symbol is the human-readable string identifier
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

# Paths — parents[2] = repo root (python/tests → python → repo-root)
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_RESPONSE_PATH = REPO_ROOT / "docs" / "samples" / "markets-response.json"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "markets_response_fixture.json"


def test_markets_response_schema_parses_captured_sample() -> None:
    """MarketsResponse.model_validate_json must parse the real captured response
    without raising. Every market must have cloLowerThresh, cloUpperThresh, and
    a non-empty symbol. The contract address is unique per market.

    Note: imData.symbol is NOT guaranteed unique in the API — discovered that
    HYPERLIQUID-BTC-29MAY2026 appears twice with different marketId/address.
    Uniqueness is on `address` (contract address), not `symbol`.
    See docs/samples/markets-schema-notes.md for the full A5 reconciliation.
    """
    from boros_brain.data.poller.schemas import MarketsResponse

    raw = REAL_RESPONSE_PATH.read_bytes()
    response = MarketsResponse.model_validate_json(raw)

    assert len(response.results) > 0, "Response must have at least one market"

    addresses_seen: set[str] = set()
    for market in response.results:
        assert market.config.clo_lower_thresh is not None, f"Market missing cloLowerThresh: {market.im_data.symbol}"
        assert market.config.clo_upper_thresh is not None, f"Market missing cloUpperThresh: {market.im_data.symbol}"
        sym = market.im_data.symbol
        assert sym, "Every market must have a non-empty imData.symbol"
        # Address is the true unique identifier
        addr = market.address or ""
        assert addr not in addresses_seen, f"Duplicate address: {addr} on market {sym}"
        addresses_seen.add(addr)


def test_markets_response_schema_forbids_missing_critical_fields() -> None:
    """A market payload MISSING cloLowerThresh must raise ValidationError.
    A payload with an extra unknown top-level field must be allowed (extra='allow').
    """
    from boros_brain.data.poller.schemas import MarketsResponse

    # Load fixture and remove cloLowerThresh from the first market's config
    data = json.loads(FIXTURE_PATH.read_bytes())
    del data["results"][0]["config"]["cloLowerThresh"]

    with pytest.raises(ValidationError):
        MarketsResponse.model_validate(data)


def test_markets_response_schema_allows_extra_unknown_top_level_fields() -> None:
    """Extra unknown fields at the MarketsResponse top level must be tolerated
    (T-01-09-01: API schema drift — new fields added — should not break the poller).
    """
    from boros_brain.data.poller.schemas import MarketsResponse

    data = json.loads(FIXTURE_PATH.read_bytes())
    # Add an unknown field at the top level
    data["unexpectedNewField"] = "some_value"

    # Must NOT raise
    response = MarketsResponse.model_validate(data)
    assert len(response.results) == 2


def test_markets_response_schema_types_are_strict() -> None:
    """cloLowerThresh must reject a string value ('not a number') with ValidationError."""
    from boros_brain.data.poller.schemas import MarketsResponse

    data = json.loads(FIXTURE_PATH.read_bytes())
    # Replace cloLowerThresh with a non-numeric string
    data["results"][0]["config"]["cloLowerThresh"] = "not a number"

    with pytest.raises(ValidationError):
        MarketsResponse.model_validate(data)
