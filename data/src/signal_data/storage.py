"""Atomic Parquet I/O for the locked store layout.

Path: store/{asset_class}/{symbol}/{timeframe}.parquet
Columns: open_time, close_time (timestamp[us, tz=UTC]), open, high, low, close,
volume, source, is_stale, source_seam. Sorted by open_time, no duplicates, closed bars only.
Stale bars (volume==0 and o==h==l==c) are kept and flagged is_stale=True.
A file may hold more than one source; each bar keeps its own source (never relabeled).
source_seam is True on every bar whose source differs from the previous bar's.
Writes go to a temp file in the same directory, then os.replace.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from signal_data.alignment import assert_aligned
from signal_data.paths import PARQUET_COLUMNS, series_path
from signal_data.timeutil import bars_fully_closed, now_utc

_TS = pa.timestamp("us", tz="UTC")
_SCHEMA = pa.schema(
    [
        ("open_time", _TS),
        ("close_time", _TS),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
        ("source", pa.string()),
        ("is_stale", pa.bool_()),
        ("source_seam", pa.bool_()),
    ]
)


def _to_utc_us(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s, utc=True)
    # pandas datetime64[ns, UTC] is fine; Arrow will cast to us
    return s


def frame_to_arrow(df: pd.DataFrame) -> pa.Table:
    if df.empty:
        return pa.Table.from_arrays(
            [
                pa.array([], type=_TS),
                pa.array([], type=_TS),
                pa.array([], type=pa.float64()),
                pa.array([], type=pa.float64()),
                pa.array([], type=pa.float64()),
                pa.array([], type=pa.float64()),
                pa.array([], type=pa.float64()),
                pa.array([], type=pa.string()),
                pa.array([], type=pa.bool_()),
                pa.array([], type=pa.bool_()),
            ],
            schema=_SCHEMA,
        )
    work = df.copy()
    if "is_stale" not in work.columns:
        from signal_data.stale import stale_mask
        work["is_stale"] = stale_mask(work).astype(bool)
    else:
        work["is_stale"] = work["is_stale"].astype(bool)
    work = mark_source_seams(work)
    out = work[list(PARQUET_COLUMNS)].copy()
    out["open_time"] = _to_utc_us(out["open_time"])
    out["close_time"] = _to_utc_us(out["close_time"])
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")
    out["source"] = out["source"].astype(str)
    out["is_stale"] = out["is_stale"].astype(bool)
    out["source_seam"] = out["source_seam"].astype(bool)
    out = out.sort_values("open_time")
    out = out.drop_duplicates(subset=["open_time"], keep="last")
    table = pa.Table.from_pandas(out, preserve_index=False)
    # force exact types
    arrays = []
    for field in _SCHEMA:
        col = table.column(field.name)
        arrays.append(col.cast(field.type))
    return pa.Table.from_arrays(arrays, schema=_SCHEMA)


def atomic_write_parquet(df: pd.DataFrame, path: Path, *, as_of=None) -> Path:
    """Write a closed-bar frame atomically (temp file in the same dir, then rename)."""
    from signal_data.paths import ASSET_CLASSES, TIMEFRAMES

    if path.suffix == ".parquet" and path.parent.parent.name in ASSET_CLASSES and path.stem in TIMEFRAMES:
        assert_aligned(df, path.stem, path.parent.parent.name)

    closed = bars_fully_closed(df, as_of=as_of)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = frame_to_arrow(closed)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        pq.write_table(table, tmp, compression="zstd")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return path


def write_series(df: pd.DataFrame, asset_class: str, symbol: str, timeframe: str, *, as_of=None, data_dir=None) -> Path:
    path = series_path(asset_class, symbol, timeframe, data_dir=data_dir)
    return atomic_write_parquet(df, path, as_of=as_of)


def read_series(asset_class: str, symbol: str, timeframe: str, *, data_dir=None) -> pd.DataFrame:
    path = series_path(asset_class, symbol, timeframe, data_dir=data_dir)
    if not path.exists():
        return pd.DataFrame(columns=list(PARQUET_COLUMNS))
    return read_parquet(path)


def read_parquet(path: Path) -> pd.DataFrame:
    table = pq.read_table(path)
    df = table.to_pandas()
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    if "is_stale" not in df.columns:
        from signal_data.stale import stale_mask
        df["is_stale"] = stale_mask(df).astype(bool)
    else:
        df["is_stale"] = df["is_stale"].astype(bool)
    df = mark_source_seams(df)
    return df.sort_values("open_time").reset_index(drop=True)



PREFERRED_SOURCE = "binance_vision"


def mark_source_seams(df: pd.DataFrame) -> pd.DataFrame:
    """Set source_seam True where ``source`` differs from the previous bar.

    The first bar is False (no previous source). Sources are never relabeled.
    """
    cols = list(df.columns)
    if df is None or df.empty:
        out = df.copy() if df is not None else pd.DataFrame()
        if "source_seam" not in out.columns:
            out["source_seam"] = pd.Series(dtype=bool)
        return out
    out = df.sort_values("open_time").copy()
    src = out["source"].astype(str) if "source" in out.columns else pd.Series("", index=out.index)
    seam = src.ne(src.shift(1))
    if len(seam):
        seam.iloc[0] = False
    out["source_seam"] = seam.astype(bool)
    return out


def _ensure_store_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(PARQUET_COLUMNS)
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    out = df.copy()
    if "is_stale" not in out.columns:
        from signal_data.stale import stale_mask
        out["is_stale"] = stale_mask(out).astype(bool)
    out = mark_source_seams(out)
    return out[cols]


def merge_on_open_time(*frames: pd.DataFrame, prefer: str = PREFERRED_SOURCE) -> pd.DataFrame:
    """Merge frames on open_time. Each bar keeps its own source; never relabeled.

    On duplicate open_time, the bar from ``prefer`` (binance_vision) wins and
    the other is dropped. If neither (or both) is preferred, the later frame
    in *frames wins. The result has no duplicate open_time and a fresh
    source_seam flag.
    """
    cols = list(PARQUET_COLUMNS)
    parts = [_ensure_store_columns(f) for f in frames if f is not None and len(f)]
    if not parts:
        return pd.DataFrame(columns=cols)
    # tag frame order so later frames win when preference is tied
    tagged = []
    for i, part in enumerate(parts):
        work = part.copy()
        work["_merge_ord"] = i
        work["_prefer"] = (work["source"].astype(str) == prefer).astype(int)
        tagged.append(work)
    base = pd.concat(tagged, ignore_index=True)
    base["open_time"] = pd.to_datetime(base["open_time"], utc=True)
    base["close_time"] = pd.to_datetime(base["close_time"], utc=True)
    # highest prefer, then latest frame
    base = base.sort_values(["open_time", "_prefer", "_merge_ord"], ascending=[True, False, False])
    base = base.drop_duplicates(subset=["open_time"], keep="first")
    base = base.drop(columns=["_merge_ord", "_prefer"])
    base = mark_source_seams(base)
    return base.reset_index(drop=True)


def merge_incremental(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Concat, prefer incoming on duplicate open_time of the same source.

    Mixed sources are allowed. On a conflict, binance_vision is kept and the
    duplicate is dropped. Sources are never relabeled.
    """
    return merge_on_open_time(existing, incoming)


def write_staging(df: pd.DataFrame, asset_class: str, symbol: str, timeframe: str, *, as_of=None, staging_dir=None) -> Path:
    """Write a backfill into staging/, never into store/."""
    from signal_data.paths import staging_path

    return atomic_write_parquet(
        df,
        staging_path(asset_class, symbol, timeframe, staging_dir=staging_dir),
        as_of=as_of,
    )


def last_open_time(asset_class: str, symbol: str, timeframe: str, *, data_dir=None) -> pd.Timestamp | None:
    df = read_series(asset_class, symbol, timeframe, data_dir=data_dir)
    if df.empty:
        return None
    return pd.Timestamp(df["open_time"].iloc[-1])
