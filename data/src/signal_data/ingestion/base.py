"""Shared fetch types and DataFrame builders for sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from signal_data.schema import FetchAttempt
from signal_data.timeutil import close_time_from_open, equity_session_times, to_utc


@dataclass
class RawFetch:
    bars: pd.DataFrame
    attempts: list[FetchAttempt] = field(default_factory=list)
    source: str | None = None
    history_limitations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def empty_bars() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["open_time", "close_time", "open", "high", "low", "close", "volume", "source", "is_stale"]
    )


def make_bars(
    open_times,
    opens,
    highs,
    lows,
    closes,
    volumes,
    *,
    source: str,
    timeframe: str,
    asset_class: str,
) -> pd.DataFrame:
    ot = pd.to_datetime(open_times, utc=True)
    if asset_class == "equity" and timeframe == "1d":
        close_times = [equity_session_times(t, "1d")[1] for t in ot]
        # also normalize open_time to official cash open
        ot = pd.to_datetime([equity_session_times(t, "1d")[0] for t in ot], utc=True)
    else:
        from signal_data.timeutil import TF_DELTA

        close_times = ot + TF_DELTA[timeframe]
    def _num(values) -> pd.Series:
        # pandas 3 may return a ndarray from to_numeric; wrap so fillna works.
        return pd.Series(pd.to_numeric(values, errors="coerce"), dtype="float64")

    df = pd.DataFrame(
        {
            "open_time": ot,
            "close_time": pd.to_datetime(close_times, utc=True),
            "open": _num(opens),
            "high": _num(highs),
            "low": _num(lows),
            "close": _num(closes),
            "volume": _num(volumes).fillna(0.0),
            "source": source,
        }
    )
    return df


def failed(source: str, error: str, *, notes: list[str] | None = None) -> FetchAttempt:
    return FetchAttempt(source=source, ok=False, bars=0, error=error, notes=list(notes or []))


def ok_attempt(source: str, n: int, *, notes: list[str] | None = None) -> FetchAttempt:
    return FetchAttempt(source=source, ok=True, bars=n, error=None, notes=list(notes or []))
