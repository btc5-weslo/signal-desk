"""No-lookahead guarantees: fills, generate() slices, higher-timeframe close only."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from signal_shared import AssetClass, Side, Signal, SignalStatus

from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import run_backtest, slice_bars
from signal_data.backtester.strategy import as_frame
from tests.toy import make_bars


START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _signal(bar_close, entry, stop, tp, side="long", horizon=5) -> Signal:
    return Signal(
        id="t1",
        strategy_id="toy",
        strategy_version="v1",
        symbol="AAPL",
        asset_class=AssetClass.equity,
        timeframe="1d",
        side=Side(side),
        generated_at=bar_close,
        bar_close_time=bar_close,
        entry=entry,
        stop_loss=stop,
        take_profit=[tp],
        horizon_bars=horizon,
        confidence=0.5,
        rationale="unit test signal",
        status=SignalStatus.active,
        is_mock=True,
    )


def test_fill_is_next_bar_open_not_signal_close():
    # Signal bar closes at 12; next bar opens at 20. Fill must be 20, not 12.
    # Wide stop/target so the trade is not immediately exited by a gap.
    path = [
        (10, 12, 10, 12),  # signal bar
        (20, 21, 19, 20.5),  # fill bar: open 20, range misses 16/26
        (20.5, 21, 20, 20.8),
        (20.8, 21, 20, 20.9),
        (20.9, 21, 20, 21.0),
        (21.0, 21.2, 20.5, 21.0),
    ]
    bars = make_bars(START, 0, path=path)
    sig_close = bars.iloc[0]["close_time"].to_pydatetime()
    sig = _signal(sig_close, entry=12.0, stop=8.0, tp=40.0, horizon=5)
    run = run_backtest(
        bars,
        symbol="AAPL",
        timeframe="1d",
        signals=[sig],
        cost=CostModel(fee_bps=0.0, slippage_bps=0.0),
    )
    assert run.report.trade_count == 1
    trade = run.audits[0]
    assert trade.reference_entry == 12.0
    assert trade.entry_price == pytest.approx(20.0)
    assert trade.entry_time == bars.iloc[1]["open_time"].to_pydatetime()
    # Must not fill at the signal bar close or open
    assert trade.entry_price != 12.0


def test_generate_only_sees_closed_bars_up_to_as_of():
    seen = []

    class Probe:
        def generate(self, bars_by_timeframe, as_of):
            df = bars_by_timeframe["1d"]
            assert df["close_time"].max() <= pd.Timestamp(as_of)
            # no future row leaked
            seen.append((pd.Timestamp(as_of), int(len(df)), float(df["close"].iloc[-1])))
            return []

    closes = list(range(100, 130))
    bars = make_bars(START, 0, closes=closes)
    run_backtest(bars, symbol="AAPL", timeframe="1d", strategy=Probe(), cost=CostModel(0, 0))
    assert len(seen) == len(bars)
    for i, (as_of, n, last) in enumerate(seen):
        assert n == i + 1
        assert last == pytest.approx(float(closes[i]))
        assert as_of == bars.iloc[i]["close_time"]


def test_higher_timeframe_excludes_partially_formed_bar():
    # 4h bars: one closes at 08:00, next would close at 12:00.
    # At 10:00 (a 1h close), the 12:00 4h bar must not be visible.
    h1 = make_bars(START, 12, timeframe="1h", closes=list(range(100, 112)))
    h4 = make_bars(START, 3, timeframe="4h", closes=[100.0, 104.0, 108.0])
    # as_of = close of the 1h bar that starts at 09:00 (close 10:00)
    as_of = h1.iloc[9]["close_time"]  # 10:00 if start is 00:00
    sliced = slice_bars({"1h": h1, "4h": h4}, as_of)
    assert sliced["1h"]["close_time"].max() <= as_of
    assert sliced["4h"]["close_time"].max() <= as_of
    # The 4h bar with close 12:00 must be absent
    closes_4h = list(sliced["4h"]["close_time"])
    assert all(ct <= as_of for ct in closes_4h)
    assert len(sliced["4h"]) == 2  # 04:00 and 08:00 closes only (start 00:00)


def test_as_frame_truncation_matches_full_history_at_t():
    """QA-style truncation: signal at t on data[:t] equals signal at t on the prefix replay."""

    class LastCloseLong:
        """Emits a long only when the last close > previous close; uses only prefix data."""

        def generate(self, bars_by_timeframe, as_of):
            df = bars_by_timeframe["1d"]
            if len(df) < 2:
                return []
            if float(df["close"].iloc[-1]) <= float(df["close"].iloc[-2]):
                return []
            close = float(df["close"].iloc[-1])
            ct = df.iloc[-1]["close_time"].to_pydatetime()
            return [
                Signal(
                    id=f"s-{ct.date()}",
                    strategy_id="toy",
                    strategy_version="v1",
                    symbol="AAPL",
                    asset_class=AssetClass.equity,
                    timeframe="1d",
                    side=Side.long,
                    generated_at=ct,
                    bar_close_time=ct,
                    entry=close,
                    stop_loss=close * 0.9,
                    take_profit=[close * 1.2],
                    horizon_bars=3,
                    confidence=0.5,
                    rationale="unit test",
                )
            ]

    closes = [100, 101, 99, 102, 103, 100, 104]
    bars = make_bars(START, 0, closes=closes)
    strat = LastCloseLong()
    full = as_frame(strat, bars, timeframe="1d")
    for t in range(len(bars)):
        part = as_frame(strat, bars.iloc[: t + 1].copy(), timeframe="1d")
        assert part.iloc[-1]["side"] == full.iloc[t]["side"]
        if full.iloc[t]["side"] != "flat":
            assert part.iloc[-1]["entry"] == pytest.approx(full.iloc[t]["entry"])
