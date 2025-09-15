import asyncio
import random
import time
import logging
import os
import pandas as pd
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# --- Global Cache for Mock Data ---
_mock_data_cache = None

def _get_mock_historical_data():
    """Loads mock historical data from CSV, caching it in memory after the first read."""
    global _mock_data_cache
    if _mock_data_cache is not None:
        return _mock_data_cache

    try:
        _mock_data_cache = pd.read_csv('mock_btc_usdt_daily.csv')
        logger.info("Successfully loaded and cached mock historical data.")
    except FileNotFoundError:
        _mock_data_cache = None
        logger.warning("Mock historical data file not found. Mocking will rely on random data.")
    return _mock_data_cache


# --- Mock CCXT.PRO Implementation ---
class MockExchange:
    """Mocks a single ccxt.pro exchange connection."""
    def __init__(self, *args, **kwargs):
        """Accept any args to be robust, ignore them."""
        self._historical_data = _get_mock_historical_data()
        self._data_index = 0
        self._last_price = 50000 + random.uniform(-100, 100)


    async def watch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Simulates waiting for and receiving a single ticker update."""
        await asyncio.sleep(random.uniform(0.1, 0.5)) # Simulate network latency

        if self._historical_data is not None and symbol == 'BTC/USDT':
            if self._data_index >= len(self._historical_data):
                self._data_index = 0 # Loop back

            record = self._historical_data.iloc[self._data_index]
            self._data_index += 1
            price = record['close']

            return {
                'symbol': symbol,
                'timestamp': int(record['unix']),
                'datetime': record['date'],
                'high': record['high'],
                'low': record['low'],
                'bid': price * 0.9998,
                'ask': price * 1.0002,
                'last': price,
                'baseVolume': record['Volume BTC'],
                'info': {},
            }

        self._last_price *= random.uniform(0.999, 1.001)
        bid = self._last_price * 0.9998
        ask = self._last_price * 1.0002
        return {
            'symbol': symbol,
            'timestamp': int(time.time() * 1000),
            'datetime': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'high': self._last_price * 1.02,
            'low': self._last_price * 0.98,
            'bid': bid,
            'ask': ask,
            'last': self._last_price,
            'baseVolume': random.uniform(1000, 5000),
            'info': {},
        }

    async def watch_order_book(self, symbol: str, limit: int = 25) -> Dict[str, List]:
        """Simulates waiting for and receiving a single order book update."""
        await asyncio.sleep(random.uniform(0.1, 0.5))
        price = self._last_price
        if self._historical_data is not None and symbol == 'BTC/USDT':
            current_index = self._data_index - 1 if self._data_index > 0 else 0
            if current_index < len(self._historical_data):
                price = self._historical_data.iloc[current_index]['close']

        bids = sorted([[price - random.uniform(0, 10), random.uniform(0.1, 5)] for _ in range(limit)], key=lambda x: x[0], reverse=True)
        asks = sorted([[price + random.uniform(0, 10), random.uniform(0.1, 5)] for _ in range(limit)], key=lambda x: x[0])
        return {
            'bids': bids,
            'asks': asks,
            'symbol': symbol,
            'timestamp': int(time.time() * 1000),
            'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        }

    async def close(self):
        """Simulates closing the connection."""
        await asyncio.sleep(0.01)

    def fetch_deposit_withdraw_fees(self, codes=None, params={}):
        """Simulates fetching deposit and withdrawal fees for multiple assets."""
        mock_fees = {
            'USDT': { 'withdraw': { 'TRX': {'fee': 1.0, 'percentage': False}, 'ERC20': {'fee': 15.0, 'percentage': False}, 'SOL': {'fee': 0.5, 'percentage': False}, 'Polygon': {'fee': 0.8, 'percentage': False} } },
            'USDC': { 'withdraw': { 'TRX': {'fee': 1.2, 'percentage': False}, 'ERC20': {'fee': 12.0, 'percentage': False}, 'Arbitrum': {'fee': 0.7, 'percentage': False} } },
            'BTC': { 'withdraw': { 'Bitcoin': {'fee': 0.0002, 'percentage': False}, 'Lightning': {'fee': 0.0, 'percentage': False}, 'BSC': {'fee': 0.000005, 'percentage': False} } }
        }
        asset = (codes[0] if codes else "USDT").upper()
        if asset not in mock_fees: return {}

        asset_fees = mock_fees[asset]
        for net in asset_fees['withdraw']: # Add some randomness
            asset_fees['withdraw'][net]['fee'] *= random.uniform(0.9, 1.1)

        response = { asset: { 'info': {'coin': asset}, 'networks': { 'deposit': {net: {'fee': 0.0, 'percentage': False} for net in asset_fees['withdraw']}, 'withdraw': asset_fees['withdraw'] } } }
        if random.random() < 0.3:
            if response[asset]['networks']['withdraw']:
                net_to_remove = random.choice(list(response[asset]['networks']['withdraw'].keys()))
                del response[asset]['networks']['withdraw'][net_to_remove]
                del response[asset]['networks']['deposit'][net_to_remove]
        return response

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1d', limit: int = 100, params={}) -> List[List]:
        """Simulates fetching historical OHLCV data."""
        await asyncio.sleep(0.1)
        if self._historical_data is not None and symbol == 'BTC/USDT' and timeframe == '1d':
            df = self._historical_data.copy()
            df['unix'] = df['unix'].astype(int)
            ohlcv = df[['unix', 'open', 'high', 'low', 'close', 'Volume BTC']].values.tolist()
            return ohlcv[-limit:]

        timestamp = int(time.time() * 1000) - limit * 86400000
        price = 50000
        ohlcv_data = []
        for _ in range(limit):
            open_price, high_price, low_price, close_price = price * random.uniform(0.99, 1.01), price * random.uniform(1.0, 1.02), price * random.uniform(0.98, 1.0), random.uniform(price * 0.98, price * 1.02)
            volume = random.uniform(100, 1000)
            ohlcv_data.append([timestamp, open_price, high_price, low_price, close_price, volume])
            price = close_price
            timestamp += 86400000
        return ohlcv_data

class MockCCXTPro:
    """Mocks the ccxtpro library by dynamically creating MockExchange instances."""
    def __getattr__(self, name: str):
        return MockExchange

try:
    import ccxt.pro as ccxtpro
    IS_MOCK = False
except ImportError:
    logger.warning("ccxt.pro not found. Using a mock implementation for CEXProvider.")
    IS_MOCK = True
    ccxtpro = MockCCXTPro()

from .base import BaseProvider

class CEXProvider(BaseProvider):
    """
    Connects to Centralized Exchanges (CEX) using ccxt.pro (or a mock version)
    to get real-time data via WebSockets.
    """
    def __init__(self, name: str, config: Dict = None, force_mock: bool = False):
        super().__init__(name)
        self.exchange_id = name.lower()
        self.is_mock = force_mock or IS_MOCK
        if self.is_mock:
            self.exchange = MockExchange()
            return

        try:
            exchange_class = getattr(ccxtpro, self.exchange_id)
            api_keys = config.get('api_keys', {}).get(self.exchange_id, {})
            self.exchange = exchange_class(api_keys if api_keys else {})
        except (AttributeError, TypeError) as e:
            raise ValueError(f"Exchange '{self.exchange_id}' is not supported by ccxt.pro or API config is invalid. Error: {e}")

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetches the next ticker data update from the WebSocket stream."""
        return await self.exchange.watch_ticker(symbol)

    async def get_order_book(self, symbol: str, limit: int = 25) -> Dict[str, List]:
        """Fetches the next order book data update from the WebSocket stream."""
        return await self.exchange.watch_order_book(symbol, limit)

    async def close(self):
        """Closes the underlying ccxt.pro exchange connection."""
        await self.exchange.close()

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """
        Fetches historical OHLCV data, implementing a cache-first strategy.
        """
        safe_symbol = symbol.replace('/', '_')
        cache_filename = f"{self.name.upper()}_{safe_symbol}_{timeframe}.csv"
        cache_filepath = f"data/{cache_filename}"

        try:
            df = pd.read_csv(cache_filepath)
            if {'timestamp', 'open', 'high', 'low', 'close', 'volume'}.issubset(df.columns):
                return df.tail(limit).to_dict('records')
        except (FileNotFoundError, Exception):
            pass

        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv: return []
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            os.makedirs(os.path.dirname(cache_filepath), exist_ok=True)
            df.to_csv(cache_filepath, index=False)
            return df.to_dict('records')
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol} from {self.name}: {e}")
            return []

    async def get_transfer_fees(self, asset: str) -> Dict[str, Any]:
        """
        Fetches deposit and withdrawal fee and network information for a specific asset.
        """
        try:
            loop = asyncio.get_running_loop()
            all_fees = await loop.run_in_executor(None, self.exchange.fetch_deposit_withdraw_fees, [asset])
            if asset in all_fees and 'networks' in all_fees[asset]:
                return {'asset': asset, **all_fees[asset]['networks']}
            return {'asset': asset, 'error': 'No fee info found for asset.'}
        except Exception as e:
            logger.error(f"Could not fetch transfer fees for {asset} from {self.name}: {e}")
            return {'asset': asset, 'error': str(e)}

    async def get_liquidity_within_percentage(self, symbol: str, percentage: float = 0.01) -> Dict[str, Any]:
        """
        Calculates the value of bids and asks within a given percentage of the mid-price.
        """
        try:
            order_book, ticker = await asyncio.gather(self.get_order_book(symbol), self.get_ticker(symbol))
            if 'error' in order_book or 'error' in ticker:
                return {'symbol': symbol, 'error': 'Failed to fetch order book or ticker.'}

            bid_price, ask_price = ticker.get('bid'), ticker.get('ask')
            if not bid_price or not ask_price:
                return {'symbol': symbol, 'error': 'Ticker missing bid/ask prices.'}

            mid_price = (bid_price + ask_price) / 2
            price_range = mid_price * percentage
            lower_bound, upper_bound = mid_price - price_range, mid_price + price_range

            bid_liquidity = sum(p * v for p, v in order_book.get('bids', []) if p >= lower_bound)
            ask_liquidity = sum(p * v for p, v in order_book.get('asks', []) if p <= upper_bound)

            return {'symbol': symbol, 'bid_liquidity_usd': bid_liquidity, 'ask_liquidity_usd': ask_liquidity, 'mid_price': mid_price}
        except Exception as e:
            logger.error(f"Could not calculate liquidity for {symbol} from {self.name}: {e}")
            return {'symbol': symbol, 'error': str(e)}
