"""Locked BacktestFlag vocabulary and metric recompute check."""

from __future__ import annotations

from datetime import datetime, timezone

from signal_shared import BacktestFlag, ExitReason, Side

from signal_data.backtester.flags import aggregate_flags, compute_flags
from signal_data.backtester.metrics import profit_factor, win_rate
from signal_data.schema import TradeAudit


def _trades(nets):
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    for n in nets:
        out.append(
            TradeAudit(
                symbol="AAPL",
                side=Side.long,
                reference_entry=100.0,
                entry_time=ts,
                exit_time=ts,
                entry_price=100.0,
                exit_price=100.0,
                stop_loss=95.0,
                exit_reason=ExitReason.tp if n > 0 else ExitReason.sl,
                r_multiple=1.0 if n > 0 else -1.0,
                bars_held=1,
                net_return=n,
            )
        )
    return out


def test_flag_enum_has_exactly_seven_values():
    # metric_undefined added 2026-11-26: undefined metrics are null + this flag.
    assert [f.value for f in BacktestFlag] == [
        "low_oos_trades",
        "sharpe_gt_3",
        "win_rate_gt_75",
        "metric_recompute_mismatch",
        "insufficient_oos_history",
        "data_quality_warning",
        "metric_undefined",
    ]


def test_low_oos_sharpe_winrate_quality_history_flags():
    trades = _trades([0.1] * 10)  # 10 wins, wr=1.0, pf infinite-capped
    flags = compute_flags(
        trades=trades,
        win_rate_reported=win_rate(trades),
        profit_factor_reported=profit_factor(trades),
        sharpe=3.1,
        has_oos_windows=False,
        data_quality_warning=True,
    )
    assert BacktestFlag.low_oos_trades in flags
    assert BacktestFlag.sharpe_gt_3 in flags
    assert BacktestFlag.win_rate_gt_75 in flags
    assert BacktestFlag.insufficient_oos_history in flags
    assert BacktestFlag.data_quality_warning in flags
    assert BacktestFlag.metric_recompute_mismatch not in flags


def test_metric_recompute_mismatch_when_reported_differs():
    trades = _trades([0.10, -0.05, 0.05])  # wr=2/3, pf=3
    wr = win_rate(trades)
    pf = profit_factor(trades)
    # Honest report: no mismatch
    flags = compute_flags(
        trades=trades,
        win_rate_reported=wr,
        profit_factor_reported=pf,
        sharpe=0.5,
        has_oos_windows=True,
        oos_bar_count=200,
    )
    assert BacktestFlag.metric_recompute_mismatch not in flags
    # Lie about win_rate by more than 1e-9
    flags = compute_flags(
        trades=trades,
        win_rate_reported=wr + 1e-8,
        profit_factor_reported=pf,
        sharpe=0.5,
        has_oos_windows=True,
        oos_bar_count=200,
    )
    assert BacktestFlag.metric_recompute_mismatch in flags
    # Lie about profit_factor
    flags = compute_flags(
        trades=trades,
        win_rate_reported=wr,
        profit_factor_reported=pf + 1e-8,
        sharpe=0.5,
        has_oos_windows=True,
        oos_bar_count=200,
    )
    assert BacktestFlag.metric_recompute_mismatch in flags


def test_aggregate_flags_is_union_in_enum_order():
    a = [BacktestFlag.sharpe_gt_3, BacktestFlag.low_oos_trades]
    b = [BacktestFlag.data_quality_warning, BacktestFlag.sharpe_gt_3]
    u = aggregate_flags([a, b])
    assert u == [
        BacktestFlag.low_oos_trades,
        BacktestFlag.sharpe_gt_3,
        BacktestFlag.data_quality_warning,
    ]
