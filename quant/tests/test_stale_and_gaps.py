"""Stale-bar exclusion and gap-driven indicator resets.

Masks come from official signal_data.stale (stale_mask / gap_segments),
re-exported by signal_quant.masks. Features consume those helpers, they
do not redefine them. There is no local pending copy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signal_quant.features import compute_features
from signal_quant.masks import STALE_RUN_GAP_BARS, gap_segments, is_stale, stale_mask
from signal_quant.strategies.trend import TrendEmaAdx
from signal_quant.synthetic import make_synthetic_ohlcv


def _hourly(n=80, start="2024-01-01", seed=7):
    df = make_synthetic_ohlcv(n=n, timeframe="1h", seed=seed, start=start, process="trend")
    return df


def test_is_stale_uses_column_when_present():
    df = _hourly(10)
    flag = np.zeros(len(df), dtype=bool)
    flag[3] = True
    df = df.copy()
    df["is_stale"] = flag
    mask = is_stale(df)
    assert mask.tolist() == flag.tolist()


def test_is_stale_detects_zero_volume_flat_bar():
    df = _hourly(10)
    df = df.copy()
    i = 4
    px = float(df["close"].iloc[i])
    df.iloc[i, df.columns.get_loc("open")] = px
    df.iloc[i, df.columns.get_loc("high")] = px
    df.iloc[i, df.columns.get_loc("low")] = px
    df.iloc[i, df.columns.get_loc("close")] = px
    df.iloc[i, df.columns.get_loc("volume")] = 0.0
    mask = is_stale(df)
    assert bool(mask.iloc[i])
    assert not bool(mask.iloc[i - 1])
    assert int(mask.sum()) == 1


def test_gap_segments_one_segment_when_regular():
    df = _hourly(20)
    segs = gap_segments(df, "1h")
    assert STALE_RUN_GAP_BARS == 3
    assert len(segs) == 1
    assert segs[0].start == pd.Timestamp(df["open_time"].iloc[0])
    assert segs[0].end == pd.Timestamp(df["open_time"].iloc[-1])


def test_gap_segments_splits_after_more_than_three_missing_bars():
    df = _hourly(20)
    # Drop 4 hourly bars between index 9 and 14 (keep 0..9 and 14..).
    # missing = 4, which is > STALE_RUN_GAP_BARS (3): two segments.
    kept = pd.concat([df.iloc[:10], df.iloc[14:]])
    segs = gap_segments(kept, "1h")
    assert len(segs) == 2
    assert segs[0].end == pd.Timestamp(df["open_time"].iloc[9])
    assert segs[1].start == pd.Timestamp(df["open_time"].iloc[14])


def test_gap_segments_does_not_split_for_three_or_fewer_missing():
    df = _hourly(20)
    # Drop 3 bars: missing_bars == 3, not longer than the threshold.
    kept = pd.concat([df.iloc[:10], df.iloc[13:]])
    segs = gap_segments(kept, "1h")
    assert len(segs) == 1
    assert segs[0].start == pd.Timestamp(df["open_time"].iloc[0])
    assert segs[0].end == pd.Timestamp(df["open_time"].iloc[-1])


def test_gap_segments_treats_stale_as_missing_whether_or_not_dropped():
    """A run of 4 stale bars splits the same way after drop_stale."""
    df = _hourly(20)
    raw = df.copy()
    for i in range(10, 14):
        px = float(raw["close"].iloc[i])
        raw.iloc[i, raw.columns.get_loc("open")] = px
        raw.iloc[i, raw.columns.get_loc("high")] = px
        raw.iloc[i, raw.columns.get_loc("low")] = px
        raw.iloc[i, raw.columns.get_loc("close")] = px
        raw.iloc[i, raw.columns.get_loc("volume")] = 0.0
    assert int(stale_mask(raw).sum()) == 4
    dropped = raw.loc[~stale_mask(raw)].copy()
    segs_raw = gap_segments(raw, "1h")
    segs_dropped = gap_segments(dropped, "1h")
    assert segs_raw == segs_dropped
    assert len(segs_raw) == 2
    assert segs_raw[0].end == pd.Timestamp(df["open_time"].iloc[9])
    assert segs_raw[1].start == pd.Timestamp(df["open_time"].iloc[14])


def test_features_exclude_stale_zeros_from_atr_and_volume():
    df = _hourly(60, seed=11)
    # Plant a wild stale placeholder that would smash ATR / volume if included.
    i = 40
    dirty = df.copy()
    dirty.iloc[i, dirty.columns.get_loc("open")] = 0.0
    dirty.iloc[i, dirty.columns.get_loc("high")] = 0.0
    dirty.iloc[i, dirty.columns.get_loc("low")] = 0.0
    dirty.iloc[i, dirty.columns.get_loc("close")] = 0.0
    dirty.iloc[i, dirty.columns.get_loc("volume")] = 0.0
    dirty["is_stale"] = False
    dirty.iloc[i, dirty.columns.get_loc("is_stale")] = True

    clean = df.copy()
    feats_dirty = compute_features(dirty, timeframe="1h")
    feats_clean = compute_features(clean, timeframe="1h")
    assert bool(feats_dirty["is_stale"].iloc[i])
    # On the stale bar itself, state is forward-filled from the previous good bar.
    assert feats_dirty["atr"].iloc[i] == pytest.approx(feats_dirty["atr"].iloc[i - 1], rel=0, abs=1e-12)
    # The next good bar must match a series that never saw the placeholder.
    # (After dropping the stale row, bar i+1 in dirty aligns with bar i in a
    #  skipped-row frame — compare the post-stale value to clean[i+1] which
    #  used the real bar at i. We instead recompute features on clean with
    #  bar i removed and check the first post-stale value is closer to that
    #  than to a zero-fed ATR.)
    skipped = pd.concat([clean.iloc[:i], clean.iloc[i + 1 :]])
    feats_skipped = compute_features(skipped, timeframe="1h")
    after = feats_dirty["atr"].iloc[i + 1]
    expected = feats_skipped["atr"].loc[skipped.index[i]]  # first row after the hole
    zero_fed = compute_features(dirty.drop(columns=["is_stale"]), timeframe="1h")
    # Even without the column, O=H=L=C volume=0 is detected as stale, so
    # zero_fed should also exclude it. Force a contrast by comparing against
    # raw ATR on the un-masked series.
    from signal_quant.features import atr as raw_atr

    raw = raw_atr(dirty["high"], dirty["low"], dirty["close"], 14)
    assert after == pytest.approx(float(expected), rel=1e-9, abs=1e-9)
    # A raw ATR that swallowed the 0,0,0,0 bar must differ at i+1.
    assert raw.iloc[i + 1] != pytest.approx(float(expected), rel=1e-9, abs=1e-9)
    # Volume ratio must not treat the stale 0 as a real observation.
    assert feats_dirty["volume_ratio"].iloc[i] == pytest.approx(
        feats_dirty["volume_ratio"].iloc[i - 1], rel=0, abs=1e-12
    )


def test_features_reset_after_long_gap():
    df = _hourly(80, seed=3)
    # 4-bar hole after index 40.
    kept = pd.concat([df.iloc[:41], df.iloc[45:]])
    feats = compute_features(kept, timeframe="1h")
    reset_at = df.index[45]
    # ATR window is 14: immediately at the first bar after the gap, ATR is
    # warming up again (NaN), not carried from before the gap.
    assert pd.isna(feats.loc[reset_at, "atr"])
    assert pd.isna(feats.loc[reset_at, "rsi"])
    assert pd.isna(feats.loc[reset_at, "bb_mid"])
    # And a value from just before the gap must not equal a mid-segment
    # post-reset value once the window has refilled — more importantly,
    # the first 13 post-gap ATR values should be NaN.
    post = feats.loc[reset_at:]
    # ATR needs `atr_window` (14) observations; the 14th post-gap bar (iloc[13]) is first valid.
    assert int(post["atr"].iloc[:13].isna().sum()) == 13
    assert pd.notna(post["atr"].iloc[13])


def test_generate_skips_stale_as_of_and_missing_as_of():
    df = _hourly(80, seed=5)
    strat = TrendEmaAdx("BTC-USDT", "crypto", is_mock=True)
    as_of = df.index[-1].to_pydatetime()
    # Sanity: a normal last bar is allowed to emit or not based on rules,
    # but the call itself must succeed.
    _ = strat.generate({"1h": df}, as_of)

    stale = df.copy()
    stale["is_stale"] = False
    stale.iloc[-1, stale.columns.get_loc("is_stale")] = True
    assert strat.generate({"1h": stale}, as_of) == []

    # Missing as_of: drop the last bar but ask for its close.
    assert strat.generate({"1h": df.iloc[:-1]}, as_of) == []



def test_gap_segments_splits_on_source_seam():
    """A source_seam=True bar starts a new segment even with no time hole."""
    df = _hourly(20)
    df = df.copy()
    df["source_seam"] = False
    # First bar may be False; seam at index 10 (contiguous grid).
    df.iloc[10, df.columns.get_loc("source_seam")] = True
    segs = gap_segments(df, "1h")
    assert len(segs) == 2
    assert segs[0].end == pd.Timestamp(df["open_time"].iloc[9])
    assert segs[1].start == pd.Timestamp(df["open_time"].iloc[10])
    # Without the flag, one segment.
    plain = df.drop(columns=["source_seam"])
    assert len(gap_segments(plain, "1h")) == 1
