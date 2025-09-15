import asyncio
import json
import time
import logging
from typing import Dict, Any, List

from web3 import Web3, AsyncHTTPProvider

from .base import BaseProvider

logger = logging.getLogger(__name__)

# --- Minimal ABIs and Contract Details ---
# Using minimal ABIs is more robust than fetching large files.

UNISWAP_V3_FACTORY_ADDRESS = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
FACTORY_ABI = json.loads("""
[
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]
""")

POOL_ABI = json.loads("""
[
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]
""")

# A small, hardcoded registry for popular tokens on Ethereum Mainnet
TOKEN_REGISTRY = {
    "WETH": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
    "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
    "WBTC": {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
}

class DEXProvider(BaseProvider):
    """
    Connects to Uniswap V3 on an EVM-compatible chain to fetch prices.
    """
    def __init__(self, name: str, rpc_url: str, chain: str = "ethereum"):
        super().__init__(name)
        if not rpc_url:
            raise ValueError("RPC URL is required for DEXProvider")
        from web3 import HTTPProvider
        self.w3 = Web3(HTTPProvider(rpc_url))
        self.chain = chain
        self.factory = self.w3.eth.contract(
            address=UNISWAP_V3_FACTORY_ADDRESS, abi=FACTORY_ABI
        )

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Estimates the current price from a Uniswap V3 liquidity pool.
        Symbol should be in the format 'TOKENA/TOKENB', e.g., 'WETH/USDC'.
        """
        try:
            token_a_sym, token_b_sym = symbol.split('/')
            token_a = TOKEN_REGISTRY.get(token_a_sym)
            token_b = TOKEN_REGISTRY.get(token_b_sym)

            if not token_a or not token_b:
                raise ValueError(f"One or both tokens in '{symbol}' not in registry.")

            # Assume the most common fee tier (0.3%) for simplicity
            fee = 3000

            pool_address = self.factory.functions.getPool(
                token_a["address"], token_b["address"], fee
            ).call()

            if pool_address == "0x0000000000000000000000000000000000000000":
                raise ValueError(f"Pool for {symbol} with fee {fee} not found.")

            pool_contract = self.w3.eth.contract(address=pool_address, abi=POOL_ABI)

            # Ensure correct ordering for price calculation
            pool_token0_address = pool_contract.functions.token0().call()

            if pool_token0_address.lower() == token_a["address"].lower():
                decimals0, decimals1 = token_a["decimals"], token_b["decimals"]
            else:
                decimals0, decimals1 = token_b["decimals"], token_a["decimals"]

            slot0 = pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]

            # Price calculation
            price = (sqrt_price_x96 / 2**96) ** 2
            adjusted_price = price * (10**decimals1 / 10**decimals0)

            return {
                'symbol': symbol,
                'provider': self.name,
                'last': adjusted_price,
                'bid': adjusted_price * 0.9995,  # Approximate bid/ask
                'ask': adjusted_price * 1.0005,
                'timestamp': int(time.time() * 1000),
            }

        except Exception as e:
            logger.error(f"Error fetching from {self.name} for {symbol}: {e}", exc_info=True)
            return {
                'symbol': symbol,
                'provider': self.name,
                'error': str(e),
            }

    async def get_order_book(self, symbol: str, limit: int = 25) -> Dict[str, List]:
        """
        DEXs don't have traditional order books. This could be enhanced later
        to show liquidity depth, but for now, it returns empty data.
        """
        return {'bids': [], 'asks': []}

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """
        Fetching historical OHLCV for DEXs is complex and provider-specific
        (e.g., requires querying historical logs or using a data service like TheGraph).
        This is a placeholder for future implementation.
        """
        logger.info(f"Historical data not implemented for DEX provider '{self.name}'.")
        return []

    async def close(self):
        # web3.py with AsyncHTTPProvider may have an underlying session
        # that's good practice to close if the provider exposes it.
        if hasattr(self.w3.provider, 'client'):
             await self.w3.provider.client.aclose()
