"""Populate the locked BacktestFlag vocabulary on every report."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from signal_shared import BacktestFlag, Trade

from signal_data.backtester.metrics import profit_factor, win_rate

# Re-export the canonical enum so Data code can import it from one place too.
# The official schema name is BacktestFlag (shared).
__all__ = ["BacktestFlag", "compute_flags", "aggregate_flags", "RECOMPUTE_TOLERANCE"]

RECOMPUTE_TOLERANCE = 1e-9
LOW_OOS_TRADES = 100


def compute_flags(
    *,
    trades: Iterable[Trade | Any],
    win_rate_reported: float,
    profit_factor_reported: float | None,
    sharpe: float | None,
    oos_bar_count: int | None = None,
    min_oos_bars: int = 60,
    has_oos_windows: bool | None = None,
    data_quality_warning: bool = False,
    metric_undefined: bool | None = None,
) -> list[BacktestFlag]:
    """Return the locked flag set for one (strategy_id, version, symbol, timeframe) report.

    ``metric_recompute_mismatch`` is set when win_rate or profit_factor rebuilt
    from the trade list differs from the reported value by more than 1e-9
    (None == None counts as a match).

    ``metric_undefined`` is set when any reported metric is null because it is
    mathematically undefined (e.g. profit factor with no losing trades). If the
    caller does not say, it is inferred from profit_factor / sharpe being None.
    """
    rows = list(trades)
    flags: list[BacktestFlag] = []
    n = len(rows)
    if n < LOW_OOS_TRADES:
        flags.append(BacktestFlag.low_oos_trades)
    if sharpe is not None and sharpe > 3:
        flags.append(BacktestFlag.sharpe_gt_3)
    if win_rate_reported > 0.75:
        flags.append(BacktestFlag.win_rate_gt_75)

    recomputed_wr = win_rate(rows)
    recomputed_pf = profit_factor(rows)
    if (recomputed_pf is None) != (profit_factor_reported is None):
        pf_mismatch = True
    elif recomputed_pf is None:
        pf_mismatch = False
    else:
        pf_mismatch = abs(recomputed_pf - float(profit_factor_reported)) > RECOMPUTE_TOLERANCE
    if abs(recomputed_wr - float(win_rate_reported)) > RECOMPUTE_TOLERANCE or pf_mismatch:
        flags.append(BacktestFlag.metric_recompute_mismatch)

    insufficient = False
    if has_oos_windows is False:
        insufficient = True
    if oos_bar_count is not None and oos_bar_count < min_oos_bars:
        insufficient = True
    if insufficient:
        flags.append(BacktestFlag.insufficient_oos_history)

    if data_quality_warning:
        flags.append(BacktestFlag.data_quality_warning)

    if metric_undefined is None:
        metric_undefined = profit_factor_reported is None or sharpe is None
    if metric_undefined:
        flags.append(BacktestFlag.metric_undefined)

    # stable unique order matching the enum declaration
    order = list(BacktestFlag)
    seen = set(flags)
    return [f for f in order if f in seen]


def aggregate_flags(children_flags: Iterable[Iterable[BacktestFlag | str]]) -> list[BacktestFlag]:
    """Union of child-report flags, in enum declaration order."""
    seen: set[BacktestFlag] = set()
    for group in children_flags:
        for f in group:
            seen.add(f if isinstance(f, BacktestFlag) else BacktestFlag(f))
    return [f for f in BacktestFlag if f in seen]
