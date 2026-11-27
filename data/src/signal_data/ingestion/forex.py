"""FX OHLCV: yfinance first (e.g. EURUSD=X); Frankfurter/ECB daily as fallback.

Frankfurter returns official ECB reference rates, not exchange OHLC. When used,
open=high=low=close=rate and volume=0, and that limitation is recorded. Rates
are not turned into fake wicks.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from signal_data.ingestion.base import RawFetch, empty_bars, failed, make_bars, ok_attempt
from signal_data.ingestion.equities import YF_INTERVAL, _resample_ohlcv_1h_to_4h
from signal_data.resample import resample_closed
from signal_data.symbols import to_source
from signal_data.timeutil import to_utc
from signal_data.universe import Instrument, YFINANCE_INTRADAY_LIMITS, FRANKFURTER_LIMITS

_USER_AGENT = "signal-data/0.1 (research; +https://localhost)"
_FRANKFURTER_URLS = (
    "https://api.frankfurter.app",
    "https://api.frankfurter.dev",
)


def fetch_yfinance_fx(
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
        return RawFetch(empty_bars(), attempts=[failed("yfinance", "download returned no rows")], history_limitations=limitations)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]).lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    if not {"open", "high", "low", "close"}.issubset(df.columns):
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
        asset_class="fx",
    )
    notes = []
    if timeframe == "4h":
        bars = resample_closed(bars, "4h", asset_class="fx", source_timeframe="1h")
        notes.append("4h resampled from yfinance 1h; incomplete trailing bucket dropped")
    return RawFetch(
        bars,
        attempts=[ok_attempt("yfinance", len(bars), notes=notes)],
        source="yfinance",
        history_limitations=limitations,
        warnings=list(notes),
    )


def fetch_frankfurter_daily(instrument: Instrument, start: datetime, end: datetime) -> RawFetch:
    limitations = [FRANKFURTER_LIMITS["1d"]]
    import requests

    pair = to_source(instrument.symbol, "frankfurter")  # EUR/USD
    base, quote = pair.split("/")
    start_s = to_utc(start).date().isoformat()
    end_s = to_utc(end).date().isoformat()
    last_err = None
    for root in _FRANKFURTER_URLS:
        url = f"{root}/{start_s}..{end_s}?from={base}&to={quote}"
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
            payload = resp.json()
            rates = payload.get("rates") or {}
            if not rates:
                last_err = "Frankfurter returned no rates"
                continue
            dates = sorted(rates)
            values = [float(rates[d][quote]) for d in dates]
            idx = pd.to_datetime(dates, utc=True)
            # Honest: official reference rate, not a real OHLC bar.
            bars = make_bars(
                idx, values, values, values, values, [0.0] * len(values),
                source="frankfurter", timeframe="1d", asset_class="fx",
            )
            note = "Frankfurter/ECB daily reference rate; O=H=L=C, volume=0 (not exchange OHLC)"
            return RawFetch(
                bars,
                attempts=[ok_attempt("frankfurter", len(bars), notes=[note])],
                source="frankfurter",
                history_limitations=limitations,
                warnings=[note],
            )
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue
    return RawFetch(
        empty_bars(),
        attempts=[failed("frankfurter", last_err or "all Frankfurter endpoints failed")],
        errors=[last_err or "frankfurter failed"],
        history_limitations=limitations,
    )


def fetch_forex(
    instrument: Instrument,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> RawFetch:
    yf = fetch_yfinance_fx(instrument, timeframe, start, end)
    if not yf.bars.empty:
        return yf
    if timeframe != "1d":
        yf.history_limitations.append(FRANKFURTER_LIMITS[timeframe])
        yf.errors.append("yfinance failed and Frankfurter fallback is daily-only")
        return yf
    fb = fetch_frankfurter_daily(instrument, start, end)
    fb.attempts = list(yf.attempts) + list(fb.attempts)
    fb.history_limitations = list(dict.fromkeys(yf.history_limitations + fb.history_limitations))
    fb.warnings = list(yf.warnings) + list(fb.warnings)
    fb.errors = list(yf.errors) + list(fb.errors)
    return fb
