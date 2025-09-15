import streamlit as st

def init_session_state():
    """Initializes the session state with default values."""

    # Configuration state
    if 'exchanges' not in st.session_state:
        st.session_state.exchanges = ['binance', 'coinbase', 'kraken']
    if 'symbols' not in st.session_state:
        st.session_state.symbols = ['BTC/USDT', 'ETH/USDT']

    # Data state
    if 'ticker_data' not in st.session_state:
        st.session_state.ticker_data = {} # e.g., {'BTC/USDT': [data1, data2]}
    if 'order_book_data' not in st.session_state:
        st.session_state.order_book_data = {}

    # App state
    if 'running' not in st.session_state:
        st.session_state.running = False

def get_provider_manager():
    """
    A helper function to get the provider manager,
    potentially from a cached resource.
    """
    # This will be implemented later
    pass

# We can later add a unified data model here, e.g., using Pydantic
# from pydantic import BaseModel
# class Ticker(BaseModel):
#     ...
