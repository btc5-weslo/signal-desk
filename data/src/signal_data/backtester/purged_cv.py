"""Purged and embargoed time-series cross-validation (Lopez de Prado style).

For a test fold covering bars [t0, t1), any train bar whose label horizon
would overlap the test period is *purged*. An *embargo* of ``embargo_bars``
after the test fold is also removed from the train set (and, when the train
set precedes the test set, a leading embargo is not required; the purge
handles look-ahead from the end of train into test).

This module only builds splits. Combining it with a parameter-search callback
is the caller's job; reported backtests should still be walk-forward OOS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PurgedSplit:
    fold: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    purged_indices: np.ndarray
    embargo_indices: np.ndarray


def purged_embargo_splits(
    n_samples: int,
    *,
    n_splits: int = 5,
    purge_bars: int,
    embargo_bars: int,
) -> list[PurgedSplit]:
    """Consecutive k-fold splits with purge and embargo.

    ``purge_bars`` should be the label horizon (e.g. ``horizon_bars``) so a
    train label ending after the test start is removed. ``embargo_bars`` is an
    additional gap after the test fold before train resumes.
    """
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if n_samples < n_splits:
        raise ValueError("not enough samples for the requested number of splits")
    if purge_bars < 0 or embargo_bars < 0:
        raise ValueError("purge_bars and embargo_bars must be >= 0")

    fold_sizes = [n_samples // n_splits] * n_splits
    for i in range(n_samples % n_splits):
        fold_sizes[i] += 1

    bounds = []
    cursor = 0
    for sz in fold_sizes:
        bounds.append((cursor, cursor + sz))
        cursor += sz

    splits: list[PurgedSplit] = []
    all_idx = np.arange(n_samples)
    for fold, (t0, t1) in enumerate(bounds):
        test = all_idx[t0:t1]
        # Purge: train labels that overlap test. A bar i has a label covering
        # (i, i+purge_bars]; it overlaps test if i < t1 and i + purge_bars >= t0.
        purged_mask = (all_idx < t1) & (all_idx + purge_bars >= t0)
        purged_mask[t0:t1] = False  # test itself is not "purged", it's test
        # Embargo after the test fold
        e0, e1 = t1, min(n_samples, t1 + embargo_bars)
        embargo_mask = np.zeros(n_samples, dtype=bool)
        embargo_mask[e0:e1] = True
        train_mask = np.ones(n_samples, dtype=bool)
        train_mask[t0:t1] = False
        train_mask[purged_mask] = False
        train_mask[embargo_mask] = False
        splits.append(
            PurgedSplit(
                fold=fold,
                train_indices=all_idx[train_mask],
                test_indices=test,
                purged_indices=all_idx[purged_mask],
                embargo_indices=all_idx[embargo_mask],
            )
        )
    return splits


def assert_no_overlap(split: PurgedSplit, *, purge_bars: int) -> None:
    """Raise if any train index's horizon overlaps the test fold (sanity check)."""
    if len(split.test_indices) == 0:
        return
    t0 = int(split.test_indices[0])
    t1 = int(split.test_indices[-1]) + 1
    for i in split.train_indices:
        # label window (i, i+purge_bars] overlaps [t0, t1)
        if i < t1 and (i + purge_bars) >= t0:
            raise AssertionError(
                f"train index {i} with purge_bars={purge_bars} overlaps test [{t0}, {t1})"
            )
    for i in split.embargo_indices:
        if i in set(split.train_indices):
            raise AssertionError(f"embargo index {i} leaked into train")


def splits_from_bars(
    bars: pd.DataFrame,
    *,
    n_splits: int = 5,
    purge_bars: int,
    embargo_bars: int,
) -> list[PurgedSplit]:
    work = bars.sort_values("close_time").reset_index(drop=True)
    return purged_embargo_splits(len(work), n_splits=n_splits, purge_bars=purge_bars, embargo_bars=embargo_bars)
