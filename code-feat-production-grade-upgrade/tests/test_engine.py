import pytest
import asyncio
import sys
import os

# The project root is expected to be in the python path when running pytest.
# This can be achieved by running `pytest` from the root, or by configuring pytest.
from src.engine import ArbitrageEngine

# --- Mock Objects for Testing ---

class MockProvider:
    """A mock provider that returns predefined ticker data."""
    def __init__(self, name: str, ticker_data: dict):
        self.name = name
        self._ticker_data = ticker_data

    async def get_ticker(self, symbol: str):
        # Simulate a small delay
        await asyncio.sleep(0.01)
        # Return the predefined ticker data for the given symbol
        return self._ticker_data.get(symbol)

# --- Test Cases ---

@pytest.mark.asyncio
async def test_find_opportunities_calculates_profit_correctly():
    """
    Tests if the ArbitrageEngine correctly identifies a profitable opportunity
    and calculates the net profit after fees.
    """
    # 1. Setup Mock Data and Config
    mock_providers = [
        MockProvider(
            name="ExchangeA",
            ticker_data={
                "BTC/USDT": {"ask": 50000.0, "bid": 49990.0, "provider_name": "ExchangeA"}
            }
        ),
        MockProvider(
            name="ExchangeB",
            ticker_data={
                "BTC/USDT": {"ask": 50600.0, "bid": 50500.0, "provider_name": "ExchangeB"}
            }
        )
    ]

    mock_config = {
        'threshold': 0.1, # 0.1%
        'fees': {
            'exchangea': { # lowercase name
                'taker': 0.001,
                'withdrawal_fees': {'BTC': 0.0001}
            },
            'exchangeb': {
                'taker': 0.001,
                'withdrawal_fees': {}
            }
        }
    }

    # 2. Instantiate the Engine
    engine = ArbitrageEngine(providers=mock_providers, config=mock_config)

    # 3. Run the method to be tested
    opportunities = await engine.find_opportunities(symbols=["BTC/USDT"])

    # 4. Assert the results
    assert len(opportunities) == 1

    op = opportunities[0]
    assert op['symbol'] == 'BTC/USDT'
    assert op['buy_at'] == 'ExchangeA'
    assert op['sell_at'] == 'ExchangeB'
    assert op['buy_price'] == 50000.0
    assert op['sell_price'] == 50500.0

    # Let's verify the profit calculation by hand:
    # Buy Price (Ask at A): 50000.0
    # Sell Price (Bid at B): 50500.0
    #
    # Cost to buy 1 BTC at Exchange A:
    #   Initial Cost = 50000.0
    #   Taker Fee (0.1%) = 50000.0 * 0.001 = 50.0
    #   Total Cost = 50000.0 + 50.0 = 50050.0
    #
    # Revenue from selling 1 BTC at Exchange B:
    #   Initial Revenue = 50500.0
    #   Taker Fee (0.1%) = 50500.0 * 0.001 = 50.5
    #   Net Revenue = 50500.0 - 50.5 = 50449.5
    #
    # Withdrawal Fee from Exchange A (0.0001 BTC):
    #   Fee in USD = 0.0001 BTC * 50000.0 USD/BTC = 5.0
    #
    # Net Profit:
    #   Net Revenue - Total Cost - Withdrawal Fee
    #   50449.5 - 50050.0 - 5.0 = 394.5
    #
    # Profit Percentage:
    #   (394.5 / 50050.0) * 100 = ~0.788%

    assert op['net_profit_usd'] == pytest.approx(394.5)
    assert op['profit_percentage'] == pytest.approx(0.7882, abs=1e-4)


@pytest.mark.asyncio
async def test_find_opportunities_no_profit():
    """
    Tests if the engine correctly finds no opportunities when the
    spread is negative after fees.
    """
    mock_providers = [
        MockProvider(name="ExchangeA", ticker_data={"BTC/USDT": {"ask": 50000.0, "bid": 49990.0, "provider_name": "ExchangeA"}}),
        MockProvider(name="ExchangeB", ticker_data={"BTC/USDT": {"ask": 50050.0, "bid": 50010.0, "provider_name": "ExchangeB"}})
    ]
    mock_config = {'threshold': 0.1, 'fees': {}} # No fees for simplicity

    engine = ArbitrageEngine(providers=mock_providers, config=mock_config)
    opportunities = await engine.find_opportunities(symbols=["BTC/USDT"])

    assert len(opportunities) == 0
