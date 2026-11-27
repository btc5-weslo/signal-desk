"""Deterministic toy OHLCV for unit tests (never passed off as market data)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

_COLUMNS = ["open_time", "close_time", "open", "high", "low", "close", "volume", "source"]

DELTAS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def _utc(x) -> pd.Timestamp:
    """Normalize to UTC. Never pass tz= into Timestamp() on an already-aware value."""
    ts = pd.Timestamp(x)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def make_bars(
    start: datetime,
    n: int = 0,
    *,
    timeframe: str = "1d",
    open_px: float = 100.0,
    path: list[tuple[float, float, float, float]] | None = None,
    closes: list[float] | None = None,
) -> pd.DataFrame:
    """Build n toy bars starting at ``start``.

    If ``path`` or ``closes`` is provided, its length is the bar count (so
    callers may pass ``n=0`` and still get a series). An empty request
    returns a correctly-columned empty frame, not an error.
    """
    if path is not None:
        n = len(path)
    elif closes is not None:
        n = len(closes)
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    if n == 0:
        return pd.DataFrame(columns=_COLUMNS)

    if timeframe not in DELTAS:
        raise ValueError(f"unknown timeframe {timeframe}")
    delta = DELTAS[timeframe]
    if closes is not None and len(closes) < n:
        raise ValueError("closes is shorter than n")
    rows = []
    for i in range(n):
        ot = start + i * delta
        ct = ot + delta
        if path is not None:
            o, h, l, c = path[i]
        elif closes is not None:
            c = closes[i]
            o = closes[i - 1] if i else c
            h = max(o, c)
            l = min(o, c)
        else:
            o = c = open_px
            h = open_px * 1.01
            l = open_px * 0.99
        rows.append(
            {
                "open_time": _utc(ot),
                "close_time": _utc(ct),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 1_000.0,
                "source": "toy",
            }
        )
    return pd.DataFrame(rows)
