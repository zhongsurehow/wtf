import streamlit as st
import asyncio
import nest_asyncio
import time
import logging
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
from typing import List, Dict, Any
from datetime import datetime, timedelta

# --- Basic Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Local Imports ---
from .config import load_config
from .db import DatabaseManager
from .engine import ArbitrageEngine, Opportunity
from .providers.base import BaseProvider
from .providers.cex import CEXProvider
from .providers.dex import DEXProvider
from .providers.bridge import BridgeProvider
from .providers.free_api import FreeAPIProvider, free_api_provider
from .providers.ccxt_enhanced import EnhancedCCXTProvider
from .providers.trend_analyzer import TrendAnalyzer
from .ui.components import sidebar_controls, display_error

# Apply nest_asyncio to allow running asyncio event loops within Streamlit's loop
nest_asyncio.apply()

# --- Page Configuration ---
st.set_page_config(
    page_title="套利机会仪表板",
    layout="wide",
    page_icon="🎯",
    initial_sidebar_state="expanded"
)

# --- Helper Functions ---
def safe_run_async(coro):
    """Safely runs an async coroutine, handling nested event loops."""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        if "cannot run loop while another loop is running" in str(e):
            # This is expected in Streamlit's environment with nest_asyncio
            return asyncio.run(coro)
        st.error(f"异步操作失败: {e}")
        return None

def _validate_symbol(symbol: str) -> bool:
    """Validates that the symbol is not empty and has a valid format."""
    if not symbol or '/' not in symbol or len(symbol.split('/')) != 2:
        st.error("请输入有效的交易对格式，例如 'BTC/USDT'。")
        return False
    return True

def _create_depth_chart(order_book: dict) -> go.Figure:
    """Creates a Plotly order book depth chart."""
    bids = pd.DataFrame(order_book.get('bids', []), columns=['price', 'volume']).astype(float)
    asks = pd.DataFrame(order_book.get('asks', []), columns=['price', 'volume']).astype(float)
    bids = bids.sort_values('price', ascending=False)
    asks = asks.sort_values('price', ascending=True)
    bids['cumulative'] = bids['volume'].cumsum()
    asks['cumulative'] = asks['volume'].cumsum()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bids['price'], y=bids['cumulative'], name='买单', fill='tozeroy', line_color='green'))
    fig.add_trace(go.Scatter(x=asks['price'], y=asks['cumulative'], name='卖单', fill='tozeroy', line_color='red'))
    fig.update_layout(title_text=f"{order_book.get('symbol', '')} 市场深度", xaxis_title="价格", yaxis_title="累计数量", height=300, margin=dict(l=20, r=20, t=40, b=20))
    return fig

