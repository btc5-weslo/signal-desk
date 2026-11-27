"""Triple-barrier labeling: stop, first TP, timeout; same-bar collision = stop."""

from __future__ import annotations

import pandas as pd

from signal_quant.labeling import label_triple_barrier
from signal_quant.synthetic import make_synthetic_ohlcv


def _bars_from_ohlc(rows, start="2024-01-01", tf="1h"):
    idx = pd.date_range(start, periods=len(rows), freq="1h", tz="UTC")
    df = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])
    df["volume"] = 1.0
    return df


def test_same_bar_stop_and_target_counts_as_stop():
    # Signal at bar 0; fill at bar 1 open=100. That same fill bar trades 90-110,
    # touching a stop at 95 and a target at 105. Must resolve to hit_sl.
    rows = [
        dict(open=100, high=101, low=99, close=100),
        dict(open=100, high=110, low=90, close=100),
        dict(open=100, high=101, low=99, close=100),
    ]
    df = _bars_from_ohlc(rows)
    lab = label_triple_barrier(
        df,
        signal_index=0,
        side="long",
        stop_loss=95.0,
        take_profit=[105.0],
        horizon_bars=3,
        entry_price=100.0,
    )
    assert lab["outcome"] == "hit_sl"
    assert lab["bars_held"] == 1
    assert lab["r_multiple"] == -1.0


def test_first_take_profit_wins_when_stop_not_hit():
    rows = [
        dict(open=100, high=101, low=99, close=100),
        dict(open=100, high=107, low=99, close=106),  # hits TP1 105, not stop 95
        dict(open=106, high=112, low=105, close=111),
    ]
    df = _bars_from_ohlc(rows)
    lab = label_triple_barrier(
        df,
        signal_index=0,
        side="long",
        stop_loss=95.0,
        take_profit=[105.0, 111.0],
        horizon_bars=3,
        entry_price=100.0,
    )
    assert lab["outcome"] == "hit_tp"
    assert lab["exit_price"] == 105.0
    assert lab["bars_held"] == 1


def test_timeout_uses_close_at_horizon():
    df = make_synthetic_ohlcv(30, timeframe="1h", seed=0, process="range")
    entry_i = 5
    entry = float(df["open"].iloc[entry_i + 1])
    # Stops/targets far away so only timeout can fire.
    lab = label_triple_barrier(
        df,
        signal_index=entry_i,
        side="long",
        stop_loss=entry * 0.1,
        take_profit=[entry * 10],
        horizon_bars=4,
    )
    assert lab["outcome"] == "expired"
    assert lab["bars_held"] == 4
    fill_i = entry_i + 1
    last = fill_i + 4 - 1
    assert lab["exit_price"] == float(df["close"].iloc[last])
