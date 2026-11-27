"""Purged / embargoed walk-forward windows do not overlap labels into test."""

from __future__ import annotations

from signal_quant.synthetic import make_synthetic_ohlcv
from signal_quant.walkforward import embargo_bars, expanding_walk_forward, holdout_split


def test_expanding_windows_respect_embargo():
    df = make_synthetic_ohlcv(400, timeframe="15m", seed=1, process="trend")
    horizon = 16
    windows = expanding_walk_forward(
        df.index, n_windows=4, train_min_bars=150, test_bars=40, horizon_bars=horizon
    )
    assert len(windows) >= 2
    gap = embargo_bars(horizon)
    for w in windows:
        assert w.train_end < w.test_start
        # At least ``horizon`` bars sit between train_end and test_start.
        n_gap = df.index.searchsorted(w.test_start) - df.index.searchsorted(w.train_end) - 1
        assert n_gap >= gap
        assert w.train_start <= w.train_end
        assert w.test_start <= w.test_end


def test_holdout_split_embargo():
    df = make_synthetic_ohlcv(200, timeframe="1h", seed=2, process="range")
    w = holdout_split(df.index, holdout_frac=0.2, horizon_bars=10)
    n_gap = df.index.searchsorted(w.test_start) - df.index.searchsorted(w.train_end) - 1
    assert n_gap >= 10
