"""Identify stale bars (the team name is ``is_stale``; do not call these placeholders).

The public import path is ``signal_data.masks``. This module re-exports those
helpers and adds store-side utilities (drop, run lengths, walk-forward breaks).

A bar is stale when ``volume == 0`` and ``open == high == low == close``.
These are not real trades. The raw store keeps them with ``is_stale=True``.
They are dropped by ``get_candles`` / ``load_closed`` by default, must never
be used as a fill, and must never feed ATR or volatility.

Dropping stale bars must never hide a hole. ``gap_segments`` treats stale
bars as missing: a run of *more than* ``STALE_RUN_GAP_BARS`` (3) stale or
otherwise missing bars is a gap, starts a new segment, and sets
``data_quality_warning``. A ``source_seam`` also starts a new segment.
"""

from __future__ import annotations

import pandas as pd

from signal_data.masks import (
    STALE_RUN_GAP_BARS,
    GapSegment,
    gap_segments,
    is_stale,
    missing_bars_between,
    stale_mask,
)
from signal_data.timeutil import to_utc

__all__ = [
    "STALE_RUN_GAP_BARS",
    "stale_mask",
    "is_stale",
    "drop_stale",
    "missing_bars_between",
    "stale_run_lengths",
    "gap_segments",
    "large_gap_breaks",
    "has_large_gaps",
    "has_stale_runs_gt",
    "GapSegment",
]


def drop_stale(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with stale rows removed. Honors an ``is_stale`` column if present.

    This does not hide holes: ``gap_segments`` reconstructs missing slots
    from the time grid, so a dropped run of stale bars still splits segments.
    """
    if df is None or df.empty:
        return df
    mask = stale_mask(df)
    if not mask.any():
        return df
    return df.loc[~mask].copy()


def _real_open_times(df: pd.DataFrame) -> list[pd.Timestamp]:
    work = df.sort_values("open_time")
    mask = stale_mask(work)
    real = work.loc[~mask] if len(mask) else work
    if real.empty:
        return []
    return [to_utc(t) for t in real["open_time"]]


def stale_run_lengths(df: pd.DataFrame, timeframe: str) -> list[int]:
    """Lengths of consecutive stale-or-missing runs on the timeframe grid.

    Leading/trailing holes relative to the first and last *row* in ``df``
    (including stale rows, so a stored stale stretch is visible) plus holes
    between real bars.
    """
    if df is None or df.empty:
        return []
    work = df.sort_values("open_time")
    opens = _real_open_times(work)
    if len(opens) < 2:
        if stale_mask(work).all():
            n = missing_bars_between(work["open_time"].iloc[0], work["open_time"].iloc[-1], timeframe) + 2
            return [n] if n > 0 else []
        return []
    return [n for a, b in zip(opens, opens[1:]) if (n := missing_bars_between(a, b, timeframe)) > 0]


def has_stale_runs_gt(df: pd.DataFrame, timeframe: str, n: int = STALE_RUN_GAP_BARS) -> bool:
    """True if any stale/missing run is longer than ``n`` bars (default 3)."""
    return any(length > n for length in stale_run_lengths(df, timeframe))


def large_gap_breaks(df: pd.DataFrame, timeframe: str) -> list[int]:
    """Indices (in ``df`` sorted by open_time) of the first real bar after each large gap or source seam.

    Stale bars are treated as missing, so a run of more than 3 stale bars
    produces a break even if those rows are still present and evenly spaced.
    A ``source_seam`` produces a break at the first bar of the new source.
    """
    if df is None or len(df) < 2:
        return []
    segs = gap_segments(df, timeframe)
    if len(segs) <= 1:
        return []
    work = df.sort_values("open_time").reset_index(drop=True)
    ot = pd.to_datetime(work["open_time"], utc=True)
    breaks: list[int] = []
    for seg in segs[1:]:
        hits = work.index[ot == seg.start]
        if len(hits):
            breaks.append(int(hits[0]))
    return breaks


def has_large_gaps(df: pd.DataFrame, timeframe: str) -> bool:
    """True when gap_segments splits the series (stale/missing run longer than 3, or a source seam)."""
    return len(gap_segments(df, timeframe)) > 1
