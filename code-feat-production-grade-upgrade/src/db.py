import aiosqlite
import asyncio
import os
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd

class DatabaseManager:
    """
    Manages the connection to a SQLite database and handles all data
    storage and retrieval operations asynchronously using aiosqlite.
    This class is designed to be used as an async context manager.
    """
    def __init__(self, db_path: str):
        if not db_path:
            raise ValueError("Database path is required.")
        self.db_path = db_path
        self._conn = None

    async def __aenter__(self):
        """Establishes the database connection."""
        # Ensure the directory for the database file exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        try:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            print(f"Successfully connected to SQLite database at {self.db_path}")
            return self
        except Exception as e:
            print(f"Error: Could not connect to the SQLite database. {e}")
            self._conn = None
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensures the database connection is closed."""
        if self._conn:
            await self._conn.close()
            print("SQLite database connection closed.")

    async def init_db(self):
        """
        Initializes the database by creating the necessary tables and indexes.
        This method is idempotent.
        """
        if not self._conn:
            raise ConnectionError("Database is not connected.")

        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_data (
            timestamp TEXT NOT NULL,
            provider_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            price REAL,
            bid REAL,
            ask REAL,
            volume REAL
        );
        """)
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticker_data_timestamp ON ticker_data (timestamp DESC);"
        )
        await self._conn.commit()
        print("Database initialization complete.")

    async def save_ticker_data(self, data: List[Dict[str, Any]]):
        """
        Saves a batch of ticker data records to the database using executemany.
        """
        if not self._conn:
            raise ConnectionError("Database is not connected.")
        if not data:
            return

        records_to_insert = [
            (
                d.get('timestamp').isoformat() if isinstance(d.get('timestamp'), datetime) else d.get('timestamp', datetime.utcnow().isoformat()),
                d.get('provider_name'),
                d.get('symbol'),
                d.get('price'),
                d.get('bid'),
                d.get('ask'),
                d.get('volume')
            ) for d in data
        ]

        await self._conn.executemany(
            "INSERT INTO ticker_data (timestamp, provider_name, symbol, price, bid, ask, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            records_to_insert
        )
        await self._conn.commit()
        print(f"Successfully saved {len(records_to_insert)} records to the database.")

    async def query_historical_data(self, symbol: str, start_time: datetime, end_time: datetime) -> pd.DataFrame:
        """
        Queries historical data for a given symbol and time range.
        """
        if not self._conn:
            raise ConnectionError("Database is not connected.")

        start_str = start_time.isoformat()
        end_str = end_time.isoformat()

        query = "SELECT * FROM ticker_data WHERE symbol = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp ASC;"
        async with self._conn.execute(query, (symbol, start_str, end_str)) as cursor:
            records = await cursor.fetchall()

        return pd.DataFrame([dict(row) for row in records]) if records else pd.DataFrame()
