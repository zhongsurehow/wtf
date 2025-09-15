import httpx
import time
import logging
from typing import Dict, Any, List

from .base import BaseProvider

logger = logging.getLogger(__name__)

THORCHAIN_API_URL = "https://thornode.ninerealms.com/thorchain/quote/swap"
# Thorchain amounts are specified in 1e8 format
AMOUNT_DECIMALS = 8

class BridgeProvider(BaseProvider):
    """
    Connects to the Thorchain API to get cross-chain swap quotes.
    """
    def __init__(self, name: str = "Thorchain"):
        super().__init__(name)
        # The API URL is consistent for Thorchain, so we can hardcode it.
        self.api_url = THORCHAIN_API_URL
        self.client = httpx.AsyncClient()

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Gets a price quote from the Thorchain API. The symbol must be in the
        format 'CHAIN.ASSET/CHAIN.ASSET', e.g., 'BTC.BTC/ETH.ETH'.
        """
        try:
            from_asset, to_asset = symbol.split('/')

            # We fetch the price for 1 unit of the from_asset
            amount_in_1e8 = 1 * (10**AMOUNT_DECIMALS)

            params = {
                "from_asset": from_asset,
                "to_asset": to_asset,
                "amount": amount_in_1e8,
            }

            response = await self.client.get(self.api_url, params=params)
            response.raise_for_status()  # Raise an exception for bad status codes

            data = response.json()

            # Based on documentation, the key should be 'expected_amount_out'.
            # If this fails, the error log will show the actual JSON response.
            expected_out = data.get("expected_amount_out")
            if not expected_out:
                raise KeyError("'expected_amount_out' not found in response. Check API docs.")

            # Adjust for 1e8 decimals
            price = int(expected_out) / (10**AMOUNT_DECIMALS)

            # Extract total fees in the 'to_asset' for net price calculation
            total_fees_1e8 = int(data.get("fees", {}).get("total", 0))
            total_fees = total_fees_1e8 / (10**AMOUNT_DECIMALS)

            net_price = price - total_fees

            return {
                'symbol': symbol,
                'provider': self.name,
                'last': net_price, # The net amount you receive is the effective price
                'bid': net_price * 0.9998, # Approximate bid/ask for consistency
                'ask': net_price * 1.0002,
                'timestamp': int(time.time() * 1000),
            }

        except httpx.RequestError as e:
            error_message = f"Request failed: {e.__class__.__name__}"
            logger.error(f"Error fetching from {self.name} for {symbol}: {error_message}", exc_info=True)
            return {'symbol': symbol, 'provider': self.name, 'error': error_message}
        except (KeyError, ValueError) as e:
            error_message = f"Failed to parse response: {e}"
            logger.error(f"Error fetching from {self.name} for {symbol}: {error_message}", exc_info=True)
            return {'symbol': symbol, 'provider': self.name, 'error': error_message}
        except Exception as e:
            logger.error(f"An unexpected error occurred in {self.name} for {symbol}: {e}", exc_info=True)
            return {'symbol': symbol, 'provider': self.name, 'error': str(e)}


    async def get_order_book(self, symbol: str, limit: int = 25) -> Dict[str, List]:
        """
        Bridges do not have order books. This method will return empty data.
        """
        return {'bids': [], 'asks': []}

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """
        Historical data is not applicable for bridge quotes.
        """
        logger.info(f"Historical data not applicable for Bridge provider '{self.name}'.")
        return []

    async def close(self):
        """Closes the httpx client session."""
        await self.client.aclose()
