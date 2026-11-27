"""Per-strategy aggregate reports.

Child reports are keyed by (strategy_id, version, symbol, timeframe).
The aggregate has symbol=timeframe=null and carries the union of child flags,
plus any flags that apply to the combined trade list (e.g. recompute mismatch
or low_oos_trades on the totals).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from signal_shared import BacktestFlag, BacktestReport

from signal_data.backtester.engine import BacktestRun
from signal_data.backtester.flags import aggregate_flags, compute_flags
from signal_data.backtester.metrics import UNDEFINABLE, summarize, undefined_metrics
from signal_data.hashing import data_hash, run_id
from signal_data.timeutil import to_utc_datetime


def aggregate_reports(
    children: list[BacktestReport] | list[BacktestRun],
    *,
    equity: pd.Series | None = None,
    position_flags: pd.Series | None = None,
    data_paths: list | None = None,
) -> BacktestReport:
    reports: list[BacktestReport] = []
    audits_equity = []
    for c in children:
        if isinstance(c, BacktestRun):
            reports.append(c.report)
            if equity is None:
                audits_equity.append(c)
        else:
            reports.append(c)
    if not reports:
        raise ValueError("aggregate_reports requires at least one child report")
    sid = reports[0].strategy_id
    ver = reports[0].version
    for r in reports:
        if r.strategy_id != sid or r.version != ver:
            raise ValueError("all child reports must share strategy_id and version")
        if r.symbol is None or r.timeframe is None:
            raise ValueError("child reports must be per-market (symbol and timeframe set)")

    trades = [t for r in reports for t in r.trades]
    windows = [w for r in reports for w in r.oos_windows]
    starts = [r.period["start"] for r in reports if "start" in r.period]
    ends = [r.period["end"] for r in reports if "end" in r.period]
    period = {
        "start": min(starts) if starts else reports[0].period.get("start"),
        "end": max(ends) if ends else reports[0].period.get("end"),
    }
    fees = reports[0].fees_bps
    slip = reports[0].slippage_bps

    if equity is None or equity.empty:
        # Metrics that need an equity curve fall back to a unit curve of trade returns.
        rets = [float(t.net_return) for t in trades]
        eq_vals = [1.0]
        for r in rets:
            eq_vals.append(eq_vals[-1] * (1.0 + r))
        equity = pd.Series(eq_vals)
        flags_series = pd.Series([1] * (len(eq_vals) - 1) + [0])
    else:
        flags_series = position_flags if position_flags is not None else pd.Series(dtype=float)

    # Use 1d / mixed annualization for the aggregate
    metrics = summarize(trades, equity, flags_series, timeframe="1d", asset_class=None)
    child_flag_union = aggregate_flags(r.flags for r in reports)
    # Recompute flags on the combined book, then union with children
    own = compute_flags(
        trades=trades,
        win_rate_reported=metrics["win_rate"],
        profit_factor_reported=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        has_oos_windows=bool(windows),
        data_quality_warning=BacktestFlag.data_quality_warning in child_flag_union,
        metric_undefined=bool(undefined_metrics({k: metrics[k] for k in UNDEFINABLE}))
        or any(undefined_metrics(w.metrics) for w in windows),
    )
    # Union: children + own (own already includes quality if we passed it)
    flags = aggregate_flags([child_flag_union, own])

    paths = data_paths or []
    dhash = data_hash(paths) if paths else reports[0].data_hash
    cfg = {"strategy_id": sid, "version": ver, "mode": "strategy_aggregate"}
    rid = run_id(sid, cfg, dhash + ":aggregate")
    return BacktestReport(
        strategy_id=sid,
        version=ver,
        period=period,
        oos_windows=windows,
        trades=trades,
        trade_count=len(trades),
        win_rate=metrics["win_rate"],
        profit_factor=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        sortino=metrics["sortino"],
        max_drawdown=metrics["max_drawdown"],
        avg_R=metrics["avg_R"],
        exposure=metrics["exposure"],
        fees_bps=fees,
        slippage_bps=slip,
        run_id=rid,
        data_hash=dhash,
        symbol=None,
        timeframe=None,
        flags=flags,
    )
