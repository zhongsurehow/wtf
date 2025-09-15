import asyncio
import itertools
from typing import List, Dict, Any, TypedDict

from .providers.base import BaseProvider

# --- Constants for default values ---
DEFAULT_PROFIT_THRESHOLD_PERCENT = 0.1
DEFAULT_TAKER_FEE = 0.002
DEFAULT_WITHDRAWAL_FEE = 0.0

class Opportunity(TypedDict):
    """A dictionary representing a single arbitrage opportunity."""
    id: str
    symbol: str
    buy_at: str
    sell_at: str
    buy_price: float
    sell_price: float
    gross_profit_usd: float
    total_fees_usd: float
    net_profit_usd: float
    profit_percentage: float

class ArbitrageEngine:
    """
    Analyzes real-time data from multiple providers to find arbitrage opportunities.
    """
    def __init__(self, providers: List[BaseProvider], config: Dict[str, Any]):
        """
        Initializes the engine with data providers and configuration.

        Args:
            providers: A list of instantiated provider objects.
            config: A dictionary containing 'fees' and 'threshold' settings.
        """
        self.providers = providers
        self.fees_config = config.get('fees', {})
        # Convert profit threshold from percentage to a decimal
        self.profit_threshold = config.get('threshold', DEFAULT_PROFIT_THRESHOLD_PERCENT)

    async def find_opportunities(self, symbols: List[str]) -> List[Opportunity]:
        """
        Compares prices across all providers for given symbols and identifies
        potential arbitrage opportunities after accounting for fees.

        The fee model assumes the following steps for a trade:
        1. Buy 1 unit of the base asset on the buy_exchange (e.g., 1 BTC).
        2. Pay the taker fee for this purchase.
        3. Withdraw the asset, incurring a flat withdrawal fee in the base asset.
        4. Deposit on the sell_exchange (deposits are assumed to be free).
        5. Sell the asset on the sell_exchange.
        6. Pay the taker fee for this sale.

        Args:
            symbols: A list of symbols to check for arbitrage (e.g., ['BTC/USDT']).

        Returns:
            A list of Opportunity dictionaries, each representing a profitable trade.
        """
        all_opportunities: List[Opportunity] = []
        for symbol in symbols:
            tasks = [provider.get_ticker(symbol) for provider in self.providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_tickers = []
            for i, res in enumerate(results):
                if isinstance(res, dict) and 'error' not in res and res.get('ask') and res.get('bid'):
                    res['provider_name'] = self.providers[i].name
                    valid_tickers.append(res)

            if len(valid_tickers) < 2:
                continue

            for buy_ticker, sell_ticker in itertools.permutations(valid_tickers, 2):
                buy_provider_name = buy_ticker['provider_name']
                sell_provider_name = sell_ticker['provider_name']
                buy_price = float(buy_ticker['ask'])
                sell_price = float(sell_ticker['bid'])

                if buy_price >= sell_price:
                    continue

                default_fees = self.fees_config.get('default', {})
                buy_fees = self.fees_config.get(buy_provider_name.lower(), default_fees)
                sell_fees = self.fees_config.get(sell_provider_name.lower(), default_fees)

                buy_taker_fee = buy_fees.get('taker', DEFAULT_TAKER_FEE)
                sell_taker_fee = sell_fees.get('taker', DEFAULT_TAKER_FEE)

                base_asset = symbol.split('/')[0]
                withdrawal_fees_map = buy_fees.get('withdrawal_fees', {})
                withdrawal_fee_asset = withdrawal_fees_map.get(base_asset, DEFAULT_WITHDRAWAL_FEE)

                # --- Fee Calculation ---
                initial_cost_usd = buy_price
                buy_fee_usd = initial_cost_usd * buy_taker_fee
                total_cost_usd = initial_cost_usd + buy_fee_usd

                revenue_usd = sell_price
                sell_fee_usd = revenue_usd * sell_taker_fee
                withdrawal_fee_usd = withdrawal_fee_asset * buy_price # Estimate value at time of purchase
                net_revenue_usd = revenue_usd - sell_fee_usd

                net_profit_usd = net_revenue_usd - total_cost_usd - withdrawal_fee_usd

                if net_profit_usd <= 0:
                    continue

                profit_percentage = (net_profit_usd / total_cost_usd) * 100

                if profit_percentage > self.profit_threshold:
                    gross_profit_usd = sell_price - buy_price
                    total_fees_usd = buy_fee_usd + sell_fee_usd + withdrawal_fee_usd

                    opportunity: Opportunity = {
                        'id': f"{symbol}-{buy_provider_name}-{sell_provider_name}",
                        'symbol': symbol,
                        'buy_at': buy_provider_name,
                        'sell_at': sell_provider_name,
                        'buy_price': round(buy_price, 4),
                        'sell_price': round(sell_price, 4),
                        'gross_profit_usd': round(gross_profit_usd, 4),
                        'total_fees_usd': round(total_fees_usd, 4),
                        'net_profit_usd': round(net_profit_usd, 4),
                        'profit_percentage': round(profit_percentage, 4),
                    }
                    all_opportunities.append(opportunity)

        return all_opportunities
