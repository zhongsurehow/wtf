import pytest
import pandas as pd
from unittest.mock import AsyncMock

from src.providers.cex import CEXProvider

# Sample OHLCV data that the mock exchange will return
SAMPLE_OHLCV = [
    [1672531200000, 16500.0, 16600.0, 16400.0, 16550.0, 1000.0],
    [1672617600000, 16550.0, 16700.0, 16500.0, 16650.0, 1200.0],
]
SAMPLE_DF = pd.DataFrame(SAMPLE_OHLCV, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

@pytest.fixture
def mock_exchange():
    """Fixture to create a mock exchange object with a fetch_ohlcv method."""
    exchange = AsyncMock()
    exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)
    return exchange

@pytest.fixture
def provider_with_mock_exchange(mock_exchange):
    """Fixture to create a CEXProvider with a mocked internal exchange."""
    # In a real test suite, you might use patching, but direct injection is simpler here
    provider = CEXProvider(name="TestEx", force_mock=True)
    provider.exchange = mock_exchange  # Inject the mock
    return provider

@pytest.mark.asyncio
async def test_get_historical_data_cache_miss(provider_with_mock_exchange, tmp_path, monkeypatch):
    """
    Test the 'cache miss' scenario:
    1. No cache file exists.
    2. Data is fetched from the exchange.
    3. A new cache file is created.
    """
    # --- Arrange ---
    # Change the current directory to the temporary directory for this test
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir() # The provider expects the 'data' directory to exist

    # --- Act ---
    result_data = await provider_with_mock_exchange.get_historical_data("BTC/USDT", "1d", 2)

    # --- Assert ---
    # 1. Assert that the exchange was called
    provider_with_mock_exchange.exchange.fetch_ohlcv.assert_called_once_with("BTC/USDT", "1d", limit=2)

    # 2. Assert that the returned data is correct
    assert len(result_data) == 2
    assert result_data[0]['close'] == 16550.0

    # 3. Assert that the cache file was created and contains the correct data
    cache_file = data_dir / "TESTEX_BTC_USDT_1d.csv"
    assert cache_file.exists()
    df_from_cache = pd.read_csv(cache_file)
    assert df_from_cache.shape[0] == 2
    assert df_from_cache['close'].iloc[1] == 16650.0

@pytest.mark.asyncio
async def test_get_historical_data_cache_hit(provider_with_mock_exchange, tmp_path, monkeypatch):
    """
    Test the 'cache hit' scenario:
    1. A cache file already exists.
    2. Data is loaded from the file.
    3. The exchange is NOT called.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create a dummy cache file
    cache_file = data_dir / "TESTEX_BTC_USDT_1d.csv"
    dummy_data = {
        'timestamp': [1672531200000], 'open': [100], 'high': [200],
        'low': [50], 'close': [150], 'volume': [99]
    }
    pd.DataFrame(dummy_data).to_csv(cache_file, index=False)

    # --- Act ---
    result_data = await provider_with_mock_exchange.get_historical_data("BTC/USDT", "1d", 1)

    # --- Assert ---
    # 1. Assert that the exchange was NOT called
    provider_with_mock_exchange.exchange.fetch_ohlcv.assert_not_called()

    # 2. Assert that the data returned is from the cache file
    assert len(result_data) == 1
    assert result_data[0]['close'] == 150
    assert result_data[0]['volume'] == 99

@pytest.mark.asyncio
async def test_get_historical_data_invalid_cache(provider_with_mock_exchange, tmp_path, monkeypatch):
    """
    Test the 'invalid cache' scenario:
    1. A corrupted cache file exists.
    2. The provider ignores it and fetches from the exchange.
    3. The corrupted file is overwritten with good data.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create a corrupted cache file (e.g., missing columns)
    cache_file = data_dir / "TESTEX_BTC_USDT_1d.csv"
    with open(cache_file, "w") as f:
        f.write("timestamp,open,close\n")
        f.write("1672531200000,100,150\n")

    # --- Act ---
    result_data = await provider_with_mock_exchange.get_historical_data("BTC/USDT", "1d", 2)

    # --- Assert ---
    # 1. Assert that the exchange WAS called, because the cache was invalid
    provider_with_mock_exchange.exchange.fetch_ohlcv.assert_called_once_with("BTC/USDT", "1d", limit=2)

    # 2. Assert that the data returned is the fresh data from the exchange
    assert len(result_data) == 2
    assert result_data[1]['close'] == 16650.0 # From SAMPLE_OHLCV

    # 3. Assert that the bad cache file was overwritten with good data
    df_from_cache = pd.read_csv(cache_file)
    assert df_from_cache.shape[0] == 2
    assert 'high' in df_from_cache.columns # Check that the columns are now correct
    assert df_from_cache['volume'].iloc[0] == 1000.0
