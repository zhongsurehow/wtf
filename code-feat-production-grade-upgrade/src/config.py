import streamlit as st
from .config_loader import load_app_config, ConfigError

def load_config() -> dict:
    """
    Loads the application configuration using the dedicated loader.
    Handles exceptions and displays errors in the Streamlit UI.
    """
    try:
        # The loader function is now UI-agnostic
        return load_app_config()
    except ConfigError as e:
        # UI-specific error handling is kept separate
        st.error(f"配置加载失败 (Configuration Load Failed): {e}")
        st.info("部分功能可能无法使用。请检查您的 .env 或 YAML 配置文件。")

        # Return a safe, default configuration to allow the app to run
        return {
            'db_dsn': None,
            'rpc_urls': {
                "ethereum": "https://eth.llamarpc.com",
            },
            'api_keys': {},
            'arbitrage': {
                'threshold': 0.2,
                'fees': {},
                'default_symbols': {
                    'bridge': 'BTC.BTC/ETH.ETH',
                    'dex': 'WETH/USDC'
                }
            },
            'qualitative_data': {}
        }
