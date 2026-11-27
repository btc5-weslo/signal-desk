"""Timeframe-grid alignment for bar open_times.

Off-grid bars (open_time not on the timeframe boundary) are dropped, never
snapped to the grid. They count as missing, so a long enough run becomes a
gap and sets data_quality_warning.
"""

from __future__ import annotations

import pandas as pd

from signal_data.timeutil import to_utc

ET = "America/New_York"


class OffGridError(ValueError):
    """A frame still contains one or more off-boundary open_times."""


def is_open_aligned(ts, timeframe: str, asset_class: str = "crypto") -> bool:
    """True if ``ts`` sits on the official open grid for this class/timeframe."""
    t = to_utc(ts)
    if int(getattr(t, "nanosecond", 0) or 0) != 0:
        return False
    if t.second != 0 or t.microsecond != 0:
        return False

    if asset_class == "equity":
        et = t.tz_convert(ET)
        if timeframe == "1d":
            return et.hour == 9 and et.minute == 30
        if timeframe == "4h":
            # RTH buckets: 09:30–13:30 and 13:30–16:00 ET; never cross days.
            return (et.hour, et.minute) in {(9, 30), (13, 30)}
        if timeframe == "1h":
            # Cash session hourly opens: 09:30, then 10:30..15:30, or clock hours
            # 09:30/10:00..15:00 depending on the source. Reject sub-minute noise.
            return et.minute in (0, 30) and 9 <= et.hour <= 15
        if timeframe == "15m":
            return et.minute % 15 == 0 and 9 <= et.hour <= 15
        return False

    # crypto and fx: UTC grids. crypto 4h = 00/04/08/12/16/20; fx 4h is the
    # same UTC grid (weekend-crossing buckets are dropped separately).
    if timeframe == "15m":
        return t.minute % 15 == 0
    if timeframe == "1h":
        return t.minute == 0
    if timeframe == "4h":
        return t.minute == 0 and t.hour % 4 == 0
    if timeframe == "1d":
        return t.minute == 0 and t.hour == 0
    return False


def off_grid_mask(df: pd.DataFrame, timeframe: str, asset_class: str = "crypto") -> pd.Series:
    if df is None or df.empty or "open_time" not in df.columns:
        return pd.Series(dtype=bool, index=getattr(df, "index", None))
    return ~pd.to_datetime(df["open_time"], utc=True).map(
        lambda t: is_open_aligned(t, timeframe, asset_class)
    )


def drop_off_grid(
    df: pd.DataFrame, timeframe: str, asset_class: str = "crypto"
) -> tuple[pd.DataFrame, list]:
    """Remove off-boundary rows (do not snap). Returns (frame, dropped open_times)."""
    if df is None or df.empty:
        return df, []
    mask = off_grid_mask(df, timeframe, asset_class)
    if not bool(mask.any()):
        return df, []
    times = [t.to_pydatetime() for t in pd.to_datetime(df.loc[mask, "open_time"], utc=True)]
    return df.loc[~mask].copy(), times


def assert_aligned(df: pd.DataFrame, timeframe: str, asset_class: str = "crypto") -> None:
    """Fail if any open_time is off the timeframe boundary."""
    mask = off_grid_mask(df, timeframe, asset_class)
    if mask.any():
        sample = pd.to_datetime(df.loc[mask, "open_time"], utc=True).head(5).tolist()
        raise OffGridError(
            f"{int(mask.sum())} off-boundary open_time(s) in {asset_class} {timeframe}; "
            f"examples: {sample}. Off-grid bars must be dropped, never snapped."
        )



def scan_store_alignment(*, data_dir=None) -> list[dict]:
    """Inspect every store file. Returns one row per series with off-grid counts."""
    from signal_data.paths import get_store_dir
    from signal_data.storage import read_parquet

    rows = []
    root = get_store_dir(data_dir)
    for path in sorted(root.glob("*/*/*.parquet")):
        asset_class = path.parent.parent.name
        symbol = path.parent.name
        timeframe = path.stem
        df = read_parquet(path)
        mask = off_grid_mask(df, timeframe, asset_class)
        n = int(mask.sum()) if len(mask) else 0
        times = [str(t) for t in df.loc[mask, "open_time"].tolist()] if n else []
        rows.append(
            {
                "path": str(path),
                "asset_class": asset_class,
                "symbol": symbol,
                "timeframe": timeframe,
                "n_bars": int(len(df)),
                "n_off_grid": n,
                "first_off_grid": times[0] if times else None,
                "last_off_grid": times[-1] if times else None,
                "ok": n == 0,
            }
        )
    return rows


def repair_off_grid_store(*, data_dir=None) -> list[dict]:
    """Drop off-grid bars from every store file (do not snap) and rewrite seams.

    Alignment is re-checked on write; a remaining off-grid bar fails the write.
    """
    from signal_data.paths import get_store_dir
    from signal_data.storage import atomic_write_parquet, mark_source_seams, read_parquet
    from signal_data.timeutil import now_utc

    rows = []
    root = get_store_dir(data_dir)
    as_of = now_utc()
    for path in sorted(root.glob("*/*/*.parquet")):
        asset_class = path.parent.parent.name
        symbol = path.parent.name
        timeframe = path.stem
        df = read_parquet(path)
        cleaned, dropped = drop_off_grid(df, timeframe, asset_class)
        n = len(dropped)
        if n:
            cleaned = mark_source_seams(cleaned)
            atomic_write_parquet(cleaned, path, as_of=as_of)
        rows.append(
            {
                "path": str(path),
                "symbol": symbol,
                "timeframe": timeframe,
                "n_before": int(len(df)),
                "n_dropped": n,
                "n_after": int(len(cleaned)),
                "first_dropped": str(dropped[0]) if dropped else None,
                "last_dropped": str(dropped[-1]) if dropped else None,
            }
        )
        print(
            f"repair {symbol} {timeframe}: dropped {n} off-grid "
            f"({dropped[0] if dropped else '-'} .. {dropped[-1] if dropped else '-'}) "
            f"{len(df)} -> {len(cleaned)}",
            flush=True,
        )
    return rows
