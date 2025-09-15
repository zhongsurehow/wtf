import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import logging

logger = logging.getLogger(__name__)

class TrendAnalyzer:
    """
    价格趋势分析器，提供历史数据分析和趋势预测功能
    """
    
    def __init__(self):
        self.price_history = {}
        self.trend_cache = {}
    
    def add_price_data(self, symbol: str, exchange: str, price_data: Dict[str, Any]):
        """添加价格数据到历史记录"""
        key = f"{symbol}_{exchange}"
        
        if key not in self.price_history:
            self.price_history[key] = []
        
        # 添加时间戳
        price_data['timestamp'] = datetime.now()
        self.price_history[key].append(price_data)
        
        # 保持最近1000条记录
        if len(self.price_history[key]) > 1000:
            self.price_history[key] = self.price_history[key][-1000:]
    
    def get_price_trend(self, symbol: str, exchange: str, hours: int = 24) -> Dict[str, Any]:
        """获取价格趋势分析"""
        key = f"{symbol}_{exchange}"
        
        if key not in self.price_history or len(self.price_history[key]) < 2:
            return {'error': 'Insufficient data'}
        
        # 获取指定时间范围内的数据
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_data = [
            data for data in self.price_history[key] 
            if data['timestamp'] >= cutoff_time
        ]
        
        if len(recent_data) < 2:
            return {'error': 'Insufficient recent data'}
        
        # 计算趋势指标
        prices = [float(data['price']) for data in recent_data if data.get('price')]
        timestamps = [data['timestamp'] for data in recent_data if data.get('price')]
        
        if len(prices) < 2:
            return {'error': 'Insufficient price data'}
        
        # 基本统计
        current_price = prices[-1]
        start_price = prices[0]
        min_price = min(prices)
        max_price = max(prices)
        avg_price = np.mean(prices)
        
        # 价格变化
        price_change = current_price - start_price
        price_change_pct = (price_change / start_price) * 100
        
        # 波动率计算
        if len(prices) > 1:
            returns = np.diff(prices) / prices[:-1]
            volatility = np.std(returns) * 100
        else:
            volatility = 0
        
        # 趋势方向
        if len(prices) >= 3:
            # 使用线性回归计算趋势
            x = np.arange(len(prices))
            slope = np.polyfit(x, prices, 1)[0]
            
            if slope > 0.001:
                trend_direction = 'upward'
                trend_strength = min(abs(slope) * 1000, 100)
            elif slope < -0.001:
                trend_direction = 'downward'
                trend_strength = min(abs(slope) * 1000, 100)
            else:
                trend_direction = 'sideways'
                trend_strength = 0
        else:
            trend_direction = 'unknown'
            trend_strength = 0
        
        # 支撑和阻力位
        support_level = min_price
        resistance_level = max_price
        
        return {
            'symbol': symbol,
            'exchange': exchange,
            'current_price': current_price,
            'start_price': start_price,
            'price_change': price_change,
            'price_change_pct': price_change_pct,
            'min_price': min_price,
            'max_price': max_price,
            'avg_price': avg_price,
            'volatility': volatility,
            'trend_direction': trend_direction,
            'trend_strength': trend_strength,
            'support_level': support_level,
            'resistance_level': resistance_level,
            'data_points': len(prices),
            'time_range_hours': hours,
            'last_update': timestamps[-1] if timestamps else None
        }
    
    def create_price_chart(self, symbol: str, exchange: str, hours: int = 24) -> Optional[go.Figure]:
        """创建价格趋势图表"""
        key = f"{symbol}_{exchange}"
        
        if key not in self.price_history or len(self.price_history[key]) < 2:
            return None
        
        # 获取数据
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_data = [
            data for data in self.price_history[key] 
            if data['timestamp'] >= cutoff_time and data.get('price')
        ]
        
        if len(recent_data) < 2:
            return None
        
        # 准备数据
        df = pd.DataFrame(recent_data)
        df['price'] = df['price'].astype(float)
        df = df.sort_values('timestamp')
        
        # 创建图表
        fig = go.Figure()
        
        # 添加价格线
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['price'],
            mode='lines+markers',
            name=f'{symbol} @ {exchange}',
            line=dict(color='blue', width=2),
            marker=dict(size=4)
        ))
        
        # 添加移动平均线
        if len(df) >= 10:
            df['ma_short'] = df['price'].rolling(window=min(5, len(df)//2)).mean()
            df['ma_long'] = df['price'].rolling(window=min(10, len(df)//2)).mean()
            
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['ma_short'],
                mode='lines',
                name='短期均线',
                line=dict(color='orange', width=1, dash='dash')
            ))
            
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['ma_long'],
                mode='lines',
                name='长期均线',
                line=dict(color='red', width=1, dash='dot')
            ))
        
        # 添加支撑和阻力位
        min_price = df['price'].min()
        max_price = df['price'].max()
        
        fig.add_hline(
            y=min_price,
            line_dash="dash",
            line_color="green",
            annotation_text="支撑位",
            annotation_position="bottom right"
        )
        
        fig.add_hline(
            y=max_price,
            line_dash="dash",
            line_color="red",
            annotation_text="阻力位",
            annotation_position="top right"
        )
        
        # 更新布局
        fig.update_layout(
            title=f'{symbol} @ {exchange} - {hours}小时价格趋势',
            xaxis_title='时间',
            yaxis_title='价格 (USD)',
            height=400,
            showlegend=True,
            hovermode='x unified'
        )
        
        return fig
    
    def create_volatility_chart(self, symbol: str, exchanges: List[str], hours: int = 24) -> Optional[go.Figure]:
        """创建波动率对比图表"""
        volatility_data = []
        
        for exchange in exchanges:
            trend_data = self.get_price_trend(symbol, exchange, hours)
            if 'error' not in trend_data:
                volatility_data.append({
                    'exchange': exchange,
                    'volatility': trend_data['volatility'],
                    'price_change_pct': trend_data['price_change_pct']
                })
        
        if not volatility_data:
            return None
        
        df = pd.DataFrame(volatility_data)
        
        # 创建波动率对比图
        fig = px.bar(
            df,
            x='exchange',
            y='volatility',
            title=f'{symbol} 各交易所波动率对比 ({hours}小时)',
            labels={'volatility': '波动率 (%)', 'exchange': '交易所'},
            color='volatility',
            color_continuous_scale='RdYlBu_r'
        )
        
        fig.update_layout(height=300)
        
        return fig
    
    def get_arbitrage_trend(self, symbol: str, exchange1: str, exchange2: str, hours: int = 24) -> Dict[str, Any]:
        """获取套利机会趋势"""
        trend1 = self.get_price_trend(symbol, exchange1, hours)
        trend2 = self.get_price_trend(symbol, exchange2, hours)
        
        if 'error' in trend1 or 'error' in trend2:
            return {'error': 'Insufficient data for arbitrage analysis'}
        
        # 计算价差趋势
        price_diff = trend1['current_price'] - trend2['current_price']
        price_diff_pct = (price_diff / min(trend1['current_price'], trend2['current_price'])) * 100
        
        # 判断套利方向
        if price_diff > 0:
            buy_exchange = exchange2
            sell_exchange = exchange1
            arbitrage_opportunity = abs(price_diff_pct)
        else:
            buy_exchange = exchange1
            sell_exchange = exchange2
            arbitrage_opportunity = abs(price_diff_pct)
        
        return {
            'symbol': symbol,
            'exchange1': exchange1,
            'exchange2': exchange2,
            'price1': trend1['current_price'],
            'price2': trend2['current_price'],
            'price_diff': price_diff,
            'price_diff_pct': price_diff_pct,
            'arbitrage_opportunity': arbitrage_opportunity,
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'volatility1': trend1['volatility'],
            'volatility2': trend2['volatility'],
            'trend1': trend1['trend_direction'],
            'trend2': trend2['trend_direction']
        }
    
    def get_market_summary(self, symbol: str, exchanges: List[str]) -> Dict[str, Any]:
        """获取市场总体摘要"""
        trends = []
        
        for exchange in exchanges:
            trend = self.get_price_trend(symbol, exchange, 24)
            if 'error' not in trend:
                trends.append(trend)
        
        if not trends:
            return {'error': 'No trend data available'}
        
        # 计算市场指标
        prices = [t['current_price'] for t in trends]
        volatilities = [t['volatility'] for t in trends]
        changes = [t['price_change_pct'] for t in trends]
        
        return {
            'symbol': symbol,
            'exchanges_analyzed': len(trends),
            'avg_price': np.mean(prices),
            'price_spread': max(prices) - min(prices),
            'price_spread_pct': ((max(prices) - min(prices)) / min(prices)) * 100,
            'avg_volatility': np.mean(volatilities),
            'max_volatility': max(volatilities),
            'min_volatility': min(volatilities),
            'avg_change_24h': np.mean(changes),
            'best_performer': exchanges[changes.index(max(changes))] if changes else None,
            'worst_performer': exchanges[changes.index(min(changes))] if changes else None,
            'most_volatile': exchanges[volatilities.index(max(volatilities))] if volatilities else None,
            'least_volatile': exchanges[volatilities.index(min(volatilities))] if volatilities else None,
            'timestamp': datetime.now()
        }
    
    def clear_old_data(self, hours: int = 168):  # 默认保留7天数据
        """清理旧数据"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for key in self.price_history:
            self.price_history[key] = [
                data for data in self.price_history[key]
                if data['timestamp'] >= cutoff_time
            ]
        
        # 清理空的历史记录
        empty_keys = [key for key, data in self.price_history.items() if not data]
        for key in empty_keys:
            del self.price_history[key]
        
        logger.info(f"Cleaned old data, kept {len(self.price_history)} symbols")