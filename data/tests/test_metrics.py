"""Metric correctness on hand-computed toy series (not market data)."""

from __future__ import annotations

import math

import pandas as pd
import pytest
from signal_shared import ExitReason, Side

from signal_data.backtester.metrics import (
    avg_R,
    avg_win_loss,
    cagr,
    max_drawdown,
    profit_factor,
    sharpe,
    sortino,
    total_return,
    win_rate,
)
from signal_data.schema import TradeAudit
from datetime import datetime, timezone


def test_win_rate_profit_factor_avg_r_hand_computed():
    # Three trades: +0.10 (R=2), -0.05 (R=-1), +0.05 (R=1)
    # win_rate = 2/3, PF = 0.15/0.05 = 3, avg_R = (2-1+1)/3 = 2/3
    def T(net, r):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        return TradeAudit(
            symbol="AAPL",
            side=Side.long,
            reference_entry=100.0,
            entry_time=ts,
            exit_time=ts,
            entry_price=100.0,
            exit_price=100.0,
            stop_loss=95.0,
            exit_reason=ExitReason.tp if net > 0 else ExitReason.sl,
            r_multiple=r,
            bars_held=1,
            net_return=net,
        )

    trades = [T(0.10, 2.0), T(-0.05, -1.0), T(0.05, 1.0)]
    assert win_rate(trades) == pytest.approx(2.0 / 3.0)
    assert profit_factor(trades) == pytest.approx(3.0)
    assert avg_R(trades) == pytest.approx(2.0 / 3.0)
    aw, al = avg_win_loss(trades)
    assert aw == pytest.approx(0.075)  # (0.10+0.05)/2
    assert al == pytest.approx(-0.05)


def test_equity_curve_metrics_hand_computed():
    # Equity path: 100 -> 120 -> 108
    # total return = 8/100 = 0.08
    # period returns: +0.20, -0.10
    # mean = 0.05
    # sample std = sqrt(((0.20-0.05)^2 + (-0.10-0.05)^2) / 1) = sqrt(0.045)
    # max drawdown: peak 120 -> 108 = -12/120 = -0.10
    idx = pd.to_datetime(["2024-01-01", "2025-01-01", "2026-01-01"], utc=True)
    equity = pd.Series([100.0, 120.0, 108.0], index=idx)
    assert total_return(equity) == pytest.approx(0.08)
    assert max_drawdown(equity) == pytest.approx(-0.10)

    std = math.sqrt(0.045)
    mean = 0.05
    ppy = 1.0  # two year-apart steps; use 1 so Sharpe = mean/std
    assert sharpe(equity, periods_per_year=ppy) == pytest.approx(mean / std)
    # Sortino uses only negative returns: [-0.10], sample std of a single
    # point is NaN with ddof=1? One downside return: std(ddof=1) of a 1-element
    # series is NaN. Our series has one negative return. Handle via the
    # implementation: len(downside)==1 -> std is NaN. We also test a 3-return path.

    # CAGR convention: calendar days / 365.25 (not "exactly 2 years").
    # 2024-01-01 to 2026-01-01 is 731 days because 2024 is a leap year.
    # years = 731/365.25
    # CAGR = (108/100) ** (365.25/731) - 1 ≈ 0.03920313187118
    # (using (1.08)**0.5 - 1 ≈ 0.039230 would ignore the leap day and is wrong.)
    calendar_days = 731.0
    expected_cagr = (108.0 / 100.0) ** (365.25 / calendar_days) - 1.0
    assert cagr(equity) == pytest.approx(expected_cagr, rel=0, abs=1e-15)


def test_sortino_hand_computed():
    # Equity: 100, 110, 99, 108
    # returns: 0.10, -0.10, 0.090909...
    # downside: [-0.10] only — not enough for sample std. Use two downside pts:
    # 100, 110, 99, 89.1  (returns 0.10, -0.10, -0.10)
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"], utc=True)
    equity = pd.Series([100.0, 110.0, 99.0, 89.1], index=idx)
    rets = equity.pct_change().dropna()
    assert list(rets.round(10)) == [pytest.approx(0.10), pytest.approx(-0.10), pytest.approx(-0.10)]
    mean = float(rets.mean())
    downside = rets[rets < 0]
    dstd = float(downside.std(ddof=1))
    # two identical -0.10 values: sample std = 0 → our sortino returns 0.0
    # Change last value so downside is -0.10 and -0.20
    equity = pd.Series([100.0, 110.0, 99.0, 79.2], index=idx)
    # returns: 0.10, -0.10, -0.20
    rets = equity.pct_change().dropna()
    mean = float(rets.mean())  # (-0.20)/3 = -0.0666...
    assert mean == pytest.approx((0.10 - 0.10 - 0.20) / 3)
    downside = rets[rets < 0]  # -0.10, -0.20
    dstd = float(downside.std(ddof=1))
    # sample std of -0.10, -0.20 = sqrt(((-0.10+0.15)^2 + (-0.20+0.15)^2)/1) = sqrt(0.005)
    assert dstd == pytest.approx(math.sqrt(0.005))
    ppy = 365.0
    expected = mean / dstd * math.sqrt(ppy)
    assert sortino(equity, periods_per_year=ppy) == pytest.approx(expected)
