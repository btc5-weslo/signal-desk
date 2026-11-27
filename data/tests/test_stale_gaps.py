"""Stale bars must not hide holes: gap_segments, resample_closed, data_quality_warning.

All three tests use a real BNB-USDT 15m stretch (2020-06-20) that contains
stale bars (volume==0 and o==h==l==c), excerpted from the ingested series.
Nothing in the fixture is synthesized.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from signal_data.backtester.flags import compute_flags
from signal_data.cleaning import clean_ohlcv
from signal_data.resample import resample_closed, resample_closed_result
from signal_data.stale import (
    STALE_RUN_GAP_BARS,
    drop_stale,
    gap_segments,
    has_large_gaps,
    has_stale_runs_gt,
    stale_mask,
    stale_run_lengths,
)
from signal_shared import BacktestFlag

FIXTURE = Path(__file__).parent / "fixtures" / "bnb_usdt_15m_stale_2020-06-20.parquet"


def _load() -> pd.DataFrame:
    df = pd.read_parquet(FIXTURE)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df.sort_values("open_time").reset_index(drop=True)


def test_fixture_is_real_bnb_15m_with_stale_runs():
    df = _load()
    assert len(df) >= 40
    assert (df["source"].str.contains("ccxt") | (df["source"].str.len() > 0)).all()
    mask = stale_mask(df)
    assert int(mask.sum()) >= 20
    # The known 20-bar stale run 12:15–17:00 UTC
    run = df[(df.open_time >= "2020-06-20 12:15:00+00:00") & (df.open_time <= "2020-06-20 17:00:00+00:00")]
    assert len(run) == 20
    assert stale_mask(run).all()
    assert STALE_RUN_GAP_BARS == 3


def test_gap_segments_treats_stale_as_missing_and_drop_does_not_hide_hole():
    """A run of more than 3 stale bars is a gap and starts a new segment.

    The segments must be identical whether stale rows are still present or
    have been dropped — dropping must never hide the hole.
    """
    raw = _load()
    dropped = drop_stale(raw)
    assert len(dropped) < len(raw)

    segs_raw = gap_segments(raw, "15m")
    segs_dropped = gap_segments(dropped, "15m")
    assert segs_raw == segs_dropped
    assert len(segs_raw) >= 2  # the 20-bar run (and the later 5-bar run) split the day

    # First segment of real bars ends at 12:00, just before the 20-bar stale run.
    assert segs_raw[0].end == pd.Timestamp("2020-06-20 12:00:00", tz="UTC")
    # Next segment starts at the first real bar after that run (17:15).
    assert segs_raw[1].start == pd.Timestamp("2020-06-20 17:15:00", tz="UTC")

    # Isolated stale bars (10:15, 10:45) are missing count 1, not > 3, so they
    # do not start a new segment: 10:00 and 11:00 stay in the first segment.
    assert segs_raw[0].start == pd.Timestamp("2020-06-20 10:00:00", tz="UTC")

    # A later run of 5 stale bars (17:30–18:30) also splits.
    starts = [s.start for s in segs_raw]
    assert pd.Timestamp("2020-06-20 18:45:00", tz="UTC") in starts


def test_resample_closed_incomplete_if_bucket_contains_stale_source_bars():
    """A higher-timeframe bucket that contains any stale 15m bar is incomplete."""
    df = _load()
    result = resample_closed_result(df, "1h", asset_class="crypto", source_timeframe="15m")
    kept = set(result.bars["open_time"]) if len(result.bars) else set()

    # 11:00–12:00 UTC has four real 15m bars (11:00, 11:15, 11:30, 11:45).
    complete = pd.Timestamp("2020-06-20 11:00:00", tz="UTC")
    assert complete in kept
    row = result.bars.loc[result.bars["open_time"] == complete].iloc[0]
    assert int(row["expected_bars"]) == 4

    # 10:00–11:00 contains stale 15m bars at 10:15 and 10:45.
    stale_bucket = pd.Timestamp("2020-06-20 10:00:00", tz="UTC")
    assert stale_bucket not in kept
    dropped_10 = [d for d in result.dropped if d.open_time == stale_bucket]
    assert dropped_10 and dropped_10[0].reason == "stale_source_bars"
    assert dropped_10[0].expected_bars == 4
    assert dropped_10[0].actual_bars < 4

    # 12:00–13:00: 12:00 is real, 12:15/12:30/12:45 are stale.
    noon = pd.Timestamp("2020-06-20 12:00:00", tz="UTC")
    assert noon not in kept
    dropped_12 = [d for d in result.dropped if d.open_time == noon]
    assert dropped_12 and dropped_12[0].reason == "stale_source_bars"

    # Same rule at 4h: 12:00–16:00 and 16:00–20:00 both contain stale 15m bars.
    r4 = resample_closed_result(df, "4h", asset_class="crypto", source_timeframe="15m")
    kept4 = set(r4.bars["open_time"]) if len(r4.bars) else set()
    for ts in ("2020-06-20 12:00:00", "2020-06-20 16:00:00"):
        t = pd.Timestamp(ts, tz="UTC")
        assert t not in kept4
        reasons = [d.reason for d in r4.dropped if d.open_time == t]
        assert reasons == ["stale_source_bars"]

    # And after drop_stale, those buckets are still incomplete (hole not hidden).
    r4_dropped = resample_closed(drop_stale(df), "4h", asset_class="crypto", source_timeframe="15m")
    kept4d = set(r4_dropped["open_time"]) if len(r4_dropped) else set()
    assert pd.Timestamp("2020-06-20 12:00:00", tz="UTC") not in kept4d
    assert pd.Timestamp("2020-06-20 16:00:00", tz="UTC") not in kept4d


def test_stale_run_longer_than_3_sets_data_quality_warning():
    """Runs longer than 3 stale/missing bars set data_quality_warning."""
    df = _load()
    assert has_stale_runs_gt(df, "15m", 3)
    assert has_large_gaps(df, "15m")
    # Still true after the stale rows are dropped — the hole remains.
    assert has_stale_runs_gt(drop_stale(df), "15m", 3)
    assert has_large_gaps(drop_stale(df), "15m")
    lengths = stale_run_lengths(df, "15m")
    assert max(lengths) >= 20
    assert any(n > 3 for n in lengths)

    cleaned, report = clean_ohlcv(
        df, symbol="BNB-USDT", asset_class="crypto", timeframe="15m", source="ccxt:binanceus"
    )
    assert report.n_stale_bars >= 20
    assert report.n_stale_runs_gt_3 >= 1
    assert any("longer than 3 bars" in w for w in report.warnings)

    flags = compute_flags(
        trades=[],
        win_rate_reported=0.0,
        profit_factor_reported=0.0,
        sharpe=0.0,
        has_oos_windows=True,
        oos_bar_count=200,
        data_quality_warning=has_large_gaps(df, "15m"),
    )
    assert BacktestFlag.data_quality_warning in flags