def _create_candlestick_chart(df: pd.DataFrame, symbol: str, show_volume: bool = True, ma_periods: list = None) -> go.Figure:
    """Creates a Plotly candlestick chart from OHLCV data with optional indicators."""
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title_text=f"{symbol} K线图 - 无数据", height=400)
        return fig
    
    # Ensure required columns exist
    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        fig = go.Figure()
        fig.update_layout(title_text=f"{symbol} K线图 - 数据格式错误", height=400)
        return fig
    
    # Convert timestamp to datetime if it's not already
    if 'datetime' not in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    fig = go.Figure(data=[go.Candlestick(
        x=df['datetime'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name=symbol
    )])
    
    # Add moving averages if requested
    if ma_periods:
        colors = ['orange', 'purple', 'green', 'red', 'cyan', 'magenta']
        for i, period in enumerate(ma_periods):
            if len(df) >= period:
                ma = df['close'].rolling(window=period).mean()
                fig.add_trace(go.Scatter(
                    x=df['datetime'],
                    y=ma,
                    mode='lines',
                    name=f'MA{period}',
                    line=dict(color=colors[i % len(colors)], width=1.5)
                ))
    
    # Add volume as a subplot if requested
    if show_volume:
        fig.add_trace(go.Bar(
            x=df['datetime'],
            y=df['volume'],
            name='成交量',
            yaxis='y2',
            opacity=0.3,
            marker_color='blue'
        ))
    
    # Configure layout
    layout_config = {
        'title_text': f"{symbol} K线图",
        'xaxis_title': "时间",
        'yaxis_title': "价格",
        'height': 600 if show_volume else 500,
        'margin': dict(l=20, r=20, t=40, b=20),
        'xaxis_rangeslider_visible': False,
        'showlegend': True
    }
    
    if show_volume:
        layout_config['yaxis2'] = dict(
            title="成交量",
            overlaying='y',
            side='right',
            showgrid=False
        )
    
    fig.update_layout(**layout_config)
    
    return fig

# --- Caching Functions ---
@st.cache_data
def get_config():
    """Load configuration from file and cache it."""
    return load_config()

@st.cache_resource
def get_db_manager(db_path: str):
    """Creates and caches the database manager."""
    if not db_path: return None
    db_manager = DatabaseManager(db_path)
    try:
        asyncio.run(db_manager.__aenter__())
        asyncio.run(db_manager.init_db())
        return db_manager
    except Exception as e:
        st.error(f"连接或初始化SQLite数据库时失败: {e}")
        asyncio.run(db_manager.__aexit__(None, None, None))
        return None

@st.cache_resource
def get_providers(_config: Dict, _session_state) -> List[BaseProvider]:
    """Create and cache a list of all data providers."""
    providers = []
    is_demo_mode = not bool(_session_state.get('api_keys'))
    provider_config = _config.copy()
    provider_config['api_keys'] = {**_config.get('api_keys', {}), **_session_state.get('api_keys', {})}
    for ex_id in _session_state.selected_exchanges:
        try:
            providers.append(CEXProvider(name=ex_id, config=provider_config, force_mock=is_demo_mode))
        except ValueError as e:
            st.error(f"初始化 CEX 提供商 '{ex_id}' 失败: {e}", icon="🚨")
        except Exception as e:
            st.warning(f"初始化 CEX 提供商 '{ex_id}' 时发生未知错误: {e}", icon="⚠️")
    return providers

def init_session_state(config):
    """Initializes the session state with default values."""
    if 'selected_exchanges' not in st.session_state:
        st.session_state.selected_exchanges = ['binance', 'okx', 'bybit']
    if 'selected_symbols' not in st.session_state:
        st.session_state.selected_symbols = ['BTC/USDT', 'ETH/USDT']
    if 'api_keys' not in st.session_state:
        st.session_state.api_keys = {}

# --- Dashboard UI ---
def show_dashboard(engine: ArbitrageEngine, providers: List[BaseProvider]):
    """The main view of the application, designed as a single, consolidated dashboard."""
    st.title("🎯 专业套利交易系统")
    
    # Enhanced status indicators with real-time metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("连接交易所", len([p for p in providers if isinstance(p, CEXProvider)]))
    with col2:
        st.metric("监控币种", len(st.session_state.get('selected_symbols', [])))
    with col3:
        demo_mode = not bool(st.session_state.get('api_keys'))
        st.metric("运行模式", "演示" if demo_mode else "实时")
    with col4:
        # Calculate active opportunities count
        opportunities = safe_run_async(engine.find_opportunities(st.session_state.selected_symbols)) if engine else []
        profitable_opps = len([opp for opp in opportunities if opp.get('profit_percentage', 0) > 0.1])
        st.metric("活跃机会", profitable_opps, delta=f"+{profitable_opps}" if profitable_opps > 0 else None)
    with col5:
        # Show highest profit opportunity
        max_profit = max([opp.get('profit_percentage', 0) for opp in opportunities], default=0)
        st.metric("最高收益率", f"{max_profit:.3f}%", delta=f"+{max_profit:.3f}%" if max_profit > 0 else None)
    
    # Professional Alert System
    with st.expander("🚨 套利警报系统", expanded=True):
        alert_col1, alert_col2, alert_col3 = st.columns(3)
        
        with alert_col1:
            min_profit = st.number_input("最小收益率阈值 (%)", min_value=0.01, max_value=10.0, value=0.5, step=0.01, key="min_profit_threshold")
            st.session_state['alert_min_profit'] = min_profit
        
        with alert_col2:
            alert_enabled = st.checkbox("启用声音警报", value=False, key="sound_alert")
            email_alert = st.checkbox("启用邮件通知", value=False, key="email_alert")
        
        with alert_col3:
            max_spread = st.number_input("最大价差限制 (%)", min_value=0.1, max_value=50.0, value=5.0, step=0.1, key="max_spread")
            min_volume = st.number_input("最小交易量 (USDT)", min_value=1000, max_value=1000000, value=10000, step=1000, key="min_volume")
    
    # Quick Action Panel
    with st.expander("⚡ 快速操作面板"):
        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
        
        with action_col1:
            if st.button("🔄 刷新所有数据", use_container_width=True):
                st.rerun()
        
        with action_col2:
            if st.button("📊 导出套利报告", use_container_width=True):
                st.info("报告导出功能开发中...")
        
        with action_col3:
            if st.button("⚙️ 风险设置", use_container_width=True):
                st.session_state['show_risk_settings'] = True
        
        with action_col4:
            auto_refresh = st.checkbox("自动刷新 (30s)", value=False, key="auto_refresh_pro")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📈 实时套利机会排行榜")
        
        # Filter controls
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            min_profit_filter = st.number_input("最小收益率过滤 (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.05, key="profit_filter")
        with filter_col2:
            sort_by = st.selectbox("排序方式", ["收益率", "净利润", "交易量"], key="sort_method")
        
        opp_placeholder = st.empty()
        with st.spinner("正在寻找套利机会..."):
            opportunities = safe_run_async(engine.find_opportunities(st.session_state.selected_symbols))
            
            # Filter opportunities based on user criteria
            filtered_opps = [opp for opp in opportunities if opp.get('profit_percentage', 0) >= min_profit_filter]
            
            if not filtered_opps:
                opp_placeholder.info(f"🔍 未发现收益率 ≥ {min_profit_filter}% 的套利机会")
            else:
                df = pd.DataFrame(filtered_opps)
                df = df.sort_values(by="profit_percentage", ascending=False)
                
                # Enhanced display with more professional metrics
                display_df = df[['profit_percentage', 'buy_at', 'sell_at', 'net_profit_usd', 'symbol']].copy()
                display_df['路径'] = display_df['buy_at'] + ' → ' + display_df['sell_at']
                display_df['风险等级'] = display_df['profit_percentage'].apply(
                    lambda x: '🟢 低' if x < 1 else '🟡 中' if x < 3 else '🔴 高'
                )
                display_df['执行难度'] = display_df['profit_percentage'].apply(
                    lambda x: '简单' if x < 2 else '中等' if x < 5 else '困难'
                )
                
                final_df = display_df[['profit_percentage', '路径', 'net_profit_usd', '风险等级', '执行难度', 'symbol']]
                final_df.columns = ['收益率(%)', '套利路径', '净利润(USD)', '风险等级', '执行难度', '交易对']
                
                # Add action buttons for top opportunities
                if len(final_df) > 0:
                    st.success(f"🎯 发现 {len(final_df)} 个套利机会！")
                    
                opp_placeholder.dataframe(
                    final_df,
                    width='stretch',
                    hide_index=True,
                    column_config={
                        "收益率(%)": st.column_config.NumberColumn(format="%.4f%%"),
                        "净利润(USD)": st.column_config.NumberColumn(format="$%.2f"),
                    }
                )
                
                # Quick execution buttons for top 3 opportunities
                if len(final_df) >= 1:
                    st.markdown("**⚡ 快速执行 (模拟)**")
                    exec_col1, exec_col2, exec_col3 = st.columns(3)
                    
                    for i, (idx, row) in enumerate(final_df.head(3).iterrows()):
                        with [exec_col1, exec_col2, exec_col3][i]:
                            if st.button(f"执行 #{i+1} ({row['收益率(%)']}%)", key=f"exec_{i}", use_container_width=True):
                                st.success(f"模拟执行套利: {row['套利路径']} - 预期收益: {row['净利润(USD)']}")

    with col2:
        st.subheader("💰 套利收益计算器")
        
        with st.container():
            calc_col1, calc_col2 = st.columns(2)
            
            with calc_col1:
                investment_amount = st.number_input("投资金额 (USDT)", min_value=100, max_value=1000000, value=10000, step=100, key="investment")
                expected_profit = st.number_input("预期收益率 (%)", min_value=0.01, max_value=20.0, value=1.0, step=0.01, key="expected_profit")
            
            with calc_col2:
                trading_fee = st.number_input("交易手续费 (%)", min_value=0.0, max_value=1.0, value=0.1, step=0.01, key="trading_fee")
                slippage = st.number_input("滑点损失 (%)", min_value=0.0, max_value=5.0, value=0.2, step=0.01, key="slippage")
            
            # Calculate results
            gross_profit = investment_amount * (expected_profit / 100)
            total_fees = investment_amount * ((trading_fee * 2 + slippage) / 100)  # Buy + Sell fees + slippage
            net_profit = gross_profit - total_fees
            roi = (net_profit / investment_amount) * 100
            
            # Display results
            st.markdown("**📊 收益分析**")
            result_col1, result_col2, result_col3 = st.columns(3)
            
            with result_col1:
                st.metric("毛利润", f"${gross_profit:.2f}")
            with result_col2:
                st.metric("总费用", f"${total_fees:.2f}")
            with result_col3:
                color = "normal" if net_profit > 0 else "inverse"
                st.metric("净利润", f"${net_profit:.2f}", f"{roi:.3f}%")
            
            # Risk assessment
            if net_profit > 0:
                if roi > 0.5:
                    st.success(f"🟢 高收益机会: 净收益率 {roi:.3f}%")
                elif roi > 0.1:
                    st.info(f"🟡 中等机会: 净收益率 {roi:.3f}%")
                else:
                    st.warning(f"🟠 低收益机会: 净收益率 {roi:.3f}%")
            else:
                st.error(f"🔴 亏损风险: 净收益率 {roi:.3f}%")
        
        st.markdown("---")
        st.subheader("📊 实时价格对比表")
        
        # 价格对比控制面板
        price_control_col1, price_control_col2, price_control_col3 = st.columns(3)
        with price_control_col1:
            highlight_best = st.checkbox("高亮最优价格", value=True, key="highlight_best_price")
        with price_control_col2:
            show_percentage = st.checkbox("显示价差百分比", value=True, key="show_price_percentage")
        with price_control_col3:
            auto_sort = st.checkbox("按价差排序", value=True, key="auto_sort_prices")
        
        price_placeholder = st.empty()

        with st.spinner("正在获取最新价格..."):
            tasks = []
            provider_symbol_pairs = []
            cex_providers = [p for p in providers if isinstance(p, CEXProvider)]
            for symbol in st.session_state.selected_symbols:
                for provider in cex_providers:
                    tasks.append(provider.get_ticker(symbol))
                    provider_symbol_pairs.append((provider.name, symbol))

            all_tickers = safe_run_async(asyncio.gather(*tasks))

            if all_tickers:
                # Filter out errors and process into a list of dicts
                processed_tickers = [
                    {'symbol': t['symbol'], 'provider': provider_symbol_pairs[i][0], 'price': t['last'], 'volume': t.get('baseVolume', 0), 'change': t.get('percentage', 0)}
                    for i, t in enumerate(all_tickers) if t and 'error' not in t
                ]
                if processed_tickers:
                    price_df = pd.DataFrame(processed_tickers)
                    # Create a pivot table: symbols as rows, providers as columns, prices as values
                    pivot_df = price_df.pivot(index='symbol', columns='provider', values='price')
                    
                    # Add price statistics and comparison metrics
                    if len(pivot_df.columns) > 1:
                        pivot_df['最高价'] = pivot_df.max(axis=1, numeric_only=True)
                        pivot_df['最低价'] = pivot_df.min(axis=1, numeric_only=True)
                        pivot_df['价差'] = pivot_df['最高价'] - pivot_df['最低价']
                        pivot_df['价差%'] = (pivot_df['价差'] / pivot_df['最低价'] * 100).round(4)
                        pivot_df['套利机会'] = pivot_df['价差%'].apply(lambda x: '🟢 高' if x > 1.0 else '🟡 中' if x > 0.3 else '🔴 低')
                        
                        # 添加最佳买入和卖出交易所
                        pivot_df['最佳买入'] = pivot_df[cex_providers[0].name if cex_providers else 'binance'].index.map(
                            lambda symbol: pivot_df.loc[symbol, [p.name for p in cex_providers]].idxmin()
                        )
                        pivot_df['最佳卖出'] = pivot_df[cex_providers[0].name if cex_providers else 'binance'].index.map(
                            lambda symbol: pivot_df.loc[symbol, [p.name for p in cex_providers]].idxmax()
                        )
                    
                    # 按价差排序（如果启用）
                    if auto_sort and '价差%' in pivot_df.columns:
                        pivot_df = pivot_df.sort_values('价差%', ascending=False)
                    
                    # 创建样式化的数据框
                    def style_price_comparison(df):
                        # 为价格列创建样式
                        styled = df.style
                        
                        if highlight_best:
                            # 高亮最低价格（绿色）和最高价格（红色）
                            for symbol in df.index:
                                if len([col for col in df.columns if col in [p.name for p in cex_providers]]) > 1:
                                    price_cols = [col for col in df.columns if col in [p.name for p in cex_providers]]
                                    min_col = df.loc[symbol, price_cols].idxmin()
                                    max_col = df.loc[symbol, price_cols].idxmax()
                                    
                                    styled = styled.applymap(
                                        lambda x: 'background-color: #90EE90' if x == df.loc[symbol, min_col] else 
                                                  'background-color: #FFB6C1' if x == df.loc[symbol, max_col] else '',
                                        subset=pd.IndexSlice[symbol, price_cols]
                                    )
                        
                        return styled
                    
                    # Format the dataframe for better display
                    column_config = {
                        **{col: st.column_config.NumberColumn(format="$%.4f") for col in pivot_df.columns if col in [p.name for p in cex_providers]},
                        '最高价': st.column_config.NumberColumn(format="$%.4f"),
                        '最低价': st.column_config.NumberColumn(format="$%.4f"),
                        '价差': st.column_config.NumberColumn(format="$%.4f"),
                        '价差%': st.column_config.NumberColumn(format="%.4f%%")
                    }
                    
                    price_placeholder.dataframe(
                        pivot_df,
                        width='stretch',
                        column_config=column_config
                    )
                    
                    # 添加价格对比图表
                    if len(pivot_df.columns) > 1 and len(pivot_df) > 0:
                        st.markdown("**📈 价格对比可视化**")
                        
                        # 创建价格对比柱状图
                        fig_comparison = go.Figure()
                        
                        exchange_cols = [col for col in pivot_df.columns if col in [p.name for p in cex_providers]]
                        colors = px.colors.qualitative.Set3[:len(exchange_cols)]
                        
                        for i, exchange in enumerate(exchange_cols):
                            fig_comparison.add_trace(go.Bar(
                                name=exchange.capitalize(),
                                x=pivot_df.index,
                                y=pivot_df[exchange],
                                marker_color=colors[i],
                                text=pivot_df[exchange].round(4),
                                textposition='auto'
                            ))
                        
                        fig_comparison.update_layout(
                            title="各交易所价格对比",
                            xaxis_title="交易对",
                            yaxis_title="价格 (USD)",
                            barmode='group',
                            height=400,
                            showlegend=True
                        )
                        
                        st.plotly_chart(fig_comparison, use_container_width=True)
                        
                        # 价差分析图
                        if '价差%' in pivot_df.columns:
                            fig_spread = go.Figure()
                            
                            fig_spread.add_trace(go.Bar(
                                x=pivot_df.index,
                                y=pivot_df['价差%'],
                                marker_color=pivot_df['价差%'].apply(
                                    lambda x: '#FF6B6B' if x > 1.0 else '#4ECDC4' if x > 0.3 else '#95E1D3'
                                ),
                                text=pivot_df['价差%'].round(3),
                                textposition='auto'
                            ))
                            
                            fig_spread.update_layout(
                                title="价差百分比分析",
                                xaxis_title="交易对",
                                yaxis_title="价差百分比 (%)",
                                height=300
                            )
                            
                            st.plotly_chart(fig_spread, use_container_width=True)
                
                else:
                    price_placeholder.warning("未能获取任何有效的价格数据。")
            else:
                price_placeholder.warning("未能获取任何价格数据。")
        
        # 免费API价格数据展示
        st.markdown("---")
        st.subheader("🆓 免费API价格数据")
        
        free_api_col1, free_api_col2 = st.columns([4, 1])
        
        with free_api_col2:
            st.markdown("**数据源选择**")
            use_coingecko = st.checkbox("CoinGecko", value=True, key="use_coingecko")
            use_cryptocompare = st.checkbox("CryptoCompare", value=True, key="use_cryptocompare")
            use_binance_public = st.checkbox("Binance Public", value=True, key="use_binance_public")
            
            selected_symbols_free = st.multiselect(
                "选择交易对",
                options=free_api_provider.get_popular_symbols(),
                default=['BTC/USDT', 'ETH/USDT', 'BNB/USDT'],
                key="selected_symbols_free"
            )
            
            if st.button("🔄 刷新免费数据", key="refresh_free_data"):
                st.session_state.free_data_refresh = time.time()
        
        with free_api_col1:
            if selected_symbols_free and any([use_coingecko, use_cryptocompare, use_binance_public]):
                with st.spinner("获取免费API数据..."):
                    try:
                        # 异步获取免费API数据
                        async def fetch_free_data():
                            return await free_api_provider.get_aggregated_prices(selected_symbols_free)
                        
                        # 运行异步函数
                        import nest_asyncio
                        nest_asyncio.apply()
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        free_data = loop.run_until_complete(fetch_free_data())
                        loop.close()
                        
                        if free_data:
                            # 创建免费API数据表格
                            free_rows = []
                            for symbol, price_list in free_data.items():
                                for price_info in price_list:
                                    free_rows.append({
                                        '交易对': symbol,
                                        '数据源': price_info.get('source', 'Unknown'),
                                        '价格 (USD)': price_info.get('price_usd', 0),
                                        '24h变化%': price_info.get('change_24h', 0),
                                        '24h成交量': price_info.get('volume_24h', 0),
                                        '更新时间': datetime.fromtimestamp(price_info.get('timestamp', time.time())).strftime('%H:%M:%S')
                                    })
                            
                            if free_rows:
                                df_free = pd.DataFrame(free_rows)
                                
                                # 按交易对分组显示
                                for symbol in selected_symbols_free:
                                    symbol_data = df_free[df_free['交易对'] == symbol]
                                    if not symbol_data.empty:
                                        st.markdown(f"**{symbol}**")
                                        
                                        # 计算价差
                                        if len(symbol_data) > 1:
                                            max_price = symbol_data['价格 (USD)'].max()
                                            min_price = symbol_data['价格 (USD)'].min()
                                            spread_pct = ((max_price - min_price) / min_price * 100) if min_price > 0 else 0
                                            
                                            spread_color = "🟢" if spread_pct > 1.0 else "🟡" if spread_pct > 0.3 else "🔴"
                                            st.caption(f"{spread_color} 价差: {spread_pct:.3f}% (${max_price - min_price:.4f})")
                                        
                                        # 显示数据表格
                                        st.dataframe(
                                            symbol_data.drop('交易对', axis=1),
                                            use_container_width=True,
                                            hide_index=True,
                                            column_config={
                                                '价格 (USD)': st.column_config.NumberColumn(format="$%.4f"),
                                                '24h变化%': st.column_config.NumberColumn(format="%.2f%%"),
                                                '24h成交量': st.column_config.NumberColumn(format="%.0f")
                                            }
                                        )
                                        
                                        st.markdown("")
                            else:
                                st.info("暂无免费API数据")
                        else:
                            st.warning("无法获取免费API数据，请检查网络连接")
                    
                    except Exception as e:
                        st.error(f"获取免费API数据时出错: {str(e)}")
                        logger.error(f"Free API data error: {e}")
            else:
                st.info("请选择交易对和数据源以获取免费API数据")

    # 价差排行榜和热力图
    st.markdown("---")
    st.subheader("🔥 实时价差排行榜")
    
    ranking_col1, ranking_col2 = st.columns([4, 1])
    
    with ranking_col2:
        min_spread = st.number_input("最小价差 (%)", min_value=0.0, max_value=10.0, value=0.1, step=0.1, key="min_spread_ranking")
        top_n = st.selectbox("显示数量", [5, 10, 20, 50], index=1, key="top_n_ranking")
    
    with ranking_col1:
        # 模拟价差数据 (实际应用中从实时数据获取)
        spread_data = [
            {"交易对": "BTC/USDT", "买入交易所": "Binance", "卖出交易所": "OKX", "价差": 1.25, "买入价": 43250.5, "卖出价": 43790.2, "24h量": "2.5B"},
            {"交易对": "ETH/USDT", "买入交易所": "Huobi", "卖出交易所": "Binance", "价差": 0.89, "买入价": 2650.8, "卖出价": 2674.4, "24h量": "1.8B"},
            {"交易对": "ADA/USDT", "买入交易所": "OKX", "卖出交易所": "Kraken", "价差": 2.15, "买入价": 0.485, "卖出价": 0.495, "24h量": "450M"},
            {"交易对": "SOL/USDT", "买入交易所": "Binance", "卖出交易所": "Huobi", "价差": 1.67, "买入价": 89.5, "卖出价": 91.0, "24h量": "680M"},
            {"交易对": "MATIC/USDT", "买入交易所": "Kraken", "卖出交易所": "OKX", "价差": 3.22, "买入价": 0.825, "卖出价": 0.852, "24h量": "320M"}
        ]
        
        # 过滤和排序
        filtered_data = [item for item in spread_data if item["价差"] >= min_spread]
        sorted_data = sorted(filtered_data, key=lambda x: x["价差"], reverse=True)[:top_n]
        
        if sorted_data:
            df_spread = pd.DataFrame(sorted_data)
            
            # 格式化显示
            def format_spread_row(row):
                spread_color = "🟢" if row["价差"] > 2.0 else "🟡" if row["价差"] > 1.0 else "🟠"
                return f"{spread_color} **{row['交易对']}** | {row['价差']:.2f}% | {row['买入交易所']} → {row['卖出交易所']} | ${row['买入价']:.4f} → ${row['卖出价']:.4f}"
            
            for i, row in df_spread.iterrows():
                col_left, col_right = st.columns([4, 1])
                with col_left:
                    st.markdown(format_spread_row(row))
                with col_right:
                    if st.button("执行", key=f"execute_{i}", help="模拟执行套利"):
                        st.success(f"已提交 {row['交易对']} 套利订单")
        else:
            st.info("暂无符合条件的套利机会")
    
    # 市场热力图
    st.markdown("---")
    st.subheader("🌡️ 市场热力图")
    
    heatmap_col1, heatmap_col2 = st.columns([4, 1])
    
    with heatmap_col2:
        heatmap_metric = st.selectbox("热力图指标", ["价差百分比", "交易量", "波动率"], key="heatmap_metric")
        time_range = st.selectbox("时间范围", ["1小时", "4小时", "24小时"], index=2, key="heatmap_time")
    
    with heatmap_col1:
        # 创建热力图数据
        exchanges = ["Binance", "OKX", "Huobi", "Kraken", "Coinbase"]
        symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT", "SOL/USDT", "MATIC/USDT"]
        
        # 模拟热力图数据
        import numpy as np
        np.random.seed(42)
        heatmap_data = np.random.uniform(0.1, 3.0, (len(symbols), len(exchanges)))
        
        fig_heatmap = go.Figure(data=go.Heatmap(
            z=heatmap_data,
            x=exchanges,
            y=symbols,
            colorscale='RdYlGn',
            text=[[f"{val:.2f}%" for val in row] for row in heatmap_data],
            texttemplate="%{text}",
            textfont={"size": 12},
            hoverongaps=False
        ))
        
        fig_heatmap.update_layout(
            title=f"{heatmap_metric} - {time_range}",
            xaxis_title="交易所",
            yaxis_title="交易对",
            height=400
        )
        
        st.plotly_chart(fig_heatmap, use_container_width=True)
    
    # 一键套利执行面板
    st.markdown("---")
    st.subheader("⚡ 一键套利执行")
    
    exec_col1, exec_col2, exec_col3 = st.columns([3, 2, 1])
    
    with exec_col1:
        st.markdown("**快速执行设置**")
        auto_amount = st.number_input("自动投资金额 (USDT)", min_value=100, max_value=50000, value=1000, step=100, key="auto_amount")
        max_slippage = st.slider("最大滑点容忍 (%)", 0.1, 2.0, 0.5, 0.1, key="max_slippage")
    
    with exec_col2:
        st.markdown("**风险控制**")
        stop_loss = st.number_input("止损点 (%)", min_value=-10.0, max_value=-0.1, value=-2.0, step=0.1, key="stop_loss")
        max_positions = st.number_input("最大同时持仓", min_value=1, max_value=10, value=3, key="max_positions")
    
    with exec_col3:
        st.markdown("**执行操作**")
        if st.button("🚀 启动自动套利", key="start_auto_arbitrage", help="开始自动监控和执行套利机会"):
            st.success("✅ 自动套利已启动")
            st.info(f"监控参数: 投资{auto_amount} USDT, 最大滑点{max_slippage}%, 止损{stop_loss}%")
        
        if st.button("⏹️ 停止自动套利", key="stop_auto_arbitrage"):
            st.warning("⚠️ 自动套利已停止")
    
    # 资金管理和风险控制
    st.markdown("---")
    st.subheader("💼 资金管理与风险控制")
    
    risk_col1, risk_col2, risk_col3 = st.columns(3)
    
    with risk_col1:
        st.markdown("**📊 资金分配**")
        total_capital = st.number_input("总资金 (USDT)", min_value=1000, max_value=10000000, value=100000, step=1000, key="total_capital")
        risk_per_trade = st.slider("单笔风险比例 (%)", 1, 10, 2, 1, key="risk_per_trade")
        max_daily_risk = st.slider("日最大风险 (%)", 5, 50, 20, 5, key="max_daily_risk")
        
        # 计算资金分配
        max_trade_amount = total_capital * (risk_per_trade / 100)
        daily_risk_amount = total_capital * (max_daily_risk / 100)
        
        st.metric("单笔最大金额", f"${max_trade_amount:,.0f}")
        st.metric("日风险限额", f"${daily_risk_amount:,.0f}")
    
    with risk_col2:
        st.markdown("**⚠️ 风险参数**")
        global_stop_loss = st.number_input("全局止损 (%)", min_value=-20.0, max_value=-1.0, value=-5.0, step=0.5, key="global_stop_loss")
        max_drawdown = st.number_input("最大回撤 (%)", min_value=-50.0, max_value=-5.0, value=-15.0, step=1.0, key="max_drawdown")
        correlation_limit = st.slider("相关性限制", 0.1, 1.0, 0.7, 0.1, key="correlation_limit")
        
        # 风险状态
        current_drawdown = -3.2  # 模拟当前回撤
        if current_drawdown <= max_drawdown:
            st.error(f"🚨 回撤警告: {current_drawdown:.1f}%")
        elif current_drawdown <= max_drawdown * 0.7:
            st.warning(f"⚠️ 回撤关注: {current_drawdown:.1f}%")
        else:
            st.success(f"✅ 回撤正常: {current_drawdown:.1f}%")
    
    with risk_col3:
        st.markdown("**🎯 交易规则**")
        min_profit_ratio = st.number_input("最小盈亏比", min_value=1.0, max_value=10.0, value=2.0, step=0.1, key="min_profit_ratio")
        max_open_positions = st.number_input("最大持仓数", min_value=1, max_value=20, value=5, key="max_open_positions")
        cool_down_period = st.number_input("冷却期 (分钟)", min_value=1, max_value=60, value=5, key="cool_down_period")
        
        # 当前状态
        current_positions = 2  # 模拟当前持仓
        st.metric("当前持仓", f"{current_positions}/{max_open_positions}")
        
        if current_positions >= max_open_positions:
            st.error("🚫 持仓已满")
        else:
            st.success(f"✅ 可开 {max_open_positions - current_positions} 仓")
    
    # 实时风险监控面板
    st.markdown("---")
    st.subheader("🚨 实时风险监控")
    
    risk_monitor_col1, risk_monitor_col2 = st.columns([2, 1])
    
    with risk_monitor_col1:
        # 风险指标表格
        risk_metrics = [
            {"指标": "总资金", "当前值": "$98,750", "阈值": "$100,000", "状态": "🟡 关注", "变化": "-1.25%"},
            {"指标": "日盈亏", "当前值": "+$1,250", "阈值": "-$20,000", "状态": "🟢 正常", "变化": "+1.27%"},
            {"指标": "最大回撤", "当前值": "-3.2%", "阈值": "-15.0%", "状态": "🟢 安全", "变化": "+0.8%"},
            {"指标": "持仓风险", "当前值": "2/5", "阈值": "5/5", "状态": "🟢 正常", "变化": "0"},
            {"指标": "相关性", "当前值": "0.65", "阈值": "0.70", "状态": "🟡 关注", "变化": "+0.05"}
        ]
        
        df_risk = pd.DataFrame(risk_metrics)
        st.dataframe(df_risk, use_container_width=True, hide_index=True)
    
    with risk_monitor_col2:
        st.markdown("**🔔 风险警报**")
        
        # 模拟风险警报
        alerts = [
            "🟡 BTC/USDT 相关性过高 (0.85)",
            "🟢 ETH/USDT 套利机会出现",
            "🔴 总资金接近止损线"
        ]
        
        for alert in alerts:
            st.write(alert)
        
        st.markdown("**⚡ 紧急操作**")
        if st.button("🛑 紧急止损", key="emergency_stop", help="立即关闭所有持仓"):
            st.error("🚨 紧急止损已触发")
        
        if st.button("⏸️ 暂停交易", key="pause_trading", help="暂停所有新交易"):
            st.warning("⚠️ 交易已暂停")
        
        if st.button("🔄 重置风险", key="reset_risk", help="重置风险参数"):
            st.info("ℹ️ 风险参数已重置")
    
    # 批量监控面板
    st.markdown("---")
    st.subheader("📋 批量监控管理")
    
    monitor_col1, monitor_col2 = st.columns([4, 1])
    
    with monitor_col1:
        # 监控列表
        st.markdown("**活跃监控列表**")
        
        monitor_data = [
            {"交易对": "BTC/USDT", "状态": "🟢 监控中", "触发条件": ">1.5%", "当前价差": "1.25%", "操作": "暂停"},
            {"交易对": "ETH/USDT", "状态": "🟡 等待中", "触发条件": ">1.0%", "当前价差": "0.89%", "操作": "修改"},
            {"交易对": "ADA/USDT", "状态": "🔴 已暂停", "触发条件": ">2.0%", "当前价差": "2.15%", "操作": "启动"}
        ]
        
        for i, item in enumerate(monitor_data):
            with st.container():
                item_col1, item_col2, item_col3, item_col4, item_col5 = st.columns([3, 1, 1, 1, 1])
                
                with item_col1:
                    st.write(f"**{item['交易对']}** - {item['状态']}")
                with item_col2:
                    st.write(f"触发: {item['触发条件']}")
                with item_col3:
                    st.write(f"当前: {item['当前价差']}")
                with item_col4:
                    if st.button(item['操作'], key=f"monitor_action_{i}"):
                        st.success(f"{item['操作']}操作已执行")
                with item_col5:
                    if st.button("删除", key=f"monitor_delete_{i}"):
                        st.warning(f"已删除 {item['交易对']} 监控")
    
    with monitor_col2:
        st.markdown("**添加新监控**")
        new_symbol = st.text_input("交易对", placeholder="BTC/USDT", key="new_monitor_symbol")
        new_threshold = st.number_input("触发阈值 (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1, key="new_threshold")
        
        if st.button("➕ 添加监控", key="add_monitor"):
            if new_symbol:
                st.success(f"已添加 {new_symbol} 监控 (>{new_threshold}%)")
            else:
                st.error("请输入交易对")
        
        st.markdown("**批量操作**")
        if st.button("▶️ 全部启动", key="start_all_monitors"):
            st.success("所有监控已启动")
        if st.button("⏸️ 全部暂停", key="pause_all_monitors"):
            st.warning("所有监控已暂停")
        if st.button("🗑️ 清空列表", key="clear_all_monitors"):
            st.error("监控列表已清空")

    st.markdown("---")

    st.subheader("🌊 市场深度可视化")
    depth_cols = st.columns(3)
    selected_ex = depth_cols[0].selectbox("选择交易所", options=[p.name for p in providers if isinstance(p, CEXProvider)], key="depth_exchange")
    selected_sym = depth_cols[1].text_input("输入交易对", st.session_state.selected_symbols[0], key="depth_symbol")

    if depth_cols[2].button("查询深度", key="depth_button"):
        if _validate_symbol(selected_sym):
            provider = next((p for p in providers if p.name == selected_ex), None)
            if provider:
                with st.spinner(f"正在从 {provider.name} 获取 {selected_sym} 的订单簿..."):
                    order_book = safe_run_async(provider.get_order_book(selected_sym))
                    if order_book and 'error' not in order_book:
                        st.plotly_chart(_create_depth_chart(order_book), width='stretch')
                    else:
                        display_error(f"无法获取订单簿: {order_book.get('error', '未知错误')}")

    st.markdown("---")
    with st.expander("🏢 交易所定性对比", expanded=False):
        show_comparison_view(get_config().get('qualitative_data', {}), providers)
    
    st.markdown("---")
    with st.expander("🚀 增强CCXT交易所支持", expanded=False):
        show_enhanced_ccxt_features()


def show_comparison_view(qualitative_data: dict, providers: List[BaseProvider]):
    """Displays a side-by-side comparison of qualitative data for selected exchanges."""
    if not qualitative_data:
        st.warning("未找到定性数据。")
        return

    key_to_chinese = {
        'security_measures': '安全措施', 'customer_service': '客户服务', 'platform_stability': '平台稳定性',
        'fund_insurance': '资金保险', 'regional_restrictions': '地区限制', 'withdrawal_limits': '提现限额',
        'withdrawal_speed': '提现速度', 'supported_cross_chain_bridges': '支持的跨链桥',
        'api_support_details': 'API支持详情', 'fee_discounts': '手续费折扣', 'margin_leverage_details': '杠杆交易详情',
        'maintenance_schedule': '维护计划', 'user_rating_summary': '用户评分摘要', 'tax_compliance_info': '税务合规信息',
        'deposit_networks': '充值网络', 'deposit_fees': '充值费用', 'withdrawal_networks': '提现网络',
        'margin_trading_api': '保证金交易API'
    }

    exchange_list = list(qualitative_data.keys())
    selected = st.multiselect(
        "选择要比较的交易所",
        options=exchange_list,
        default=exchange_list[:3] if len(exchange_list) >= 3 else exchange_list,
        format_func=lambda x: x.capitalize(),
        key="qualitative_multiselect"
    )

    if selected:
        comparison_data = {exch: qualitative_data[exch] for exch in selected if exch in qualitative_data}
        df = pd.DataFrame(comparison_data).rename(index=key_to_chinese)
        all_keys_df = pd.DataFrame(index=list(key_to_chinese.values()))
        df_display = all_keys_df.join(df).fillna("N/A")
        st.dataframe(df_display, width='stretch')

    with st.expander("🪙 资产转账分析"):
        cex_providers = [p for p in providers if isinstance(p, CEXProvider)]
        show_asset_transfer_view(cex_providers, providers)


def show_asset_transfer_view(cex_providers: List[CEXProvider], providers: List[BaseProvider]):
    """Displays a side-by-side comparison of transfer fees for a given asset."""
    asset = st.text_input("输入要比较的资产代码", "USDT", key="transfer_asset_input").upper()

    if st.button("比较资产转账选项", key="compare_transfers"):
        if not asset:
            st.error("请输入一个资产代码。")
            return

        with st.spinner(f"正在从所有选定的交易所获取 {asset} 的转账费用..."):
            results = safe_run_async(asyncio.gather(*[p.get_transfer_fees(asset) for p in cex_providers]))

        all_networks = set()
        processed_data = {}
        failed_providers = []

        for i, res in enumerate(results):
            provider_name = cex_providers[i].name.capitalize()
            if isinstance(res, dict) and 'error' not in res:
                withdraw_info = res.get('withdraw', {})
                processed_data[provider_name] = {}
                for network, details in withdraw_info.items():
                    all_networks.add(network)
                    fee = details.get('fee')
                    processed_data[provider_name][network] = f"{fee:.6f}".rstrip('0').rstrip('.') if fee is not None else "N/A"
            else:
                failed_providers.append(provider_name)

        if failed_providers:
            st.warning(f"无法获取以下交易所的费用数据: {', '.join(failed_providers)}。")

        if processed_data:
            df = pd.DataFrame(processed_data).reindex(sorted(list(all_networks))).fillna("不支持")
            st.subheader(f"{asset} 提现费用对比")
            st.dataframe(df, width='stretch')
        else:
            st.warning(f"未能成功获取任何交易所关于 '{asset}' 的费用数据。")

    with st.expander("📈 K线图与历史数据"):
        show_kline_view(providers)


def show_kline_view(providers: List[BaseProvider]):
    """Displays a candlestick chart for a selected symbol and exchange."""
    cex_providers = [p for p in providers if isinstance(p, CEXProvider)]
    if not cex_providers:
        st.warning("无可用CEX提供商。")
        return

    # Main controls
    col1, col2, col3, col4 = st.columns([2, 2, 1.5, 1.5])
    name = col1.selectbox("选择交易所", options=[p.name for p in cex_providers], key="kline_exchange")
    symbol = col2.text_input("输入交易对", "BTC/USDT", key="kline_symbol")
    timeframe = col3.selectbox("选择时间周期", options=['1d', '4h', '1h', '30m', '5m'], key="kline_timeframe")
    limit = col4.number_input("数据点", min_value=20, max_value=1000, value=100, key="kline_limit")
    
    # Advanced options
    with st.expander("📊 高级选项"):
        col_a, col_b = st.columns(2)
        show_volume = col_a.checkbox("显示成交量", value=True, key="show_volume")
        show_ma = col_b.checkbox("显示移动平均线", value=False, key="show_ma")
        if show_ma:
            ma_periods = st.multiselect(
                "移动平均线周期",
                options=[5, 10, 20, 50, 100, 200],
                default=[20, 50],
                key="ma_periods"
            )

    if st.button("获取K线数据", key="get_kline"):
        if _validate_symbol(symbol):
            provider = next((p for p in cex_providers if p.name == name), None)
            if provider:
                with st.spinner(f"正在从 {provider.name} 获取 {symbol} 的 {timeframe} 数据..."):
                    data = safe_run_async(provider.get_historical_data(symbol, timeframe, limit))
                    if data:
                        df = pd.DataFrame(data)
                        fig = _create_candlestick_chart(df, symbol, show_volume, ma_periods if show_ma else None)
                        st.plotly_chart(fig, width='stretch')
                    else:
                        display_error(f"无法获取 {symbol} 的K线数据。")

def show_enhanced_ccxt_features():
    """显示增强的CCXT功能"""
    st.header("🚀 增强CCXT交易所支持")
    
    # 初始化增强CCXT提供者和趋势分析器
    if 'ccxt_provider' not in st.session_state:
        st.session_state.ccxt_provider = EnhancedCCXTProvider()
    
    if 'trend_analyzer' not in st.session_state:
        st.session_state.trend_analyzer = TrendAnalyzer()
    
    ccxt_provider = st.session_state.ccxt_provider
    trend_analyzer = st.session_state.trend_analyzer
    
    # 支持的交易所信息
    with st.expander("📋 支持的免费交易所", expanded=True):
        exchanges = ccxt_provider.get_supported_exchanges()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("活跃交易所")
            active_exchanges = [ex for ex in exchanges if ex['status'] == 'active']
            if active_exchanges:
                for ex in active_exchanges:
                    st.success(f"✅ {ex['name']} ({ex['id']})")
                    st.caption(f"限制: {ex['rate_limit']}/分钟")
            else:
                st.warning("暂无活跃交易所")
        
        with col2:
            st.subheader("支持的交易对")
            symbols = ccxt_provider.get_supported_symbols()
            for symbol in symbols:
                st.info(f"📈 {symbol}")
    
    # 实时价格对比
    st.subheader("💰 多交易所实时价格对比")
    
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        selected_symbol = st.selectbox(
            "选择交易对",
            options=ccxt_provider.get_supported_symbols(),
            key="ccxt_symbol_select"
        )
    
    with col2:
        if st.button("🔄 刷新价格", key="refresh_ccxt_prices"):
            st.session_state.ccxt_refresh_trigger = time.time()
    
    with col3:
        auto_refresh = st.checkbox("自动刷新", key="ccxt_auto_refresh")
    
    # 获取价格数据
    if st.button("获取价格数据", key="get_ccxt_prices") or 'ccxt_refresh_trigger' in st.session_state:
        with st.spinner(f"正在获取 {selected_symbol} 的价格数据..."):
            try:
                tickers = safe_run_async(ccxt_provider.get_all_tickers(selected_symbol))
                
                if tickers:
                    # 创建价格对比表
                    df_data = []
                    for ticker in tickers:
                        df_data.append({
                            '交易所': ticker['exchange'].upper(),
                            '最新价格': f"${ticker['price']:.4f}" if ticker['price'] else "N/A",
                            '买入价': f"${ticker['bid']:.4f}" if ticker['bid'] else "N/A",
                            '卖出价': f"${ticker['ask']:.4f}" if ticker['ask'] else "N/A",
                            '24h变化': f"{ticker['change_24h']:.2f}%" if ticker['change_24h'] else "N/A",
                            '成交量': f"{ticker['volume']:.2f}" if ticker['volume'] else "N/A",
                            '更新时间': ticker['datetime'][:19] if ticker['datetime'] else "N/A"
                        })
                    
                    df = pd.DataFrame(df_data)
                    st.dataframe(df, use_container_width=True)
                    
                    # 价格分析
                    prices = [t['price'] for t in tickers if t['price']]
                    if len(prices) >= 2:
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("平均价格", f"${np.mean(prices):.4f}")
                        
                        with col2:
                            st.metric("最高价格", f"${max(prices):.4f}")
                        
                        with col3:
                            st.metric("最低价格", f"${min(prices):.4f}")
                        
                        with col4:
                            spread_pct = ((max(prices) - min(prices)) / min(prices)) * 100
                            st.metric("价差", f"{spread_pct:.2f}%")
                        
                        # 价格分布图
                        fig = px.bar(
                            x=[t['exchange'].upper() for t in tickers if t['price']],
                            y=prices,
                            title=f"{selected_symbol} 各交易所价格对比",
                            labels={'x': '交易所', 'y': '价格 (USD)'}
                        )
                        fig.update_layout(showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("未获取到价格数据")
                    
            except Exception as e:
                st.error(f"获取数据时出错: {str(e)}")
    
    # 套利机会分析
    st.subheader("🎯 实时套利机会")
    
    if st.button("分析套利机会", key="analyze_arbitrage"):
        with st.spinner("正在分析套利机会..."):
            try:
                opportunities = safe_run_async(ccxt_provider.calculate_arbitrage_opportunities(selected_symbol))
                
                if opportunities:
                    st.success(f"发现 {len(opportunities)} 个套利机会！")
                    
                    # 显示前5个最佳机会
                    top_opportunities = opportunities[:5]
                    
                    for i, opp in enumerate(top_opportunities, 1):
                        with st.container():
                            col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
                            
                            with col1:
                                st.write(f"**#{i}**")
                            
                            with col2:
                                st.write(f"**买入:** {opp['buy_exchange'].upper()}")
                                st.write(f"价格: ${opp['buy_price']:.4f}")
                            
                            with col3:
                                st.write(f"**卖出:** {opp['sell_exchange'].upper()}")
                                st.write(f"价格: ${opp['sell_price']:.4f}")
                            
                            with col4:
                                profit_color = "green" if opp['profit_pct'] > 0.5 else "orange"
                                st.markdown(f"<span style='color:{profit_color}'>**+{opp['profit_pct']:.2f}%**</span>", unsafe_allow_html=True)
                                st.write(f"${opp['profit_abs']:.4f}")
                            
                            st.divider()
                    
                    # 套利机会图表
                    if len(opportunities) > 1:
                        fig = px.scatter(
                            x=[f"{opp['buy_exchange']} → {opp['sell_exchange']}" for opp in top_opportunities],
                            y=[opp['profit_pct'] for opp in top_opportunities],
                            size=[opp['profit_abs'] for opp in top_opportunities],
                            title="套利机会分布",
                            labels={'x': '交易路径', 'y': '利润率 (%)'}
                        )
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("当前没有发现明显的套利机会")
                    
            except Exception as e:
                st.error(f"分析套利机会时出错: {str(e)}")
    
    # 市场摘要
    with st.expander("📊 市场摘要"):
        if st.button("获取市场摘要", key="get_market_summary"):
            with st.spinner("正在生成市场摘要..."):
                try:
                    summary = safe_run_async(ccxt_provider.get_market_summary(selected_symbol))
                    
                    if 'error' not in summary:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.metric("参与交易所", summary['exchanges_count'])
                            st.metric("平均价格", f"${summary['avg_price']:.4f}")
                            st.metric("总成交量", f"{summary['total_volume']:.2f}")
                        
                        with col2:
                            st.metric("最高价格", f"${summary['max_price']:.4f}")
                            st.metric("最低价格", f"${summary['min_price']:.4f}")
                            st.metric("价格差异", f"{summary['price_spread_pct']:.2f}%")
                        
                        st.info(f"数据更新时间: {summary['timestamp'][:19]}")
                    else:
                        st.error(summary['error'])
                        
                except Exception as e:
                    st.error(f"获取市场摘要时出错: {str(e)}")
    
    # 价格趋势分析
    st.subheader("📈 价格趋势分析")
    
    col1, col2 = st.columns(2)
    
    with col1:
        trend_symbol = st.selectbox(
            "选择分析币种",
            ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "SOL/USDT"],
            key="trend_symbol"
        )
    
    with col2:
        trend_period = st.selectbox(
            "时间周期",
            ["1小时", "6小时", "24小时", "7天"],
            key="trend_period"
        )
    
    if st.button("📊 生成趋势分析", key="generate_trend"):
        try:
            # 模拟添加历史价格数据
            import random
            import datetime
            
            base_price = 50000 if "BTC" in trend_symbol else 3000
            
            for i in range(24):  # 添加24小时的数据
                timestamp = datetime.datetime.now() - datetime.timedelta(hours=23-i)
                price = base_price * (1 + random.uniform(-0.05, 0.05))
                trend_analyzer.add_price_data(trend_symbol, "binance", price, timestamp)
                trend_analyzer.add_price_data(trend_symbol, "okx", price * (1 + random.uniform(-0.002, 0.002)), timestamp)
            
            # 获取趋势数据
            trend_data = trend_analyzer.get_price_trend(trend_symbol, hours=24)
            
            if trend_data:
                # 显示趋势图表
                fig = trend_analyzer.create_price_trend_chart(trend_symbol, hours=24)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                
                # 显示趋势统计
                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                
                with col1:
                    current_price = trend_data[-1]['price']
                    st.metric("当前价格", f"${current_price:.2f}")
                
                with col2:
                    price_change = ((trend_data[-1]['price'] - trend_data[0]['price']) / trend_data[0]['price']) * 100
                    st.metric("24h变化", f"{price_change:.2f}%", delta=f"{price_change:.2f}%")
                
                with col3:
                    prices = [d['price'] for d in trend_data]
                    volatility = (max(prices) - min(prices)) / min(prices) * 100
                    st.metric("波动率", f"{volatility:.2f}%")
                
                with col4:
                    trend_direction = "上涨" if price_change > 0 else "下跌" if price_change < 0 else "横盘"
                    st.metric("趋势方向", trend_direction)
                
                # 波动率对比图
                st.subheader("📊 交易所波动率对比")
                volatility_fig = trend_analyzer.create_volatility_comparison(["binance", "okx"], [trend_symbol])
                if volatility_fig:
                    st.plotly_chart(volatility_fig, use_container_width=True)
                
            else:
                st.warning("暂无趋势数据")
                
        except Exception as e:
            st.error(f"生成趋势分析失败: {str(e)}")
    
    # 套利机会趋势
    st.subheader("💰 套利机会趋势")
    
    if st.button("📈 查看套利趋势", key="arbitrage_trend"):
        try:
            arbitrage_trends = trend_analyzer.get_arbitrage_trends(hours=24)
            
            if arbitrage_trends:
                # 显示套利机会统计
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    avg_opportunity = sum(t['max_spread'] for t in arbitrage_trends) / len(arbitrage_trends)
                    st.metric("平均套利机会", f"{avg_opportunity:.2f}%")
                
                with col2:
                    max_opportunity = max(t['max_spread'] for t in arbitrage_trends)
                    st.metric("最大套利机会", f"{max_opportunity:.2f}%")
                
                with col3:
                    profitable_count = len([t for t in arbitrage_trends if t['max_spread'] > 0.5])
                    st.metric("盈利机会数", f"{profitable_count}")
                
                # 显示套利趋势表格
                st.dataframe(
                    arbitrage_trends,
                    use_container_width=True
                )
            else:
                st.info("暂无套利趋势数据")
                
        except Exception as e:
            st.error(f"获取套利趋势失败: {str(e)}")

def main():
    """Main function to run the Streamlit application."""
    config = get_config()
    init_session_state(config)

    sidebar_controls()

    providers = get_providers(config, st.session_state)
    if not providers:
        st.error("没有可用的数据提供商。请在侧边栏中选择交易所或检查配置。")
        st.info("💡 提示：请在侧边栏中选择至少一个交易所来开始使用。")
        return

    engine = ArbitrageEngine(providers, config.get('arbitrage', {}))

    show_dashboard(engine, providers)

    # Auto refresh footer
    if st.session_state.get('auto_refresh_enabled', False):
        interval = st.session_state.get('auto_refresh_interval', 10)
        st.info(f"🔄 自动刷新已启用，每 {interval} 秒刷新一次")
        time.sleep(interval)
        st.rerun()

if __name__ == "__main__":
    main()
