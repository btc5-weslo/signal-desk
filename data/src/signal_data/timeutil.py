"""UTC time helpers and bar close-time conventions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

UTC = timezone.utc
ET = ZoneInfo("America/New_York")

TF_DELTA = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def to_utc(ts: datetime | pd.Timestamp | str) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def to_utc_datetime(ts: datetime | pd.Timestamp | str) -> datetime:
    t = to_utc(ts)
    return t.to_pydatetime()


def now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def close_time_from_open(open_time: datetime | pd.Timestamp, timeframe: str) -> pd.Timestamp:
    """Default close = open + timeframe length (crypto / FX / generic)."""
    if timeframe not in TF_DELTA:
        raise ValueError(f"unknown timeframe {timeframe}")
    return to_utc(open_time) + TF_DELTA[timeframe]


def equity_session_times(session_date, timeframe: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """RTH conventions for US equities.

    Daily bars: 09:30–16:00 America/New_York on the session date.
    Intraday: open_time is the bar open in ET, close is open + timeframe.
    """
    d = pd.Timestamp(session_date)
    if d.tzinfo is not None:
        d_et = d.tz_convert(ET)
    else:
        d_et = d.tz_localize(ET)
    if timeframe == "1d":
        open_time = pd.Timestamp(year=d_et.year, month=d_et.month, day=d_et.day, hour=9, minute=30, tz=ET).tz_convert("UTC")
        close_time = pd.Timestamp(year=d_et.year, month=d_et.month, day=d_et.day, hour=16, minute=0, tz=ET).tz_convert("UTC")
        return open_time, close_time
    open_time = to_utc(session_date)
    return open_time, close_time_from_open(open_time, timeframe)


def bars_fully_closed(df: pd.DataFrame, as_of: datetime | pd.Timestamp | None = None) -> pd.DataFrame:
    """Drop any bar whose close_time is after as_of (default: now UTC). Never keep a forming bar."""
    if df.empty:
        return df
    cut = to_utc(as_of) if as_of is not None else now_utc()
    ct = pd.to_datetime(df["close_time"], utc=True)
    return df.loc[ct <= cut].copy()
