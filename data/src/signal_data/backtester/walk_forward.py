"""Rolling walk-forward evaluation.

Train windows are used only to choose parameters via a callback; reported
metrics are aggregated from the out-of-sample test windows alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import pandas as pd
from signal_shared import OOSWindow

from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import BacktestRun, run_backtest
from signal_data.backtester.flags import compute_flags
from signal_data.backtester.metrics import UNDEFINABLE, summarize, undefined_metrics
from signal_data.backtester.strategy import BarStrategy
from signal_data.hashing import data_hash, run_id
from signal_data.schema import TradeAudit
from signal_data.stale import has_large_gaps, large_gap_breaks
from signal_data.timeutil import to_utc, to_utc_datetime


@dataclass
class WindowSpec:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def rolling_windows(
    bars: pd.DataFrame,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    timeframe: str | None = None,
) -> list[WindowSpec]:
    """Build rolling train/test windows over a sorted primary series.

    Windows never span a gap longer than 3x the bar interval. When such a
    gap exists, the series is split and windows are formed independently
    on each contiguous segment.
    """
    work = bars.sort_values("close_time").reset_index(drop=True)
    n = len(work)
    step = step_bars or test_bars
    if train_bars < 1 or test_bars < 1:
        raise ValueError("train_bars and test_bars must be >= 1")

    # Default: one segment. If we know the timeframe, split on large gaps.
    segments: list[tuple[int, int]] = [(0, n)]
    if timeframe is not None:
        breaks = large_gap_breaks(work, timeframe)
        if breaks:
            segments = []
            prev = 0
            for b in breaks:
                if b > prev:
                    segments.append((prev, b))
                prev = b
            if prev < n:
                segments.append((prev, n))

    out: list[WindowSpec] = []
    for lo, hi in segments:
        start = lo
        while start + train_bars + test_bars <= hi:
            tr = work.iloc[start : start + train_bars]
            te = work.iloc[start + train_bars : start + train_bars + test_bars]
            out.append(
                WindowSpec(
                    train_start=pd.Timestamp(tr["open_time"].iloc[0]),
                    train_end=pd.Timestamp(tr["close_time"].iloc[-1]),
                    test_start=pd.Timestamp(te["open_time"].iloc[0]),
                    test_end=pd.Timestamp(te["close_time"].iloc[-1]),
                )
            )
            start += step
    return out


# callback(train_bars: DataFrame) -> dict of kwargs for the strategy factory, or a BarStrategy
ParamCallback = Callable[[pd.DataFrame], dict[str, Any] | BarStrategy]


def walk_forward(
    bars: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    strategy_factory: Callable[..., BarStrategy],
    param_callback: ParamCallback,
    cost: CostModel | None = None,
    train_bars: int = 252,
    test_bars: int = 126,
    step_bars: int | None = None,
    data_paths: list | None = None,
    strategy_id: str | None = None,
    strategy_version: str = "v1",
    initial_equity: float = 100_000.0,
) -> tuple[BacktestRun, list[dict[str, Any]]]:
    """Run a rolling walk-forward backtest.

    ``param_callback`` sees only the train window and returns either a
    strategy instance or kwargs for ``strategy_factory``. Variants tried
    should be logged by the callback itself if it searches a grid; this
    function records the returned params per window.
    """
    cost = cost or CostModel()
    work = bars.copy()
    work["open_time"] = pd.to_datetime(work["open_time"], utc=True)
    work["close_time"] = pd.to_datetime(work["close_time"], utc=True)
    work = work.sort_values("open_time").reset_index(drop=True)

    windows = rolling_windows(work, train_bars=train_bars, test_bars=test_bars, step_bars=step_bars, timeframe=timeframe)
    oos_audits: list[TradeAudit] = []
    oos_windows: list[OOSWindow] = []
    window_logs: list[dict[str, Any]] = []
    pieces_equity: list[pd.Series] = []
    pieces_flags: list[pd.Series] = []

    for w in windows:
        train = work[(work["open_time"] >= w.train_start) & (work["close_time"] <= w.train_end)]
        test = work[(work["open_time"] >= w.test_start) & (work["close_time"] <= w.test_end)]
        chosen = param_callback(train)
        if isinstance(chosen, dict):
            params = dict(chosen)
            strategy = strategy_factory(**params)
        else:
            strategy = chosen
            params = {"strategy": getattr(strategy, "strategy_id", type(strategy).__name__)}
            for attr in ("fast", "slow", "stop_atr", "tp_atr", "horizon_bars"):
                if hasattr(strategy, attr):
                    params[attr] = getattr(strategy, attr)

        run = run_backtest(
            test,
            symbol=symbol,
            timeframe=timeframe,
            strategy=strategy,
            cost=cost,
            initial_equity=initial_equity,
            strategy_id=strategy_id or getattr(strategy, "strategy_id", "unknown"),
            strategy_version=strategy_version or getattr(strategy, "strategy_version", "v1"),
            data_paths=data_paths,
            period_start=to_utc_datetime(w.test_start),
            period_end=to_utc_datetime(w.test_end),
        )
        oos_audits.extend(run.audits)
        pieces_equity.append(run.equity)
        # window metrics from this test only
        m = {
            "win_rate": run.report.win_rate,
            "profit_factor": run.report.profit_factor,
            "sharpe": run.report.sharpe,
            "sortino": run.report.sortino,
            "max_drawdown": run.report.max_drawdown,
            "avg_R": run.report.avg_R,
            "exposure": run.report.exposure,
            "total_return": run.extra_metrics.get("total_return", 0.0),
        }
        oos_windows.append(
            OOSWindow(
                train_start=to_utc_datetime(w.train_start),
                train_end=to_utc_datetime(w.train_end),
                test_start=to_utc_datetime(w.test_start),
                test_end=to_utc_datetime(w.test_end),
                trades=run.report.trade_count,
                metrics=m,
            )
        )
        window_logs.append({"params": params, "trades": run.report.trade_count, "metrics": m})

    # Stitch equity curves (each test window starts at initial_equity; chain them)
    if pieces_equity:
        chained_vals = []
        chained_idx = []
        eq = initial_equity
        for series in pieces_equity:
            if series is None or series.empty:
                continue
            # rescale so the window starts from current equity
            start = float(series.iloc[0])
            if start == 0:
                continue
            scaled = series / start * eq
            chained_idx.extend(list(scaled.index))
            chained_vals.extend(list(scaled.values))
            eq = float(scaled.iloc[-1])
        equity = pd.Series(chained_vals, index=pd.DatetimeIndex(chained_idx, tz="UTC"))
        equity = equity[~equity.index.duplicated(keep="last")].sort_index()
    else:
        equity = pd.Series(dtype=float)

    flags = pd.Series(dtype=float)
    if not equity.empty:
        # exposure: fraction of OOS bars that had a position, from per-window flags if available
        flags = pd.Series(0, index=equity.index)
        # approximate from trade intervals
        for t in oos_audits:
            mask = (equity.index >= to_utc(t.entry_time)) & (equity.index <= to_utc(t.exit_time))
            flags.loc[mask] = 1

    from signal_data.symbols import asset_class_of
    from signal_data.backtester.engine import _build_equity_and_flags

    # Rebuild a single equity path over the concatenated OOS bars for consistency
    oos_bars = []
    for w in windows:
        sl = work[(work["open_time"] >= w.test_start) & (work["close_time"] <= w.test_end)]
        oos_bars.append(sl)
    oos_data = pd.concat(oos_bars, ignore_index=True) if oos_bars else work.iloc[0:0]
    if not oos_data.empty:
        equity, flags = _build_equity_and_flags(oos_data, oos_audits, initial_equity=initial_equity)

    ac = asset_class_of(symbol) if not oos_data.empty else None
    metrics = summarize(oos_audits, equity, flags, timeframe=timeframe, asset_class=ac)
    trades = [a.to_trade() for a in oos_audits]
    sid = strategy_id or getattr(strategy_factory, "strategy_id", None) or "unknown"
    # factory might be a class
    if sid == "unknown" and hasattr(strategy_factory, "__name__"):
        sid = "sma_crossover_placeholder" if "Sma" in strategy_factory.__name__ or "sma" in strategy_factory.__name__.lower() else strategy_factory.__name__
    cfg = {
        "symbol": symbol,
        "timeframe": timeframe,
        "fee_bps": cost.fee_bps,
        "slippage_bps": cost.slippage_bps,
        "train_bars": train_bars,
        "test_bars": test_bars,
        "step_bars": step_bars or test_bars,
        "mode": "walk_forward",
    }
    dhash = data_hash(data_paths or [])
    if not data_paths:
        from signal_data.backtester.engine import _bars_fingerprint
        from signal_data.hashing import config_hash

        dhash = config_hash({"fingerprint": _bars_fingerprint(work)})
    rid = run_id(str(sid), cfg, dhash)
    start = to_utc_datetime(windows[0].test_start) if windows else to_utc_datetime(work["open_time"].iloc[0])
    end = to_utc_datetime(windows[-1].test_end) if windows else to_utc_datetime(work["close_time"].iloc[-1])
    from signal_shared import BacktestReport

    oos_bar_count = int(len(oos_data)) if not oos_data.empty else 0
    flags_list = compute_flags(
        trades=trades,
        win_rate_reported=metrics["win_rate"],
        profit_factor_reported=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        oos_bar_count=oos_bar_count,
        has_oos_windows=bool(oos_windows),
        data_quality_warning=has_large_gaps(work, timeframe),
        metric_undefined=bool(undefined_metrics({k: metrics[k] for k in UNDEFINABLE}))
        or any(undefined_metrics(w.metrics) for w in oos_windows),
    )
    report = BacktestReport(
        strategy_id=str(sid),
        version=strategy_version,
        period={"start": start, "end": end},
        oos_windows=oos_windows,
        trades=trades,
        trade_count=len(trades),
        win_rate=metrics["win_rate"],
        profit_factor=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        sortino=metrics["sortino"],
        max_drawdown=metrics["max_drawdown"],
        avg_R=metrics["avg_R"],
        exposure=metrics["exposure"],
        fees_bps=cost.fee_bps,
        slippage_bps=cost.slippage_bps,
        run_id=rid,
        data_hash=dhash,
        symbol=symbol,
        timeframe=timeframe,
        flags=flags_list,
    )
    run = BacktestRun(
        report=report,
        audits=oos_audits,
        equity=equity,
        extra_metrics={k: metrics[k] for k in ("total_return", "cagr", "avg_win", "avg_loss")},
        config=cfg,
        data_paths=[str(p) for p in (data_paths or [])],
    )
    return run, window_logs
