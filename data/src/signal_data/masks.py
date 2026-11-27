"""Public stale / gap helpers.

Official import::

    from signal_data.masks import is_stale, gap_segments, STALE_RUN_GAP_BARS

Signatures match Quant's expected contract:

- ``is_stale(df)``
- ``gap_segments(df, timeframe, max_gap_bars=3)``
- ``STALE_RUN_GAP_BARS = 3``

``gap_segments`` treats stale bars as missing (whether or not they were
dropped). A run *longer than* ``max_gap_bars`` (default 3) starts a new
segment. It also starts a new segment at every bar where ``source_seam``
is true, so Quant's feature reset and the walk-forward splitter both
handle a source change automatically.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# A run *longer than* this many stale/missing bars is a gap.
STALE_RUN_GAP_BARS = 3

_TF_DELTA = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}

__all__ = [
    "STALE_RUN_GAP_BARS",
    "GapSegment",
    "gap_segments",
    "is_stale",
    "missing_bars_between",
    "stale_mask",
]


def _to_utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def is_stale(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: True where the row is stale.

    If an ``is_stale`` column is already present, it is used as-is (bool).
    Otherwise a bar is stale when ``volume == 0`` and ``O == H == L == C``.
    """
    if df is None or df.empty:
        return pd.Series(dtype=bool, index=getattr(df, "index", None))
    if "is_stale" in df.columns:
        return df["is_stale"].astype(bool)
    vol = (
        pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
        if "volume" in df.columns
        else pd.Series(1.0, index=df.index)
    )
    o = pd.to_numeric(df["open"], errors="coerce")
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    return (vol == 0) & (o == h) & (h == l) & (l == c)


# Official name previously used in signal_data.stale; same function.
stale_mask = is_stale


def _ensure_open_time(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "open_time" in df.columns:
        return df
    out = df.copy()
    if "close_time" in out.columns:
        out["open_time"] = pd.to_datetime(out["close_time"], utc=True)
    elif isinstance(out.index, pd.DatetimeIndex):
        idx = out.index
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        out["open_time"] = idx
    else:
        raise ValueError("gap_segments requires open_time, close_time, or a DatetimeIndex")
    return out


def missing_bars_between(t0: pd.Timestamp, t1: pd.Timestamp, timeframe: str) -> int:
    """Count expected bar opens strictly between t0 and t1 on the timeframe grid."""
    if timeframe not in _TF_DELTA:
        raise ValueError(f"unknown timeframe {timeframe}")
    step = _TF_DELTA[timeframe]
    delta = _to_utc(t1) - _to_utc(t0)
    if delta <= step:
        return 0
    slots = int(round(delta / step))
    return max(slots - 1, 0)


@dataclass(frozen=True)
class GapSegment:
    """One contiguous run of *real* (non-stale) bars that does not span a large gap or source seam."""

    start: pd.Timestamp  # first real open_time (UTC)
    end: pd.Timestamp    # last real open_time (UTC), inclusive


def gap_segments(
    df: pd.DataFrame,
    timeframe: str,
    max_gap_bars: int = STALE_RUN_GAP_BARS,
) -> list[GapSegment]:
    """Contiguous real-bar segments, treating stale bars as missing.

    A run of more than ``max_gap_bars`` (default ``STALE_RUN_GAP_BARS`` = 3)
    stale or otherwise missing bars starts a new segment. A bar with
    ``source_seam`` true also starts a new segment, even if the grid is
    contiguous. The result is the same whether stale rows are still in
    ``df`` or have already been dropped.
    """
    if df is None or df.empty:
        return []
    if timeframe not in _TF_DELTA:
        raise ValueError(f"unknown timeframe {timeframe}")
    work = _ensure_open_time(df).sort_values("open_time").reset_index(drop=True)
    if work.empty:
        return []
    stale = is_stale(work).reindex(work.index).fillna(False)
    real_idx = work.index[~stale].tolist()
    if not real_idx:
        return []
    opens = [_to_utc(t) for t in work.loc[real_idx, "open_time"]]
    if "source_seam" in work.columns:
        seam_csum = work["source_seam"].astype(bool).astype(int).cumsum()
    else:
        seam_csum = pd.Series(0, index=work.index)

    segments: list[GapSegment] = []
    seg_start = prev_open = opens[0]
    prev_i = real_idx[0]
    for cur_i, cur_open in zip(real_idx[1:], opens[1:]):
        missing = missing_bars_between(prev_open, cur_open, timeframe)
        # Seams on bars after the previous real bar, up to and including this one
        # (a seam on a stale row is not hidden).
        seam_hit = int(seam_csum.iloc[cur_i]) - int(seam_csum.iloc[prev_i]) > 0
        if missing > max_gap_bars or seam_hit:
            segments.append(GapSegment(seg_start, prev_open))
            seg_start = cur_open
        prev_open = cur_open
        prev_i = cur_i
    segments.append(GapSegment(seg_start, prev_open))
    return segments
