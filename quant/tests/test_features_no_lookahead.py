"""Shifting / mutating future bars must not change past feature values."""

from __future__ import annotations

import numpy as np
import pandas as pd

from signal_quant.features import compute_features
from signal_quant.synthetic import make_synthetic_ohlcv


def test_mutating_future_bars_does_not_change_past_features():
    df = make_synthetic_ohlcv(250, timeframe="15m", seed=3, process="trend")
    feats = compute_features(df)
    mid = 120  # well after typical warmup
    # Corrupt every bar *after* mid. Past features must be identical.
    df2 = df.copy()
    rng = np.random.default_rng(99)
    future = df2.index[mid + 1 :]
    for col in ("open", "high", "low", "close", "volume"):
        shock = 1.0 + rng.uniform(0.5, 2.0, size=len(future))
        df2.loc[future, col] = df2.loc[future, col] * shock
    # Keep OHLC consistency on the shocked bars so we are testing lookahead,
    # not a crash on invalid candles.
    df2.loc[future, "high"] = df2.loc[future, ["open", "high", "close"]].max(axis=1)
    df2.loc[future, "low"] = df2.loc[future, ["open", "low", "close"]].min(axis=1)
    feats2 = compute_features(df2)
    past = feats.iloc[: mid + 1]
    past2 = feats2.iloc[: mid + 1]
    pd.testing.assert_frame_equal(past, past2, check_exact=False, atol=1e-12, rtol=0.0)


def test_features_align_with_input_index(synth_15m):
    feats = compute_features(synth_15m)
    assert feats.index.equals(synth_15m.index)
    assert not feats.columns.duplicated().any()
