"""Official multi-timeframe closed-bar loader.

    from signal_data.bars import load_closed

    frames = load_closed(symbol, timeframes, as_of, lookback_bars)

Each frame is truncated at ``as_of`` (close_time <= as_of), stale bars are
dropped by default, and the ``source`` column is preserved. This module
does not start ingestion or touch the network.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from signal_data.store import get_candles
from signal_data.timeutil import to_utc


def load_closed(
    symbol: str,
    timeframes,
    as_of: datetime | pd.Timestamp,
    lookback_bars: int,
    *,
    data_dir: Path | str | None = None,
    store_dir: Path | str | None = None,
    drop_stale: bool = True,
) -> dict[str, pd.DataFrame]:
    """Load closed bars for one or more timeframes, truncated at ``as_of``.

    Parameters
    ----------
    symbol:
        Any form accepted by ``to_canonical``.
    timeframes:
        A timeframe string or an iterable of ``15m`` / ``1h`` / ``4h`` / ``1d``.
    as_of:
        Inclusive UTC close cut. Higher-timeframe frames contain only fully
        closed bars (``close_time <= as_of``).
    lookback_bars:
        Keep at most this many trailing bars on each timeframe.
    """
    if isinstance(timeframes, str):
        tfs = [timeframes]
    else:
        tfs = list(timeframes)
    if lookback_bars < 1:
        raise ValueError("lookback_bars must be >= 1")
    cut = to_utc(as_of)
    out: dict[str, pd.DataFrame] = {}
    for tf in tfs:
        try:
            df = get_candles(symbol, tf, data_dir=data_dir, store_dir=store_dir, drop_stale=drop_stale)
        except FileNotFoundError:
            out[tf] = pd.DataFrame(
                columns=["open_time", "close_time", "open", "high", "low", "close", "volume", "source"]
            )
            continue
        if df is None or df.empty:
            out[tf] = df.iloc[0:0] if df is not None else pd.DataFrame()
            continue
        work = df.copy()
        work["close_time"] = pd.to_datetime(work["close_time"], utc=True)
        work = work.loc[work["close_time"] <= cut].copy()
        if lookback_bars and len(work) > lookback_bars:
            work = work.tail(int(lookback_bars))
        out[tf] = work.reset_index(drop=True)
    return out
