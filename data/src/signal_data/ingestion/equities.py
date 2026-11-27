"""Equity OHLCV: yfinance first, Stooq daily as fallback.

yfinance 4h is not a native interval; it is resampled from 1h using only
fully closed buckets (real aggregation, not synthesized prices). Intraday
history limits are recorded in the quality report, not papered over.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from signal_data.ingestion.base import RawFetch, empty_bars, failed, make_bars, ok_attempt
from signal_data.symbols import to_source
from signal_data.timeutil import to_utc
from signal_data.resample import resample_closed
from signal_data.universe import Instrument, YFINANCE_INTRADAY_LIMITS, STOOQ_LIMITS

YF_INTERVAL = {"15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d"}
_USER_AGENT = "signal-data/0.1 (research; +https://localhost)"


def _resample_ohlcv_1h_to_4h(df: pd.DataFrame, *, asset_class: str = "equity") -> pd.DataFrame:
    """Delegate to the public ``resample_closed`` (complete buckets only)."""
    return resample_closed(df, "4h", asset_class=asset_class, source_timeframe="1h")



def fetch_yfinance_equity(
    instrument: Instrument,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> RawFetch:
    limitations = [YFINANCE_INTRADAY_LIMITS[timeframe]]
    ticker = to_source(instrument.symbol, "yfinance")
    interval = YF_INTERVAL[timeframe]
    try:
        import yfinance as yf
    except Exception as exc:
        return RawFetch(empty_bars(), attempts=[failed("yfinance", f"import failed: {exc}")], errors=[str(exc)], history_limitations=limitations)

    try:
        # auto_adjust=True so splits/dividends are applied consistently.
        df = yf.download(
            ticker,
            start=to_utc(start).tz_convert(None),
            end=(to_utc(end) + timedelta(days=1)).tz_convert(None),
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as exc:
        return RawFetch(
            empty_bars(),
            attempts=[failed("yfinance", f"{type(exc).__name__}: {exc}")],
            errors=[str(exc)],
            history_limitations=limitations,
        )

    if df is None or df.empty:
        return RawFetch(
            empty_bars(),
            attempts=[failed("yfinance", "download returned no rows")],
            history_limitations=limitations,
        )

    # yfinance may return MultiIndex columns when a single ticker is used
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]).lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]

    required = {"open", "high", "low", "close"}
    if not required.issubset(set(df.columns)):
        return RawFetch(
            empty_bars(),
            attempts=[failed("yfinance", f"missing OHLC columns: {list(df.columns)}")],
            history_limitations=limitations,
        )

    idx = pd.to_datetime(df.index, utc=True)
    vol = df["volume"] if "volume" in df.columns else 0.0
    bars = make_bars(
        idx, df["open"], df["high"], df["low"], df["close"], vol,
        source="yfinance", timeframe=("1h" if timeframe == "4h" else timeframe),
        asset_class="equity",
    )
    notes = []
    if timeframe == "4h":
        bars = _resample_ohlcv_1h_to_4h(bars)
        notes.append("4h resampled from yfinance 1h; incomplete trailing bucket dropped")
        # fix close_time already set
    attempts = [ok_attempt("yfinance", len(bars), notes=notes)]
    warnings = list(notes)
    return RawFetch(bars, attempts=attempts, source="yfinance", history_limitations=limitations, warnings=warnings)


def fetch_stooq_daily(instrument: Instrument, start: datetime, end: datetime) -> RawFetch:
    limitations = [STOOQ_LIMITS["1d"]]
    import requests

    code = to_source(instrument.symbol, "stooq")
    url = f"https://stooq.com/q/d/l/?s={code}&i=d"
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        text = resp.text.strip()
        if not text or "No data" in text or not text.lower().startswith("date"):
            return RawFetch(
                empty_bars(),
                attempts=[failed("stooq", f"no daily data for {code}")],
                history_limitations=limitations,
            )
        from io import StringIO

        df = pd.read_csv(StringIO(text))
        df.columns = [c.lower() for c in df.columns]
        if "date" not in df.columns:
            return RawFetch(
                empty_bars(),
                attempts=[failed("stooq", f"unexpected CSV columns {list(df.columns)}")],
                history_limitations=limitations,
            )
        starts = pd.to_datetime(df["date"], utc=True)
        mask = (starts >= to_utc(start).normalize()) & (starts <= to_utc(end))
        df = df.loc[mask]
        if df.empty:
            return RawFetch(
                empty_bars(),
                attempts=[failed("stooq", "CSV had no rows in the requested window")],
                history_limitations=limitations,
            )
        vol = df["volume"] if "volume" in df.columns else 0.0
        bars = make_bars(
            starts.loc[df.index], df["open"], df["high"], df["low"], df["close"], vol,
            source="stooq", timeframe="1d", asset_class="equity",
        )
        return RawFetch(bars, attempts=[ok_attempt("stooq", len(bars))], source="stooq", history_limitations=limitations)
    except Exception as exc:
        return RawFetch(
            empty_bars(),
            attempts=[failed("stooq", f"{type(exc).__name__}: {exc}")],
            errors=[str(exc)],
            history_limitations=limitations,
        )


def fetch_equity(
    instrument: Instrument,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> RawFetch:
    yf = fetch_yfinance_equity(instrument, timeframe, start, end)
    if not yf.bars.empty:
        return yf
    # Stooq is daily only
    if timeframe != "1d":
        yf.history_limitations.append(STOOQ_LIMITS[timeframe])
        yf.errors.append("yfinance failed and Stooq fallback does not provide this timeframe")
        return yf
    stooq = fetch_stooq_daily(instrument, start, end)
    # combine attempts so the quality report shows both
    stooq.attempts = list(yf.attempts) + list(stooq.attempts)
    stooq.history_limitations = list(dict.fromkeys(yf.history_limitations + stooq.history_limitations))
    stooq.warnings = list(yf.warnings) + list(stooq.warnings)
    stooq.errors = list(yf.errors) + list(stooq.errors)
    return stooq
