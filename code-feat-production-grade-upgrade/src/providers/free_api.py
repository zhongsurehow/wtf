import requests
import asyncio
import aiohttp
import time
from typing import Dict, List, Optional, Any
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)

class FreeAPIProvider:
    """免费API数据提供者，支持多个免费数据源"""
    
    def __init__(self):
        # 缓存设置：最多1000个条目，TTL为60秒
        self.cache = TTLCache(maxsize=1000, ttl=60)
        self.session = None
        
        # API端点配置
        self.endpoints = {
            'coingecko': {
                'base_url': 'https://api.coingecko.com/api/v3',
                'rate_limit': 10,  # 每分钟10次请求
                'last_request': 0
            },
            'cryptocompare': {
                'base_url': 'https://min-api.cryptocompare.com/data',
                'rate_limit': 100,  # 每小时100次请求
                'last_request': 0
            },
            'binance_public': {
                'base_url': 'https://api.binance.com/api/v3',
                'rate_limit': 1200,  # 每分钟1200次请求
                'last_request': 0
            }
        }
    
    async def get_session(self):
        """获取异步HTTP会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def _check_rate_limit(self, provider: str) -> bool:
        """检查API速率限制"""
        now = time.time()
        config = self.endpoints[provider]
        
        if provider == 'coingecko':
            # CoinGecko: 10次/分钟
            if now - config['last_request'] < 6:  # 6秒间隔
                return False
        elif provider == 'cryptocompare':
            # CryptoCompare: 100次/小时
            if now - config['last_request'] < 36:  # 36秒间隔
                return False
        elif provider == 'binance_public':
            # Binance: 1200次/分钟
            if now - config['last_request'] < 0.05:  # 0.05秒间隔
                return False
        
        config['last_request'] = now
        return True
    
    async def get_coingecko_prices(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """从CoinGecko获取价格数据"""
        cache_key = f"coingecko_prices_{','.join(sorted(symbols))}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        if not self._check_rate_limit('coingecko'):
            logger.warning("CoinGecko API rate limit exceeded")
            return {}
        
        try:
            # 将交易对转换为CoinGecko格式
            coin_ids = []
            symbol_map = {}
            
            for symbol in symbols:
                if '/' in symbol:
                    base, quote = symbol.split('/')
                    coin_id = base.lower()
                    coin_ids.append(coin_id)
                    symbol_map[coin_id] = symbol
            
            if not coin_ids:
                return {}
            
            session = await self.get_session()
            url = f"{self.endpoints['coingecko']['base_url']}/simple/price"
            params = {
                'ids': ','.join(coin_ids),
                'vs_currencies': 'usd,btc,eth',
                'include_24hr_change': 'true',
                'include_24hr_vol': 'true'
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    result = {}
                    for coin_id, price_data in data.items():
                        if coin_id in symbol_map:
                            symbol = symbol_map[coin_id]
                            result[symbol] = {
                                'price_usd': price_data.get('usd', 0),
                                'price_btc': price_data.get('btc', 0),
                                'price_eth': price_data.get('eth', 0),
                                'change_24h': price_data.get('usd_24h_change', 0),
                                'volume_24h': price_data.get('usd_24h_vol', 0),
                                'source': 'CoinGecko',
                                'timestamp': time.time()
                            }
                    
                    self.cache[cache_key] = result
                    return result
                else:
                    logger.error(f"CoinGecko API error: {response.status}")
                    return {}
        
        except Exception as e:
            logger.error(f"Error fetching CoinGecko prices: {e}")
            return {}
    
    async def get_binance_prices(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """从Binance公共API获取价格数据"""
        cache_key = f"binance_prices_{','.join(sorted(symbols))}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        if not self._check_rate_limit('binance_public'):
            logger.warning("Binance API rate limit exceeded")
            return {}
        
        try:
            session = await self.get_session()
            url = f"{self.endpoints['binance_public']['base_url']}/ticker/24hr"
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    result = {}
                    for item in data:
                        symbol_raw = item['symbol']
                        # 转换为标准格式 (BTCUSDT -> BTC/USDT)
                        if symbol_raw.endswith('USDT'):
                            base = symbol_raw[:-4]
                            symbol = f"{base}/USDT"
                        elif symbol_raw.endswith('BTC'):
                            base = symbol_raw[:-3]
                            symbol = f"{base}/BTC"
                        elif symbol_raw.endswith('ETH'):
                            base = symbol_raw[:-3]
                            symbol = f"{base}/ETH"
                        else:
                            continue
                        
                        if symbol in symbols:
                            result[symbol] = {
                                'price_usd': float(item['lastPrice']),
                                'change_24h': float(item['priceChangePercent']),
                                'volume_24h': float(item['volume']),
                                'high_24h': float(item['highPrice']),
                                'low_24h': float(item['lowPrice']),
                                'source': 'Binance',
                                'timestamp': time.time()
                            }
                    
                    self.cache[cache_key] = result
                    return result
                else:
                    logger.error(f"Binance API error: {response.status}")
                    return {}
        
        except Exception as e:
            logger.error(f"Error fetching Binance prices: {e}")
            return {}
    
    async def get_cryptocompare_prices(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """从CryptoCompare获取价格数据"""
        cache_key = f"cryptocompare_prices_{','.join(sorted(symbols))}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        if not self._check_rate_limit('cryptocompare'):
            logger.warning("CryptoCompare API rate limit exceeded")
            return {}
        
        try:
            session = await self.get_session()
            
            # 提取所有基础货币
            base_currencies = set()
            for symbol in symbols:
                if '/' in symbol:
                    base, _ = symbol.split('/')
                    base_currencies.add(base)
            
            if not base_currencies:
                return {}
            
            url = f"{self.endpoints['cryptocompare']['base_url']}/pricemultifull"
            params = {
                'fsyms': ','.join(base_currencies),
                'tsyms': 'USD,BTC,ETH'
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'RAW' not in data:
                        return {}
                    
                    result = {}
                    for base_currency, quote_data in data['RAW'].items():
                        for quote_currency, price_info in quote_data.items():
                            symbol = f"{base_currency}/{quote_currency}"
                            if symbol in symbols:
                                result[symbol] = {
                                    'price_usd': price_info.get('PRICE', 0),
                                    'change_24h': price_info.get('CHANGEPCT24HOUR', 0),
                                    'volume_24h': price_info.get('VOLUME24HOUR', 0),
                                    'high_24h': price_info.get('HIGH24HOUR', 0),
                                    'low_24h': price_info.get('LOW24HOUR', 0),
                                    'source': 'CryptoCompare',
                                    'timestamp': time.time()
                                }
                    
                    self.cache[cache_key] = result
                    return result
                else:
                    logger.error(f"CryptoCompare API error: {response.status}")
                    return {}
        
        except Exception as e:
            logger.error(f"Error fetching CryptoCompare prices: {e}")
            return {}
    
    async def get_aggregated_prices(self, symbols: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """获取聚合价格数据，从多个免费API源获取"""
        tasks = [
            self.get_coingecko_prices(symbols),
            self.get_binance_prices(symbols),
            self.get_cryptocompare_prices(symbols)
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            aggregated = {}
            for symbol in symbols:
                aggregated[symbol] = []
                
                for result in results:
                    if isinstance(result, dict) and symbol in result:
                        aggregated[symbol].append(result[symbol])
            
            return aggregated
        
        except Exception as e:
            logger.error(f"Error aggregating prices: {e}")
            return {}
    
    def get_supported_exchanges(self) -> List[str]:
        """获取支持的免费数据源列表"""
        return ['CoinGecko', 'Binance', 'CryptoCompare']
    
    def get_popular_symbols(self) -> List[str]:
        """获取热门交易对列表"""
        return [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT',
            'XRP/USDT', 'DOT/USDT', 'DOGE/USDT', 'AVAX/USDT', 'MATIC/USDT',
            'LINK/USDT', 'UNI/USDT', 'LTC/USDT', 'ATOM/USDT', 'FTT/USDT'
        ]

# 全局实例
free_api_provider = FreeAPIProvider()