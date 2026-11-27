"""Stale bars (volume==0 and o==h==l==c) are flagged in the raw store and dropped on read."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import run_backtest
from signal_data.backtester.walk_forward import rolling_windows
from signal_data.candles import get_candles, load_closed
from signal_data.cleaning import clean_ohlcv
from signal_data.stale import drop_stale, stale_mask, large_gap_breaks
from signal_data.storage import atomic_write_parquet
from signal_shared import AssetClass, Side, Signal, SignalStatus
from tests.toy import make_bars


def _stale_row(ts, px=100.0):
    return {
        "open_time": pd.Timestamp(ts, tz="UTC") if pd.Timestamp(ts).tzinfo is None else pd.Timestamp(ts).tz_convert("UTC"),
        "close_time": (pd.Timestamp(ts, tz="UTC") if pd.Timestamp(ts).tzinfo is None else pd.Timestamp(ts).tz_convert("UTC"))
        + pd.Timedelta(days=1),
        "open": px,
        "high": px,
        "low": px,
        "close": px,
        "volume": 0.0,
        "source": "toy",
    }


def test_stale_mask_and_drop():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    real = make_bars(start, 3, timeframe="1d")
    stale = pd.DataFrame([_stale_row("2024-01-04")])
    df = pd.concat([real, stale], ignore_index=True)
    mask = stale_mask(df)
    assert int(mask.sum()) == 1
    out = drop_stale(df)
    assert len(out) == 3
    assert not stale_mask(out).any()


def test_cleaning_keeps_stale_and_flags_them():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    real = make_bars(start, 5, timeframe="1d")
    stale = pd.DataFrame([_stale_row("2024-01-06")])  # after day 1-5 (Jan 1-5), this is Jan 6
    df = pd.concat([real, stale], ignore_index=True)
    cleaned, report = clean_ohlcv(df, symbol="BTC-USDT", asset_class="crypto", timeframe="1d", source="toy")
    assert report.n_stale_bars == 1
    assert len(cleaned) == 6  # raw store keeps the stale row
    assert "is_stale" in cleaned.columns
    assert int(cleaned["is_stale"].sum()) == 1
    assert int(stale_mask(cleaned).sum()) == 1


def test_get_candles_and_load_closed_drop_stale_by_default(tmp_path):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    real = make_bars(start, 4, timeframe="1d")
    # Force a stale row into a parquet (as if a bad write happened)
    stale = pd.DataFrame([_stale_row("2024-01-05")])
    mixed = pd.concat([real, stale], ignore_index=True)
    path = tmp_path / "crypto" / "BTC-USDT" / "1d.parquet"
    atomic_write_parquet(mixed, path)
    dropped = get_candles("BTC-USDT", "1d", store_dir=tmp_path)
    assert len(dropped) == 4
    kept = get_candles("BTC-USDT", "1d", store_dir=tmp_path, drop_stale=False)
    assert len(kept) == 5
    assert len(load_closed("BTC-USDT", "1d", store_dir=tmp_path)) == 4


def test_backtester_does_not_fill_on_stale():
    # Signal on bar 0; next bar is stale (would be a bad fill); bar 2 is the first real open.
    path = [
        (10, 12, 10, 12),
        (12, 12, 12, 12),  # will override volume to 0 to make it stale
        (20, 21, 19, 20.5),
        (20.5, 21, 20, 20.8),
        (20.8, 21, 20, 20.9),
        (20.9, 21, 20, 21.0),
        # one more real bar so the 5-bar horizon completes; the engine drops
        # (does not truncate) a trade still open when the bars run out.
        (21.0, 21.2, 20.5, 21.0),
    ]
    bars = make_bars(datetime(2024, 1, 1, tzinfo=timezone.utc), 0, path=path)
    bars.loc[1, "volume"] = 0.0
    bars.loc[1, ["open", "high", "low", "close"]] = 12.0
    sig_close = bars.iloc[0]["close_time"].to_pydatetime()
    sig = Signal(
        id="t1",
        strategy_id="toy",
        strategy_version="v1",
        symbol="AAPL",
        asset_class=AssetClass.equity,
        timeframe="1d",
        side=Side.long,
        generated_at=sig_close,
        bar_close_time=sig_close,
        entry=12.0,
        stop_loss=8.0,
        take_profit=[40.0],
        horizon_bars=5,
        confidence=0.5,
        rationale="unit test signal",
        status=SignalStatus.active,
        is_mock=True,
    )
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=[sig], cost=CostModel(0, 0))
    assert run.report.trade_count == 1
    # Fill must be the first *real* next open (20), not the stale 12
    assert run.audits[0].entry_price == pytest.approx(20.0)


def test_walk_forward_windows_split_around_gap_gt_3x():
    # 20 daily bars, then a 10-day hole, then 20 more. 3x daily = 3 days.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    left = make_bars(start, 20, timeframe="1d")
    right = make_bars(datetime(2024, 2, 10, tzinfo=timezone.utc), 20, timeframe="1d")
    bars = pd.concat([left, right], ignore_index=True)
    assert large_gap_breaks(bars, "1d") == [20]
    # train=8, test=8 would produce several windows if unsplit (40 bars)
    # After split, each side has 20 bars: floor((20-16)/8)+1 = 1 window per side if step=8
    windows = rolling_windows(bars, train_bars=8, test_bars=8, step_bars=8, timeframe="1d")
    assert len(windows) >= 2
    # No window may span the hole (left last close before 2024-02-10, right first open on 2024-02-10)
    hole = pd.Timestamp("2024-01-21", tz="UTC")  # approx inside the gap
    for w in windows:
        # window is entirely on one side of the gap
        assert not (w.train_start < hole < w.test_end)
