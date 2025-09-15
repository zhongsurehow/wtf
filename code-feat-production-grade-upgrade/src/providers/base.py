from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseProvider(ABC):
    """
    Abstract base class for all data providers (CEX, DEX, Bridge).
    Ensures a consistent interface for fetching data.
    """
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Asynchronously fetches ticker data for a single symbol.

        Args:
            symbol (str): The trading symbol (e.g., 'BTC/USDT').

        Returns:
            A dictionary containing ticker information (last, bid, ask, volume, etc.).
        """
        pass

    @abstractmethod
    async def get_order_book(self, symbol: str, limit: int = 25) -> Dict[str, List]:
        """
        Asynchronously fetches the order book for a single symbol.

        Args:
            symbol (str): The trading symbol.
            limit (int): The number of bids and asks to retrieve.

        Returns:
            A dictionary with 'bids' and 'asks' lists.
        """
        pass

    @abstractmethod
    async def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """
        Asynchronously fetches historical K-line (OHLCV) data.

        Args:
            symbol (str): The trading symbol.
            timeframe (str): The timeframe (e.g., '1d', '1h', '5m').
            limit (int): The number of data points to retrieve.

        Returns:
            A list of dictionaries, where each dict is an OHLCV candle.
        """
        pass

    async def close(self):
        """
        Cleanly close any open connections (e.g., WebSockets, HTTP sessions).
        This is crucial for resource management.
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"
