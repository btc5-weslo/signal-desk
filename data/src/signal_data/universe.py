"""Locked v1 market universe and source routing."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Instrument:
    symbol: str  # storage symbol, no slashes: BTC-USDT, AAPL, EURUSD
    asset_class: str  # crypto|equity|fx
    display: str
    ccxt_symbol: str | None = None  # e.g. BTC/USDT
    yfinance_symbol: str | None = None
    stooq_symbol: str | None = None
    frankfurter_base: str | None = None
    frankfurter_quote: str | None = None


CRYPTO: tuple[Instrument, ...] = (
    Instrument("BTC-USDT", "crypto", "BTC/USDT", ccxt_symbol="BTC/USDT"),
    Instrument("ETH-USDT", "crypto", "ETH/USDT", ccxt_symbol="ETH/USDT"),
    Instrument("SOL-USDT", "crypto", "SOL/USDT", ccxt_symbol="SOL/USDT"),
    Instrument("BNB-USDT", "crypto", "BNB/USDT", ccxt_symbol="BNB/USDT"),
    Instrument("XRP-USDT", "crypto", "XRP/USDT", ccxt_symbol="XRP/USDT"),
)

EQUITIES: tuple[Instrument, ...] = tuple(
    Instrument(s, "equity", s, yfinance_symbol=s, stooq_symbol=f"{s.lower()}.us")
    for s in ("SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META")
)

FOREX: tuple[Instrument, ...] = (
    Instrument("EURUSD", "fx", "EURUSD", yfinance_symbol="EURUSD=X", frankfurter_base="EUR", frankfurter_quote="USD"),
    Instrument("GBPUSD", "fx", "GBPUSD", yfinance_symbol="GBPUSD=X", frankfurter_base="GBP", frankfurter_quote="USD"),
    Instrument("USDJPY", "fx", "USDJPY", yfinance_symbol="USDJPY=X", frankfurter_base="USD", frankfurter_quote="JPY"),
    Instrument("AUDUSD", "fx", "AUDUSD", yfinance_symbol="AUDUSD=X", frankfurter_base="AUD", frankfurter_quote="USD"),
)

UNIVERSE: tuple[Instrument, ...] = CRYPTO + EQUITIES + FOREX
TIMEFRAMES: tuple[str, ...] = ("15m", "1h", "4h", "1d")

# Documented free-source history limits (yfinance, as commonly observed).
# These are recorded in the data-quality report; they are not invented bars.
YFINANCE_INTRADAY_LIMITS = {
    "15m": "yfinance typically provides about 60 days of 15m history",
    "1h": "yfinance typically provides about 730 days of 60m/1h history",
    "4h": "yfinance has no native 4h interval; 4h is resampled from 1h (closed bars only). 1h history is typically ~730 days",
    "1d": "yfinance daily history usually covers many years for liquid names",
}

STOOQ_LIMITS = {
    "15m": "Stooq fallback is daily only in v1; 15m is not available from this fallback",
    "1h": "Stooq fallback is daily only in v1; 1h is not available from this fallback",
    "4h": "Stooq fallback is daily only in v1; 4h is not available from this fallback",
    "1d": "Stooq daily equities are used only if yfinance fails",
}

FRANKFURTER_LIMITS = {
    "15m": "Frankfurter/ECB provides daily reference rates only; no intraday",
    "1h": "Frankfurter/ECB provides daily reference rates only; no intraday",
    "4h": "Frankfurter/ECB provides daily reference rates only; no intraday",
    "1d": "Frankfurter/ECB daily rates are official reference rates, not exchange OHLC (O=H=L=C, volume=0)",
}


def get_instrument(symbol: str) -> Instrument:
    key = symbol.replace("/", "-").upper()
    # accept BTC/USDT or btc-usdt
    for inst in UNIVERSE:
        if inst.symbol == key or inst.symbol == symbol or inst.display.replace("/", "-") == key:
            return inst
        if inst.yfinance_symbol and inst.yfinance_symbol.upper() == symbol.upper():
            return inst
        if inst.ccxt_symbol and inst.ccxt_symbol.replace("/", "-") == key:
            return inst
    raise KeyError(f"symbol {symbol!r} is not in the locked v1 universe")


def instruments_by_class(asset_class: str) -> tuple[Instrument, ...]:
    return tuple(i for i in UNIVERSE if i.asset_class == asset_class)
