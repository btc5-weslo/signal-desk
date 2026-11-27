"""Synthetic OHLCV generators for tests and smoke runs.

All data produced here is SYNTHETIC. It is not market data, and results on it
must not be reported as accuracy or returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signal_quant.bars import TF_MINUTES


def make_synthetic_ohlcv(
    n: int = 400,
    *,
    start: str = "2024-01-01",
    timeframe: str = "15m",
    seed: int = 7,
    process: str = "trend",
    start_price: float = 100.0,
) -> pd.DataFrame:
    """Build a UTC-aligned OHLCV frame.

    ``process`` is one of ``trend``, ``range``, ``breakout`` (range then a drift shift).
    """
    if timeframe not in TF_MINUTES:
        raise ValueError(timeframe)
    rng = np.random.default_rng(seed)
    freq = f"{TF_MINUTES[timeframe]}min"
    idx = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    if process == "trend":
        drift = 0.0004
        noise = 0.003
        rets = drift + noise * rng.normal(size=n)
    elif process == "range":
        # Tight two-sided noise plus a few short excursions after warmup so
        # RSI and Bollinger can tag a band while ADX stays in a range regime
        # (H2 also blocks high-vol). Lets the lookahead gate observe a real emit.
        rets = 0.0006 * rng.normal(size=n)
        # Repeat the short excursion every 60 bars after warmup so a longer
        # series still has honest RSI / Bollinger extremes (same shape as the
        # original 120/180/240/300 pattern). Strategy parameters are unchanged.
        start, sign = 120, -1.0
        while start + 30 < n:
            rets[start : start + 15] = sign * 0.0016
            rets[start + 15 : start + 30] = -sign * 0.0013
            start += 60
            sign *= -1.0
    elif process == "breakout":
        mid = n // 2
        rets = 0.0015 * rng.normal(size=n)
        rets[:mid] = 0.85 * np.r_[0.0, np.diff(np.cumsum(rets[:mid]) * 0)] + 0.002 * rng.normal(size=mid)
        # quieter range then a positive drift
        rets[:mid] = 0.0012 * rng.normal(size=mid)
        rets[mid:] = 0.0008 + 0.002 * rng.normal(size=n - mid)
    else:
        raise ValueError(process)
    close = start_price * np.exp(np.cumsum(rets))
    close = np.maximum(close, 1e-6)
    # Causal-looking OHLC: open is previous close; high/low contain close.
    open_ = np.empty_like(close)
    open_[0] = start_price
    open_[1:] = close[:-1]
    wick_vol = 0.0006 if process == "range" else 0.0015
    wick = np.abs(rng.normal(0.0, wick_vol, size=n)) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    low = np.maximum(low, 1e-6)
    volume = rng.uniform(100.0, 1000.0, size=n)
    if process == "breakout":
        volume[n // 2 :] *= 2.0
    out = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    # Index and close_time are the bar close (UTC). open_time is inferred from the TF.
    out["close_time"] = idx
    out["open_time"] = idx - pd.Timedelta(minutes=TF_MINUTES[timeframe])
    out["source"] = "synthetic"
    return out
