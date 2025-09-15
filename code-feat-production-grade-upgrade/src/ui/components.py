import streamlit as st

def sidebar_controls():
    """
    Defines the controls in the sidebar and updates session_state.
    The main app will react to changes in st.session_state.
    """
    st.sidebar.header("⚙️ 配置")
    
    # --- Welcome Message for Demo Mode ---
    if st.session_state.get('demo_mode', True):
        st.sidebar.success(
            "🎯 **欢迎体验演示模式！**\n\n"
            "您可以立即探索所有功能，无需配置API密钥。\n\n"
            "💡 配置API密钥后可获取真实市场数据。",
            icon="🚀"
        )

    # --- Demo Mode Toggle ---
    # This toggle now acts as a read-only status indicator. It is always disabled,
    # and its state is determined automatically by the presence of API keys.
    keys_provided = bool(st.session_state.get('api_keys'))
    st.sidebar.toggle(
        "🚀 演示模式",
        value=not keys_provided,
        key='demo_mode',
        help="这是一个状态指示器。当您提供API密钥时，它会自动关闭。",
        disabled=True  # The toggle is always disabled, making it read-only.
    )
    st.sidebar.divider()

    # --- Exchange Selection ---
    EXCHANGES = ['binance', 'okx', 'bybit', 'kucoin', 'gate', 'mexc', 'bitget', 'htx']
    st.sidebar.multiselect(
        "选择中心化交易所",
        options=EXCHANGES,
        key='selected_exchanges', # This key links the widget to session_state
        help="选择用于行情和套利分析的中心化交易所。"
    )

    # --- API Key Management ---
    st.sidebar.subheader("🔑 API密钥管理")
    if st.session_state.get('demo_mode', True):
        st.sidebar.info(
            "🎯 **可选配置**\n\n"
            "演示模式下无需API密钥即可体验所有功能。\n\n"
            "配置后可获取真实市场数据进行分析。",
            icon="💡"
        )
    st.sidebar.caption("API密钥存储在会话状态中，不会被永久保存。")

    # Dynamically create input fields for selected exchanges
    if 'api_keys' not in st.session_state:
        st.session_state.api_keys = {}

    for ex_id in st.session_state.selected_exchanges:
        with st.sidebar.expander(f"{ex_id.capitalize()} API密钥"):
            api_key = st.text_input(f"{ex_id} API Key", key=f"api_key_{ex_id}", value=st.session_state.api_keys.get(ex_id, {}).get('apiKey', ''))
            api_secret = st.text_input(f"{ex_id} API Secret", type="password", key=f"api_secret_{ex_id}", value=st.session_state.api_keys.get(ex_id, {}).get('secret', ''))

            # Update session state as user types
            if api_key and api_secret:
                 st.session_state.api_keys[ex_id] = {'apiKey': api_key, 'secret': api_secret}
            elif ex_id in st.session_state.api_keys:
                 # Clear keys if fields are emptied
                 del st.session_state.api_keys[ex_id]

    st.sidebar.divider()

    # --- Symbol Selection ---
    st.sidebar.multiselect(
        "选择CEX/DEX交易对",
        options=['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ETH/BTC', 'WETH/USDC', 'WBTC/WETH'],
        default=['BTC/USDT', 'ETH/USDT'],
        key='selected_symbols',
        help="选择要在不同交易所之间跟踪的交易对。"
    )

    # --- Bridge Symbol Selection ---
    st.sidebar.text_input(
        "跨链桥交易对",
        value='BTC.BTC/ETH.ETH',
        key='bridge_symbol',
        help="为Thorchain输入一个跨链交易对，例如 'BTC.BTC/ETH.ETH'。"
    )

    # --- Arbitrage Settings ---
    st.sidebar.subheader("套利设置")
    st.sidebar.number_input(
        "利润阈值 (%)",
        min_value=0.01,
        max_value=10.0,
        value=0.2,
        step=0.01,
        key='arbitrage_threshold',
        help="设置触发警报的最低利润百分比。"
    )

    # --- Refresh Control ---
    st.sidebar.subheader("显示控制")
    if st.sidebar.button("🔄 强制刷新所有数据"):
        # Clearing cached resources will force them to rerun
        st.cache_resource.clear()
        st.rerun()

    st.sidebar.toggle("自动刷新", key='auto_refresh_enabled', value=False)
    st.sidebar.number_input(
        "刷新间隔 (秒)",
        min_value=5,
        max_value=120,
        value=10,
        step=5,
        key='auto_refresh_interval',
        disabled=not st.session_state.get('auto_refresh_enabled', False)
    )

def display_error(message: str):
    """A standardized way to display errors."""
    st.error(message, icon="🚨")

def display_warning(message: str):
    """A standardized way to display warnings."""
    st.warning(message, icon="⚠️")
