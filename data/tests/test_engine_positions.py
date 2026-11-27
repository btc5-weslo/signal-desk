"""Engine position state (fix for the 2026-11-26 `in_trade` bug).

A position is open from its fill (next bar open) until the exit_time that
``signal_data.barriers.resolve`` returns. Signals emitted while a position is
open are skipped; after the exit, new signals are eligible again. Nothing is
resolved after the loop: a trade still open when the bars run out is dropped
(counted in ``run.config["dropped_open_at_end"]``), and a signal on the last
bar with no fill bar is counted in ``run.config["unfilled_at_end"]``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from signal_shared import AssetClass, ExitReason, Side, Signal, SignalStatus

from signal_data.barriers import resolve
from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import run_backtest
from tests.toy import make_bars

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
COST = CostModel(fee_bps=10.0, slippage_bps=5.0)


def _sig(bars, i, *, horizon=3, stop=90.0, tp=110.0, sid=None, side="long") -> Signal:
    close_t = bars.iloc[i]["close_time"].to_pydatetime()
    return Signal(
        id=sid or f"s{i}",
        strategy_id="toy",
        strategy_version="v1",
        symbol="AAPL",
        asset_class=AssetClass.equity,
        timeframe="1d",
        side=Side(side),
        generated_at=close_t,
        bar_close_time=close_t,
        entry=float(bars.iloc[i]["close"]),
        stop_loss=stop if side == "long" else 110.0,
        take_profit=[tp if side == "long" else 90.0],
        horizon_bars=horizon,
        confidence=0.5,
        rationale="unit test signal",
        status=SignalStatus.active,
        is_mock=True,
    )


def _flat(n=40):
    # o=c=100, h=101, l=99: stop 90 / tp 110 never trade, so every trade times out.
    return make_bars(START, n)


def test_n_non_overlapping_signals_give_n_trades():
    bars = _flat()
    idx = [0, 5, 10, 15, 20, 25, 30]
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=[_sig(bars, i) for i in idx], cost=COST)
    assert run.report.trade_count == len(idx)
    assert [a.signal_id for a in run.audits] == [f"s{i}" for i in idx]
    for a, i in zip(run.audits, idx):
        assert a.entry_time == bars.iloc[i + 1]["open_time"].to_pydatetime()
        assert a.exit_reason == ExitReason.timeout and a.bars_held == 3
    assert run.config["signals_skipped_in_position"] == 0
    assert run.config["dropped_open_at_end"] == 0


def test_overlapping_signals_skipped_only_while_position_open():
    bars = _flat()
    # sig0 fills bar1 and exits at the close of bar3 (3 bars incl. fill).
    # sig1, sig2 arrive while it is open -> skipped. sig3 arrives at the close of
    # bar3, the exact exit -> eligible, fills bar4, exits close of bar6.
    # sig4..sig6 arrive while that one is open -> skipped. sig9 is after -> taken.
    idx = [0, 1, 2, 3, 4, 5, 6, 9]
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=[_sig(bars, i) for i in idx], cost=COST)
    # s6 is emitted at the close of bar6 == exit of s3's trade, so it is eligible.
    assert [a.signal_id for a in run.audits] == ["s0", "s3", "s6", "s9"]
    assert run.config["signals_skipped_in_position"] == 4  # s1, s2, s4, s5
    # no two trades overlap
    for prev, nxt in zip(run.audits, run.audits[1:]):
        assert nxt.entry_time >= prev.exit_time


def test_more_than_two_trades_per_window_regression():
    """The old engine produced ~2 trades per window by construction."""
    bars = _flat(200)
    sigs = [_sig(bars, i) for i in range(0, 190, 4)]
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=sigs, cost=COST)
    assert run.report.trade_count == len(sigs)


def test_engine_outcomes_equal_barriers_resolve_with_each_signals_horizon():
    """Parity with the live tracker: every trade is exactly barriers.resolve(signal)."""
    path = []
    px = 100.0
    for k in range(60):
        o = px
        c = px * (1.03 if (k // 3) % 2 == 0 else 0.975)
        path.append((o, max(o, c) * 1.004, min(o, c) * 0.996, c))
        px = c
    bars = make_bars(START, 0, path=path)
    sigs = []
    for j, i in enumerate(range(0, 55, 6)):
        c = float(bars.iloc[i]["close"])
        s = _sig(bars, i, horizon=[2, 5, 7][j % 3], stop=c * 0.96, tp=c * 1.05)
        sigs.append(s)
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=sigs, cost=COST)
    assert run.audits, "expected trades"
    by_id = {s.id: s for s in sigs}
    for a in run.audits:
        o = resolve(by_id[a.signal_id], bars, cost=COST)
        assert a.entry_time == o.entry_time
        assert a.exit_time == o.exit_time
        assert a.exit_price == pytest.approx(o.exit_price, abs=0)
        assert a.bars_held == o.bars_held
        assert a.exit_reason == o.exit_reason
        assert a.net_return == pytest.approx(o.net_return, abs=0)
        assert a.bars_held <= by_id[a.signal_id].horizon_bars
    assert {by_id[a.signal_id].horizon_bars for a in run.audits} >= {2, 5}


def test_trade_still_open_when_bars_run_out_is_dropped_not_resolved():
    bars = _flat(20)
    sigs = [_sig(bars, 2), _sig(bars, 16, horizon=10)]  # second needs bars 17..26, only 17..19 exist
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=sigs, cost=COST)
    assert [a.signal_id for a in run.audits] == ["s2"]
    assert run.config["dropped_open_at_end"] == 1


def test_trade_that_exits_inside_available_bars_near_end_is_kept():
    bars = _flat(20)
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=[_sig(bars, 15, horizon=4)], cost=COST)
    # fills bar16, times out at close of bar19 == last bar: fully resolved, kept.
    assert run.report.trade_count == 1
    assert run.audits[0].bars_held == 4
    assert run.config["dropped_open_at_end"] == 0


def test_signal_on_last_bar_has_no_fill_and_is_not_resolved_after_loop():
    bars = _flat(10)
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=[_sig(bars, 9)], cost=COST)
    assert run.report.trade_count == 0
    assert run.config["unfilled_at_end"] == 1


def test_strategy_path_also_reopens_after_exit():
    bars = _flat(40)

    class EveryBar:
        strategy_id = "every_bar"
        strategy_version = "v1"

        def generate(self, frames, as_of):
            df = frames["1d"]
            return [_sig(df, len(df) - 1, sid=f"g{len(df)-1}")]

    run = run_backtest(bars, symbol="AAPL", timeframe="1d", strategy=EveryBar(), cost=COST)
    # signal at close k fills k+1 and exits close k+3; next eligible signal at close k+3.
    # k = 0, 3, 6, ..., 36 fully resolve (36 -> exit close 39); 39 has no fill bar.
    assert [a.signal_id for a in run.audits] == [f"g{k}" for k in range(0, 37, 3)]


def test_barriers_is_importable_first_in_a_fresh_process():
    import subprocess
    import sys

    r = subprocess.run([sys.executable, "-c", "from signal_data.barriers import resolve"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
