"""Purged / embargoed walk-forward splits.

The embargo after each training end is at least ``horizon_bars`` (the label
horizon) so a training label cannot overlap the test fold. This module only
produces index ranges; it does not compute performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    def as_oos(self) -> dict:
        return {
            "train_start": self.train_start.to_pydatetime(),
            "train_end": self.train_end.to_pydatetime(),
            "test_start": self.test_start.to_pydatetime(),
            "test_end": self.test_end.to_pydatetime(),
        }


def embargo_bars(horizon_bars: int, extra: int = 0) -> int:
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")
    return int(horizon_bars + extra)


def expanding_walk_forward(
    index: pd.DatetimeIndex,
    *,
    n_windows: int = 5,
    train_min_bars: int = 200,
    test_bars: int = 50,
    horizon_bars: int = 16,
    embargo_extra: int = 0,
) -> list[WalkForwardWindow]:
    """Expanding train, fixed-length test, purged by an embargo of horizon_bars.

    The last ``embargo`` bars of the training sample are dropped so labels that
    would look into the embargo/test region are not used.
    """
    if not isinstance(index, pd.DatetimeIndex):
        index = pd.DatetimeIndex(index)
    n = len(index)
    gap = embargo_bars(horizon_bars, embargo_extra)
    windows: list[WalkForwardWindow] = []
    # Place n_windows test blocks walking forward, leaving room for train_min + gap.
    needed = train_min_bars + gap + test_bars
    if n < needed:
        return windows
    # Test blocks are laid out from the end of the minimum-train point to the series end.
    remaining = n - train_min_bars - gap
    if remaining < test_bars:
        return windows
    # Use non-overlapping test windows as far as they fit.
    start_test_pos = train_min_bars + gap
    pos = start_test_pos
    while pos + test_bars <= n and len(windows) < n_windows:
        test_start_i = pos
        test_end_i = pos + test_bars - 1
        train_end_i = test_start_i - gap - 1
        if train_end_i + 1 < train_min_bars:
            pos += test_bars
            continue
        windows.append(
            WalkForwardWindow(
                train_start=index[0],
                train_end=index[train_end_i],
                test_start=index[test_start_i],
                test_end=index[test_end_i],
            )
        )
        pos = test_end_i + 1 + gap  # optional gap between tests; at least move forward
        # After a test window, the next train can include it (expanding) but the
        # following test still has an embargo from the new train end.
        # Advance to the next non-overlapping test after this one; train will expand.
        # Recompute start as last test end + 1, train expands to that - gap - 1 later.
        # Simpler: next test starts at test_end + 1, train_end = next_test - gap - 1.
        pos = test_end_i + 1
    return windows


def holdout_split(
    index: pd.DatetimeIndex,
    *,
    holdout_frac: float = 0.2,
    horizon_bars: int = 16,
) -> WalkForwardWindow:
    """Single chronological holdout with an embargo between train and test."""
    if not 0.0 < holdout_frac < 0.5:
        # Keep holdout strictly smaller than half so train remains the majority.
        # 0.5 itself is rejected to avoid an ambiguous split.
        raise ValueError("holdout_frac must be in (0, 0.5)")
    if not isinstance(index, pd.DatetimeIndex):
        index = pd.DatetimeIndex(index)
    n = len(index)
    test_bars = max(1, int(round(n * holdout_frac)))
    gap = embargo_bars(horizon_bars)
    train_end_i = n - test_bars - gap - 1
    if train_end_i < 1:
        raise ValueError("series too short for the requested holdout and embargo")
    test_start_i = train_end_i + 1 + gap
    return WalkForwardWindow(
        train_start=index[0],
        train_end=index[train_end_i],
        test_start=index[test_start_i],
        test_end=index[-1],
    )


def window_to_datetimes(w: WalkForwardWindow) -> dict[str, datetime]:
    return w.as_oos()
