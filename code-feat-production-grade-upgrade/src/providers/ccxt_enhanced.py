import ccxt
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

class EnhancedCCXTProvider:
    """
    增强的CCXT提供者，支持更多免费交易所和优化的数据获取
    """
    
    # 免费交易所列表（不需要API密钥）
    FREE_EXCHANGES = {
        'binance': {
            'name': 'Binance',
            'has_public_api': True,
            'rate_limit': 1200,  # 每分钟请求限制
            'symbols': ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'okx': {
            'name': 'OKX',
            'has_public_api': True,
            'rate_limit': 600,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'OKB/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'bybit': {
            'name': 'Bybit',
            'has_public_api': True,
            'rate_limit': 600,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'BIT/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'kucoin': {
            'name': 'KuCoin',
            'has_public_api': True,
            'rate_limit': 1800,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'KCS/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'gate': {
            'name': 'Gate.io',
            'has_public_api': True,
            'rate_limit': 900,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'GT/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'mexc': {
            'name': 'MEXC',
            'has_public_api': True,
            'rate_limit': 1200,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'MX/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'bitget': {
            'name': 'Bitget',
            'has_public_api': True,
            'rate_limit': 600,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'BGB/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'coinex': {
            'name': 'CoinEx',
            'has_public_api': True,
            'rate_limit': 600,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'CET/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'huobi': {
            'name': 'Huobi',
            'has_public_api': True,
            'rate_limit': 600,
            'symbols': ['BTC/USDT', 'ETH/USDT', 'HT/USDT', 'ADA/USDT', 'SOL/USDT']
        },
        'kraken': {
            'name': 'Kraken',
            'has_public_api': True,
            'rate_limit': 60,  # 更严格的限制
            'symbols': ['BTC/USDT', 'ETH/USDT', 'ADA/USDT', 'SOL/USDT']
        }
    }
    
    def __init__(self):
        self.exchanges = {}
        self.last_request_time = {}
        self.request_counts = {}
        self._initialize_exchanges()
    
    def _initialize_exchanges(self):
        """初始化所有免费交易所"""
        for exchange_id, config in self.FREE_EXCHANGES.items():
            try:
                if hasattr(ccxt, exchange_id):
                    exchange_class = getattr(ccxt, exchange_id)
                    self.exchanges[exchange_id] = exchange_class({
                        'enableRateLimit': True,
                        'rateLimit': config['rate_limit'],
                        'timeout': 30000,
                        'sandbox': False
                    })
                    self.last_request_time[exchange_id] = 0
                    self.request_counts[exchange_id] = 0
                    logger.info(f"Initialized {config['name']} exchange")
                else:
                    logger.warning(f"Exchange {exchange_id} not available in ccxt")
            except Exception as e:
                logger.error(f"Failed to initialize {exchange_id}: {e}")
    
    def _check_rate_limit(self, exchange_id: str) -> bool:
        """检查速率限制"""
        if exchange_id not in self.FREE_EXCHANGES:
            return False
        
        current_time = time.time()
        config = self.FREE_EXCHANGES[exchange_id]
        
        # 重置每分钟的计数器
        if current_time - self.last_request_time[exchange_id] > 60:
            self.request_counts[exchange_id] = 0
            self.last_request_time[exchange_id] = current_time
        
        # 检查是否超过限制
        if self.request_counts[exchange_id] >= config['rate_limit'] / 60:  # 每秒限制
            return False
        
        self.request_counts[exchange_id] += 1
        return True
    
    async def get_ticker_data(self, exchange_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取单个交易所的ticker数据"""
        if exchange_id not in self.exchanges:
            return None
        
        if not self._check_rate_limit(exchange_id):
            logger.warning(f"Rate limit exceeded for {exchange_id}")
            return None
        
        try:
            exchange = self.exchanges[exchange_id]
            ticker = await asyncio.get_event_loop().run_in_executor(
                None, exchange.fetch_ticker, symbol
            )
            
            return {
                'exchange': exchange_id,
                'symbol': symbol,
                'price': ticker.get('last'),
                'bid': ticker.get('bid'),
                'ask': ticker.get('ask'),
                'volume': ticker.get('baseVolume'),
                'change_24h': ticker.get('percentage'),
                'timestamp': ticker.get('timestamp'),
                'datetime': ticker.get('datetime')
            }
        except Exception as e:
            logger.error(f"Error fetching ticker from {exchange_id}: {e}")
            return None
    
    async def get_all_tickers(self, symbol: str) -> List[Dict[str, Any]]:
        """获取所有交易所的ticker数据"""
        tasks = []
        for exchange_id in self.exchanges.keys():
            if symbol in self.FREE_EXCHANGES[exchange_id]['symbols']:
                tasks.append(self.get_ticker_data(exchange_id, symbol))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤掉None和异常结果
        valid_results = []
        for result in results:
            if result is not None and not isinstance(result, Exception):
                valid_results.append(result)
        
        return valid_results
    
    async def get_order_book_data(self, exchange_id: str, symbol: str, limit: int = 10) -> Optional[Dict[str, Any]]:
        """获取订单簿数据"""
        if exchange_id not in self.exchanges:
            return None
        
        if not self._check_rate_limit(exchange_id):
            return None
        
        try:
            exchange = self.exchanges[exchange_id]
            order_book = await asyncio.get_event_loop().run_in_executor(
                None, exchange.fetch_order_book, symbol, limit
            )
            
            return {
                'exchange': exchange_id,
                'symbol': symbol,
                'bids': order_book.get('bids', [])[:limit],
                'asks': order_book.get('asks', [])[:limit],
                'timestamp': order_book.get('timestamp'),
                'datetime': order_book.get('datetime')
            }
        except Exception as e:
            logger.error(f"Error fetching order book from {exchange_id}: {e}")
            return None
    
    async def calculate_arbitrage_opportunities(self, symbol: str) -> List[Dict[str, Any]]:
        """计算套利机会"""
        tickers = await self.get_all_tickers(symbol)
        
        if len(tickers) < 2:
            return []
        
        opportunities = []
        
        # 找出最高买价和最低卖价
        for i, ticker1 in enumerate(tickers):
            for j, ticker2 in enumerate(tickers):
                if i >= j:
                    continue
                
                # 检查套利机会：在ticker1买入，在ticker2卖出
                buy_price = ticker1.get('ask')  # 买入价格
                sell_price = ticker2.get('bid')  # 卖出价格
                
                if buy_price and sell_price and sell_price > buy_price:
                    profit_abs = sell_price - buy_price
                    profit_pct = (profit_abs / buy_price) * 100
                    
                    opportunities.append({
                        'buy_exchange': ticker1['exchange'],
                        'sell_exchange': ticker2['exchange'],
                        'symbol': symbol,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'profit_abs': profit_abs,
                        'profit_pct': profit_pct,
                        'buy_volume': ticker1.get('volume', 0),
                        'sell_volume': ticker2.get('volume', 0)
                    })
        
        # 按利润率排序
        opportunities.sort(key=lambda x: x['profit_pct'], reverse=True)
        return opportunities
    
    def get_supported_exchanges(self) -> List[Dict[str, Any]]:
        """获取支持的交易所列表"""
        return [
            {
                'id': exchange_id,
                'name': config['name'],
                'symbols': config['symbols'],
                'rate_limit': config['rate_limit'],
                'status': 'active' if exchange_id in self.exchanges else 'inactive'
            }
            for exchange_id, config in self.FREE_EXCHANGES.items()
        ]
    
    def get_supported_symbols(self) -> List[str]:
        """获取所有支持的交易对"""
        all_symbols = set()
        for config in self.FREE_EXCHANGES.values():
            all_symbols.update(config['symbols'])
        return sorted(list(all_symbols))
    
    async def get_market_summary(self, symbol: str) -> Dict[str, Any]:
        """获取市场摘要"""
        tickers = await self.get_all_tickers(symbol)
        
        if not tickers:
            return {'error': 'No data available'}
        
        prices = [t['price'] for t in tickers if t['price']]
        volumes = [t['volume'] for t in tickers if t['volume']]
        
        if not prices:
            return {'error': 'No price data available'}
        
        return {
            'symbol': symbol,
            'exchanges_count': len(tickers),
            'avg_price': sum(prices) / len(prices),
            'min_price': min(prices),
            'max_price': max(prices),
            'price_spread': max(prices) - min(prices),
            'price_spread_pct': ((max(prices) - min(prices)) / min(prices)) * 100,
            'total_volume': sum(volumes) if volumes else 0,
            'timestamp': datetime.now().isoformat()
        }