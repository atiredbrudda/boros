"""Shared AsyncWeb3 factory for Arbitrum RPC.

Consumed by:
  - INFRA-14 (chain_time) — eth_getBlockByNumber for chain-time drift monitoring.
  - DATA-07 (fIndexOracle reader, plan 01-09) — eth_call getLatestFIndex.

Security note (T-01-07-02): the RPC URL may contain an embedded API key.
`make_arbitrum_rpc` passes it directly to AsyncHTTPProvider — it is NEVER logged.
The structlog redaction processor (01-06) redacts any field matching /api[-_]?key/.
"""

from __future__ import annotations

from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider

from boros_brain.config.schema import BotConfig


async def make_arbitrum_rpc(config: BotConfig) -> AsyncWeb3:  # type: ignore[type-arg]
    """Return a shared AsyncWeb3 instance wired to the Arbitrum RPC endpoint.

    URL is read from config.data.rpc_url_arbitrum (Wave 0 canonical field name).
    The URL is NEVER logged — T-01-07-02 mitigation.
    """
    return AsyncWeb3(AsyncHTTPProvider(config.data.rpc_url_arbitrum))


async def get_latest_block_timestamp(w3: AsyncWeb3) -> int:  # type: ignore[type-arg]
    """Return eth.get_block('latest').timestamp as a plain int (unix seconds).

    Raises web3 exceptions on RPC failure — callers wrap in asyncio.wait_for.
    """
    block = await w3.eth.get_block("latest")
    return int(block["timestamp"])
