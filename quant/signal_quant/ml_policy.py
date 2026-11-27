"""Where ML meta-models may be fit (Lead Architect, final v1).

Crypto: ML may be fit on all v1 timeframes (15m, 1h, 4h, 1d).
Equities and FX: fit on 1d only. Their 4h series is resampled from yfinance 1h
data (~2 years of history), and 15m / 1h yfinance history is shorter still.
Equity / FX 15m, 1h, and 4h are parameter-free rule confirmations and must be
flagged ``insufficient_oos_history``.
"""

from __future__ import annotations

ML_FIT_ALLOWED = {
    ("crypto", "15m"),
    ("crypto", "1h"),
    ("crypto", "4h"),
    ("crypto", "1d"),
    ("equity", "1d"),
    ("fx", "1d"),
}

INSUFFICIENT_OOS_HISTORY = {
    ("equity", "15m"),
    ("equity", "1h"),
    ("equity", "4h"),
    ("fx", "15m"),
    ("fx", "1h"),
    ("fx", "4h"),
}

FLAG = "insufficient_oos_history"


def ml_fit_allowed(asset_class: str, timeframe: str) -> bool:
    return (str(asset_class), str(timeframe)) in ML_FIT_ALLOWED


def insufficient_oos_history(asset_class: str, timeframe: str) -> bool:
    return (str(asset_class), str(timeframe)) in INSUFFICIENT_OOS_HISTORY


def policy_flags(asset_class: str, timeframe: str) -> dict:
    short = insufficient_oos_history(asset_class, timeframe)
    return {
        "ml_fit_allowed": ml_fit_allowed(asset_class, timeframe) and not short,
        FLAG: short,
        "rule_only": short or not ml_fit_allowed(asset_class, timeframe),
    }
