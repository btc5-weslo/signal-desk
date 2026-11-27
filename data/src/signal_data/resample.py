"""Stable public resampling API used by Data and imported by Quant.

Official import path:

    from signal_data.resample import resample_closed

A resampled bar is written only when *every* expected source bar in that
bucket is present. Importing this module has no side effects.

Stable public name: ``from signal_data.resample import resample_closed``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from signal_data.stale import stale_mask
from signal_data.timeutil import TF_DELTA, to_utc

UTC = timezone.utc
ET = ZoneInfo("America/New_York")

# FX / crypto weekend close: Friday 22:00 UTC to Sunday 22:00 UTC.
FX_WEEKEND_START_DOW = 4  # Friday
FX_WEEKEND_START_HOUR = 22
FX_WEEKEND_END_DOW = 6  # Sunday
FX_WEEKEND_END_HOUR = 22

__all__ = ["resample_closed", "resample_closed_result", "overlaps_fx_weekend", "infer_source_timeframe"]

TARGET_TFS = ("15m", "1h", "4h", "1d")
SOURCE_DELTAS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


@dataclass
class DroppedBucket:
    open_time: pd.Timestamp
    close_time: pd.Timestamp
    reason: str
    expected_bars: int
    actual_bars: int


@dataclass
class ResampleResult:
    bars: pd.DataFrame
    dropped: list[DroppedBucket] = field(default_factory=list)


def infer_source_timeframe(df: pd.DataFrame) -> str:
    """Infer source timeframe from median open_time spacing."""
    if "open_time" not in df.columns:
        raise ValueError("bars need an open_time column")
    ot = pd.to_datetime(df["open_time"], utc=True).sort_values()
    if len(ot) < 2:
        raise ValueError("need at least two bars to infer source timeframe")
    minutes = ot.diff().dt.total_seconds().median() / 60.0
    for tf, delta in (("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440)):
        if abs(minutes - delta) <= max(2.0, 0.25 * delta):
            return tf
    raise ValueError(f"cannot infer source timeframe from median spacing {minutes:.1f} minutes")


def overlaps_fx_weekend(open_time: pd.Timestamp, close_time: pd.Timestamp) -> bool:
    """True if [open_time, close_time) overlaps Fri 22:00 UTC–Sun 22:00 UTC."""
    start = to_utc(open_time)
    end = to_utc(close_time)
    if end <= start:
        return False
    cursor = (start - pd.Timedelta(days=8)).normalize()
    # advance to a Friday (Mon=0 ... Fri=4)
    while int(cursor.dayofweek) != 4:
        cursor += pd.Timedelta(days=1)
    last = end + pd.Timedelta(days=8)
    while cursor <= last:
        wk_start = cursor + pd.Timedelta(hours=FX_WEEKEND_START_HOUR)
        wk_end = wk_start + pd.Timedelta(days=2)  # Sun 22:00
        if start < wk_end and end > wk_start:
            return True
        cursor += pd.Timedelta(days=7)
    return False


def _expected_opens(bucket_open: pd.Timestamp, bucket_close: pd.Timestamp, source_tf: str) -> list[pd.Timestamp]:
    step = SOURCE_DELTAS[source_tf]
    t = to_utc(bucket_open)
    end = to_utc(bucket_close)
    out: list[pd.Timestamp] = []
    # safety cap
    for _ in range(10_000):
        if t >= end:
            break
        out.append(t)
        t = t + step
    return out


def _crypto_or_fx_4h_buckets(min_open: pd.Timestamp, max_close: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """UTC 4h buckets aligned to 00/04/08/12/16/20."""
    start = to_utc(min_open).floor("4h")
    end = to_utc(max_close).ceil("4h")
    buckets = []
    t = start
    while t < end:
        buckets.append((t, t + pd.Timedelta(hours=4)))
        t += pd.Timedelta(hours=4)
    return buckets


def _equity_4h_buckets(min_open: pd.Timestamp, max_close: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """US RTH: 09:30–13:30 ET and 13:30–16:00 ET. Never merges across days."""
    start_et = to_utc(min_open).tz_convert(ET).normalize() - pd.Timedelta(days=1)
    end_et = to_utc(max_close).tz_convert(ET).normalize() + pd.Timedelta(days=2)
    buckets = []
    day = start_et
    while day <= end_et:
        # skip weekends
        if int(day.dayofweek) < 5:
            d = day.tz_convert(ET)
            b1_o = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=9, minute=30, tz=ET).tz_convert("UTC")
            b1_c = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=13, minute=30, tz=ET).tz_convert("UTC")
            b2_o = b1_c
            b2_c = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=16, minute=0, tz=ET).tz_convert("UTC")
            buckets.append((b1_o, b1_c))
            buckets.append((b2_o, b2_c))
        day += pd.Timedelta(days=1)
    return buckets


def _generic_buckets(
    min_open: pd.Timestamp,
    max_close: pd.Timestamp,
    target_tf: str,
    *,
    asset_class: str,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if target_tf == "4h":
        if asset_class == "equity":
            return _equity_4h_buckets(min_open, max_close)
        return _crypto_or_fx_4h_buckets(min_open, max_close)
    if target_tf == "1h":
        start = to_utc(min_open).floor("1h")
        end = to_utc(max_close).ceil("1h")
        out = []
        t = start
        while t < end:
            out.append((t, t + pd.Timedelta(hours=1)))
            t += pd.Timedelta(hours=1)
        return out
    if target_tf == "15m":
        start = to_utc(min_open).floor("15min")
        end = to_utc(max_close).ceil("15min")
        out = []
        t = start
        while t < end:
            out.append((t, t + pd.Timedelta(minutes=15)))
            t += pd.Timedelta(minutes=15)
        return out
    if target_tf == "1d":
        if asset_class == "equity":
            # one bucket per RTH session
            start_et = to_utc(min_open).tz_convert(ET).normalize() - pd.Timedelta(days=1)
            end_et = to_utc(max_close).tz_convert(ET).normalize() + pd.Timedelta(days=2)
            out = []
            day = start_et
            while day <= end_et:
                if int(day.dayofweek) < 5:
                    d = day
                    o = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=9, minute=30, tz=ET).tz_convert("UTC")
                    c = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=16, minute=0, tz=ET).tz_convert("UTC")
                    out.append((o, c))
                day += pd.Timedelta(days=1)
            return out
        start = to_utc(min_open).floor("1D")
        end = to_utc(max_close).ceil("1D")
        out = []
        t = start
        while t < end:
            out.append((t, t + pd.Timedelta(days=1)))
            t += pd.Timedelta(days=1)
        return out
    raise ValueError(f"unsupported target_tf {target_tf}")


def resample_closed_result(
    df: pd.DataFrame,
    target_tf: str,
    as_of: datetime | pd.Timestamp | None = None,
    *,
    asset_class: str,
    source_timeframe: str | None = None,
) -> ResampleResult:
    """Same as ``resample_closed`` but also returns dropped-bucket reasons."""
    if target_tf not in TARGET_TFS:
        raise ValueError(f"target_tf must be one of {TARGET_TFS}")
    if asset_class not in {"crypto", "equity", "fx"}:
        raise ValueError(f"unknown asset_class {asset_class}")
    if df is None or df.empty:
        empty = pd.DataFrame(
            columns=[
                "open_time", "close_time", "open", "high", "low", "close",
                "volume", "source", "expected_bars",
            ]
        )
        return ResampleResult(empty, [])

    work = df.copy()
    work["open_time"] = pd.to_datetime(work["open_time"], utc=True)
    if "close_time" not in work.columns:
        src_tf = source_timeframe or infer_source_timeframe(work)
        work["close_time"] = work["open_time"] + SOURCE_DELTAS[src_tf]
    else:
        work["close_time"] = pd.to_datetime(work["close_time"], utc=True)
    if as_of is not None:
        cut = to_utc(as_of)
        work = work.loc[work["close_time"] <= cut]
    work = work.sort_values("open_time").drop_duplicates(subset=["open_time"], keep="last")
    if work.empty:
        return resample_closed_result(work.iloc[0:0], target_tf, asset_class=asset_class, source_timeframe=source_timeframe)

    src_tf = source_timeframe or infer_source_timeframe(work)
    if SOURCE_DELTAS[target_tf] < SOURCE_DELTAS[src_tf]:
        raise ValueError(f"cannot resample {src_tf} up to a shorter {target_tf}")

    # If the source is already the target, just apply as_of / completeness vs itself.
    if src_tf == target_tf:
        out = work.copy()
        out["expected_bars"] = 1
        return ResampleResult(out.reset_index(drop=True), [])

    opens_all = set(to_utc(ts) for ts in work["open_time"])
    # Stale source bars do not count as present: the bucket is incomplete.
    is_stale = stale_mask(work)
    work = work.copy()
    work["_stale"] = is_stale.values if len(is_stale) == len(work) else False
    real = work.loc[~work["_stale"]]
    opens = set(to_utc(ts) for ts in real["open_time"]) if not real.empty else set()
    by_open = real.set_index(real["open_time"].map(to_utc), drop=False) if not real.empty else work.iloc[0:0]
    buckets = _generic_buckets(
        work["open_time"].min(), work["close_time"].max(), target_tf, asset_class=asset_class
    )
    rows = []
    dropped: list[DroppedBucket] = []
    src_col = work["source"].iloc[0] if "source" in work.columns and len(work) else ""

    for b_open, b_close in buckets:
        if as_of is not None and to_utc(b_close) > to_utc(as_of):
            # forming / not yet closed
            continue
        expected = _expected_opens(b_open, b_close, src_tf)
        n_exp = len(expected)
        if n_exp == 0:
            continue
        if asset_class == "fx" and overlaps_fx_weekend(b_open, b_close):
            dropped.append(
                DroppedBucket(b_open, b_close, "fx_weekend_overlap", n_exp, 0)
            )
            continue
        have = [t for t in expected if t in opens]
        if len(have) != n_exp:
            stale_hit = any(t in opens_all and t not in opens for t in expected)
            reason = "stale_source_bars" if stale_hit else "missing_source_bars"
            dropped.append(
                DroppedBucket(b_open, b_close, reason, n_exp, len(have))
            )
            continue
        part = by_open.loc[expected]
        rows.append(
            {
                "open_time": to_utc(b_open),
                "close_time": to_utc(b_close),
                "open": float(part["open"].iloc[0]),
                "high": float(part["high"].max()),
                "low": float(part["low"].min()),
                "close": float(part["close"].iloc[-1]),
                "volume": float(part["volume"].sum()) if "volume" in part.columns else 0.0,
                "source": f"{src_col}|resampled_{src_tf}_to_{target_tf}".lstrip("|"),
                "expected_bars": n_exp,
            }
        )
    bars = pd.DataFrame(rows)
    if bars.empty:
        bars = pd.DataFrame(
            columns=[
                "open_time", "close_time", "open", "high", "low", "close",
                "volume", "source", "expected_bars",
            ]
        )
    else:
        bars["open_time"] = pd.to_datetime(bars["open_time"], utc=True)
        bars["close_time"] = pd.to_datetime(bars["close_time"], utc=True)
        bars = bars.sort_values("open_time").reset_index(drop=True)
    return ResampleResult(bars, dropped)


def resample_closed(
    df: pd.DataFrame,
    target_tf: str,
    as_of: datetime | pd.Timestamp | None = None,
    *,
    asset_class: str,
    source_timeframe: str | None = None,
) -> pd.DataFrame:
    """Resample a lower-timeframe OHLCV series to ``target_tf``, closed bars only.

    A bucket is kept only when every expected source bar is present and not stale.
    A higher-timeframe bucket that contains any stale source bar is incomplete.

    Alignment
    ---------
    - crypto: 4h buckets at UTC 00/04/08/12/16/20.
    - US equities: regular session only, 09:30–13:30 ET and 13:30–16:00 ET.
      The second bucket is 2.5 hours; ``expected_bars`` reflects that (e.g. 3
      hourly bars, not 4). Buckets never merge across days.
    - fx: UTC 4h buckets like crypto, but any bucket that overlaps the weekend
      close (Fri 22:00 UTC–Sun 22:00 UTC) is dropped.

    Parameters
    ----------
    df:
        Source bars with ``open_time`` (UTC) and OHLCV columns.
    target_tf:
        ``15m``, ``1h``, ``4h``, or ``1d``.
    as_of:
        If given, source bars with ``close_time`` after this instant and any
        bucket that has not yet closed are excluded (no lookahead, no forming bar).
    asset_class:
        ``crypto``, ``equity``, or ``fx``. Required so session rules are explicit.
    source_timeframe:
        Optional; inferred from median spacing when omitted.

    Returns
    -------
    pandas.DataFrame
        Complete buckets only, including an ``expected_bars`` column so the
        shorter equity close-session bucket is documented honestly. This
        extra column is dropped before writing the locked Parquet store.
    """
    return resample_closed_result(
        df,
        target_tf,
        as_of,
        asset_class=asset_class,
        source_timeframe=source_timeframe,
    ).bars
