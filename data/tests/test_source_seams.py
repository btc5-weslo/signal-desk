"""Merge on open_time, source_seam flags, and walk-forward / gap_segments exclusion."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from signal_data.backtester.walk_forward import rolling_windows
from signal_data.masks import STALE_RUN_GAP_BARS, gap_segments, is_stale
from signal_data.storage import mark_source_seams, merge_on_open_time
from tests.toy import make_bars


def _frame(start, n, source, timeframe="1h"):
    df = make_bars(start, n, timeframe=timeframe)
    df["source"] = source
    return df


def test_merge_prefers_binance_vision_and_has_no_duplicate_open_time():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    us = _frame(start, 6, "ccxt:binanceus")
    # Vision overlaps the last two US bars and extends two more hours
    vis = _frame(datetime(2024, 1, 1, 4, tzinfo=timezone.utc), 4, "binance_vision")
    # Different close on the overlap so we can see which row won
    vis = vis.copy()
    vis.loc[vis["open_time"] == pd.Timestamp("2024-01-01 04:00", tz="UTC"), "close"] = 999.0

    merged = merge_on_open_time(us, vis)
    assert merged["open_time"].is_unique
    assert not merged["open_time"].duplicated().any()
    assert len(merged) == 8  # 6 US + 2 unique vision extensions
    # Overlap kept vision, source never relabeled
    row = merged.loc[merged["open_time"] == pd.Timestamp("2024-01-01 04:00", tz="UTC")].iloc[0]
    assert row["source"] == "binance_vision"
    assert float(row["close"]) == 999.0
    # Pre-overlap stays binanceus
    first = merged.iloc[0]
    assert first["source"] == "ccxt:binanceus"
    sources = set(merged["source"].unique())
    assert sources == {"ccxt:binanceus", "binance_vision"}


def test_source_seam_true_only_when_source_changes():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    us = _frame(start, 4, "ccxt:binanceus")
    vis = _frame(datetime(2024, 1, 1, 4, tzinfo=timezone.utc), 3, "binance_vision")
    merged = merge_on_open_time(us, vis)
    assert "source_seam" in merged.columns
    assert bool(merged["source_seam"].iloc[0]) is False
    # Seam is the first vision bar (2024-01-01 04:00)
    seams = merged.loc[merged["source_seam"], "open_time"].tolist()
    assert seams == [pd.Timestamp("2024-01-01 04:00", tz="UTC")]
    # Re-marking is idempotent
    again = mark_source_seams(merged)
    assert again["source_seam"].tolist() == merged["source_seam"].tolist()


def test_gap_segments_starts_new_segment_at_source_seam():
    """Quant / walk-forward must split at a source_seam even when the grid is contiguous."""
    assert STALE_RUN_GAP_BARS == 3
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    us = _frame(start, 5, "ccxt:binanceus")
    vis = _frame(datetime(2024, 1, 1, 5, tzinfo=timezone.utc), 5, "binance_vision")
    merged = merge_on_open_time(us, vis)
    # 10 contiguous hourly bars; only the seam should split.
    segs = gap_segments(merged, "1h")
    assert len(segs) == 2
    segs3 = gap_segments(merged, "1h", max_gap_bars=3)
    assert segs3 == segs
    assert segs[0].end == pd.Timestamp("2024-01-01 04:00", tz="UTC")
    assert segs[1].start == pd.Timestamp("2024-01-01 05:00", tz="UTC")
    # Without the seam column, a contiguous grid is one segment.
    bare = merged.drop(columns=["source_seam"])
    assert len(gap_segments(bare, "1h")) == 1


def test_is_stale_signature():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _frame(start, 3, "toy")
    mask = is_stale(df)
    assert len(mask) == 3
    assert not mask.any()


def test_walk_forward_windows_do_not_span_a_source_seam():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    us = _frame(start, 8, "ccxt:binanceus")
    vis = _frame(datetime(2024, 1, 1, 8, tzinfo=timezone.utc), 8, "binance_vision")
    merged = merge_on_open_time(us, vis)
    # 16 contiguous hours, seam at 08:00. train=3, test=2 fits on each side.
    windows = rolling_windows(merged, train_bars=3, test_bars=2, step_bars=2, timeframe="1h")
    assert windows, "expected windows on each side of the seam"
    seam = pd.Timestamp("2024-01-01 08:00", tz="UTC")
    for w in windows:
        # A window that starts before the seam must finish at or before it.
        if w.train_start < seam:
            assert w.test_end <= seam, f"window spanned seam: {w}"
        else:
            assert w.train_start >= seam, f"window spanned seam: {w}"
