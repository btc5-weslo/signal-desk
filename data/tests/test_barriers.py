"""signal_data.barriers.resolve — one triple-barrier implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from signal_shared import ExitReason, SignalStatus

from signal_data.backtester.costs import CostModel
from signal_data.barriers import Outcome, resolve
from tests.toy import make_bars


def _signal(*, close, side="long", entry=100.0, stop=95.0, tps=None, horizon=3):
    return SimpleNamespace(
        side=side,
        stop_loss=stop,
        take_profit=list(tps or [105.0]),
        horizon_bars=horizon,
        bar_close_time=close,
        entry=entry,
    )


def test_same_bar_stop_wins_and_timeout():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # path: signal bar, fill bar that trades through both 95 and 105, then a quiet bar
    bars = make_bars(
        start,
        0,
        path=[
            (100, 101, 99, 100),
            (100, 110, 90, 100),
            (100, 101, 99, 100),
        ],
        timeframe="1h",
    )
    out = resolve(_signal(close=bars.iloc[0]["close_time"], tps=[105.0], stop=95.0, horizon=3, entry=100.0), bars)
    assert isinstance(out, Outcome)
    assert out.status == SignalStatus.hit_sl
    assert out.outcome == "hit_sl"
    assert out.exit_reason == ExitReason.sl
    assert out.bars_held == 1
    assert out.r_multiple == pytest.approx(-1.0)
    assert not out.gap_exit

    timeout = make_bars(
        start,
        0,
        path=[
            (100, 101, 99, 100),
            (100, 102, 99, 101),
            (101, 103, 100, 102),
            (102, 104, 101, 103),
        ],
        timeframe="1h",
    )
    exp = resolve(_signal(close=timeout.iloc[0]["close_time"], tps=[110.0], stop=95.0, horizon=2, entry=100.0), timeout)
    assert exp.status == SignalStatus.expired
    assert exp.bars_held == 2
    assert exp.exit_price == pytest.approx(102.0)


def test_gap_exit_at_open_not_at_level():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = make_bars(
        start,
        0,
        path=[
            (100, 101, 99, 100),
            (90, 92, 88, 91),  # opens already through the stop at 95
        ],
        timeframe="1h",
    )
    out = resolve(_signal(close=bars.iloc[0]["close_time"], stop=95.0, tps=[110.0], horizon=3), bars)
    assert out.status == SignalStatus.hit_sl
    assert out.gap_exit is True
    assert out.exit_price == pytest.approx(90.0)  # the open, not the 95 stop


def test_fill_is_next_open_plus_slippage_r_from_actual_fill():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = make_bars(
        start,
        0,
        path=[
            (100, 101, 99, 100),
            (100, 100, 90, 95),  # hits stop 95 after a slipped fill
            (95, 96, 94, 95),
        ],
        timeframe="1h",
    )
    cost = CostModel(fee_bps=0.0, slippage_bps=100.0)  # 1%
    out = resolve(
        _signal(close=bars.iloc[0]["close_time"], stop=95.0, tps=[120.0], horizon=3, entry=100.0),
        bars,
        cost=cost,
    )
    # Long fill at 100 * 1.01 = 101; stop at 95 with 1% adverse slippage = 95 * 0.99
    assert out.fill_price == pytest.approx(101.0)
    assert out.status == SignalStatus.hit_sl
    # R is measured from the actual (slipped) fill, not the reference entry.
    assert out.r_multiple < 0
    risk = out.fill_price - 95.0
    assert risk == pytest.approx(6.0)


def test_cancelled_when_no_fill_bar():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = make_bars(start, 1, timeframe="1h")
    out = resolve(_signal(close=bars.iloc[0]["close_time"]), bars)
    assert out.status == SignalStatus.cancelled
    assert out.exit_time is None
    assert out.bars_held == 0
