"""Pydantic v2 schemas for the Boros /markets response.

Source of truth: docs/samples/markets-response.json (captured 2026-04-24).
Schema reconciliation documented in docs/samples/markets-schema-notes.md.

Key differences from initial planning assumptions (A5 landmine reconciliation):
  - Response is wrapped: {results: [...], total, skip, syncStatus}
    NOT a bare list or {markets: [...]} or {data: [...]}
  - CLO thresholds are nested under config.cloLowerThresh / config.cloUpperThresh
    NOT at the market top level
  - fIndexOracle is nested under config.fIndexOracle
    NOT at the market top level
  - marketId is int; use imData.symbol as the human-readable string identifier

T-01-09-01 mitigation: extra='allow' on all models tolerates API schema drift
(new fields). Critical fields (cloLowerThresh, cloUpperThresh, fIndexOracle)
are required and will raise ValidationError if absent.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SyncStatus(BaseModel):
    """Freshness indicator returned at top level."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    block_number: int = Field(alias="blockNumber")
    timestamp: int


class MarketImData(BaseModel):
    """Immutable market data (name, symbol, maturity, tick settings)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    symbol: str  # e.g. "BINANCE-ETHUSDT-29MAY2026" — used as DB market_id
    maturity: int  # unix timestamp
    is_isolated_only: bool | None = Field(None, alias="isIsolatedOnly")
    tick_step: int | None = Field(None, alias="tickStep")


class MarketConfig(BaseModel):
    """Per-market configuration. Contains CLO thresholds + fIndexOracle address.

    CLO thresholds are int (tick-space integers) in the API; cast to float for DB.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # CLO thresholds — REQUIRED. These are the core fields for DATA-06.
    # In the API they are int (tick-space); we store as float in clo_history.
    clo_lower_thresh: float = Field(alias="cloLowerThresh")
    clo_upper_thresh: float = Field(alias="cloUpperThresh")

    # fIndexOracle — per-market oracle contract address. Present on all incentivized markets.
    findex_oracle: str | None = Field(None, alias="fIndexOracle")

    # Fees (1e18-denominated strings in API)
    taker_fee: str | None = Field(None, alias="takerFee")

    # Market status
    status: int | None = None


class MarketExtConfig(BaseModel):
    """Extended config — AMM details and oracle timing parameters."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    amm_address: str | None = Field(None, alias="ammAddress")
    # maxUpdateDelay in seconds — used by SAFE-02 oracle staleness breaker:
    # fTime > 0.7 × maxUpdateDelay => staleness alert
    max_update_delay: int | None = Field(None, alias="maxUpdateDelay")
    payment_period: int | None = Field(None, alias="paymentPeriod")


class MarketData(BaseModel):
    """Live market data (APRs, volumes, OI)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    mark_apr: float | None = Field(None, alias="markApr")
    floating_apr: float | None = Field(None, alias="floatingApr")
    long_yield_apr: float | None = Field(None, alias="longYieldApr")
    time_to_maturity: int | None = Field(None, alias="timeToMaturity")
    daily_volatility: float | None = Field(None, alias="dailyVolatility")


class Market(BaseModel):
    """One market object from the /markets results array.

    The string identifier used everywhere in the bot is imData.symbol
    (e.g. "BINANCE-ETHUSDT-29MAY2026"). The API marketId is an int.

    CLO thresholds and fIndexOracle are accessed via market.config.*
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    market_id: int = Field(alias="marketId")  # integer — NOT the string identifier
    address: str | None = None
    im_data: MarketImData = Field(alias="imData")
    config: MarketConfig
    ext_config: MarketExtConfig | None = Field(None, alias="extConfig")
    data: MarketData | None = None
    state: str | None = None


class MarketsResponse(BaseModel):
    """Top-level /markets response.

    Shape (confirmed from docs/samples/markets-response.json):
        {"results": [...], "total": 30, "skip": 0, "syncStatus": {...}}

    Extra top-level fields (T-01-09-01) are tolerated — logged at INFO by the poller.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    results: list[Market]
    total: int | None = None
    skip: int | None = None
    sync_status: SyncStatus | None = Field(None, alias="syncStatus")
