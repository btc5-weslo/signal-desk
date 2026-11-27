"""Canonical symbol mapping for the v1 universe."""

import pytest

from signal_data.symbols import (
    SYMBOLS,
    SymbolError,
    asset_class_of,
    to_canonical,
    to_source,
    universe_symbols,
)


@pytest.mark.parametrize(
    "raw, canonical",
    [
        ("BTC/USDT", "BTC-USDT"),
        ("BTCUSDT", "BTC-USDT"),
        ("btc-usdt", "BTC-USDT"),
        ("BTC-USD", "BTC-USDT"),
        ("BTC/USD", "BTC-USDT"),
        ("ETH-USD", "ETH-USDT"),
        ("ETHUSD", "ETH-USDT"),
        ("SOLUSDT", "SOL-USDT"),
        ("BNB/USDT", "BNB-USDT"),
        ("xrp-usd", "XRP-USDT"),
        ("EURUSD=X", "EURUSD"),
        ("EUR/USD", "EURUSD"),
        ("EUR-USD", "EURUSD"),
        ("EURUSD", "EURUSD"),
        ("GBPUSD=X", "GBPUSD"),
        ("USDJPY=X", "USDJPY"),
        ("AUD/USD", "AUDUSD"),
        ("AAPL", "AAPL"),
        ("aapl", "AAPL"),
        ("aapl.us", "AAPL"),
        ("MSFT.US", "MSFT"),
        ("SPY", "SPY"),
        ("NVDA", "NVDA"),
    ],
)
def test_to_canonical(raw, canonical):
    assert to_canonical(raw) == canonical


@pytest.mark.parametrize(
    "canonical, source, expected",
    [
        ("BTC-USDT", "ccxt", "BTC/USDT"),
        ("BTC-USDT", "binance", "BTC/USDT"),
        ("BTC-USDT", "ccxt:binance", "BTC/USDT"),
        ("BTC-USDT", "kraken", "BTC/USDT"),
        ("BTC-USDT", "coinbase", "BTC/USD"),
        ("ETH-USDT", "coinbaseexchange", "ETH/USD"),
        ("AAPL", "yfinance", "AAPL"),
        ("EURUSD", "yfinance", "EURUSD=X"),
        ("USDJPY", "yahoo", "USDJPY=X"),
        ("AAPL", "stooq", "aapl.us"),
        ("SPY", "stooq", "spy.us"),
        ("EURUSD", "frankfurter", "EUR/USD"),
        ("USDJPY", "ecb", "USD/JPY"),
        ("BTC-USDT", "yfinance", "BTC-USD"),
    ],
)
def test_to_source(canonical, source, expected):
    assert to_source(canonical, source) == expected


def test_universe_list_exported():
    assert list(SYMBOLS) == universe_symbols()
    assert SYMBOLS[0] == "BTC-USDT"
    assert "AAPL" in SYMBOLS and "EURUSD" in SYMBOLS
    assert all("/" not in s for s in SYMBOLS)
    assert len(SYMBOLS) == 5 + 8 + 4


def test_asset_class_of():
    assert asset_class_of("BTC/USDT") == "crypto"
    assert asset_class_of("AAPL") == "equity"
    assert asset_class_of("EURUSD=X") == "fx"


def test_unknown_symbol_raises():
    with pytest.raises(SymbolError):
        to_canonical("DOGEUSDT")
    with pytest.raises(SymbolError):
        to_source("AAPL", "not-a-vendor")
