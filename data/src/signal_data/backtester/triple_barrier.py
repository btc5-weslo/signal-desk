"""Triple-barrier exit logic shared by the backtester and the live tracker.

A trade that fills on next-bar open (plus slippage) ends at the first of:

- stop_loss
- the first take_profit
- timeout at horizon_bars (counting the fill bar)

Gap rule: if a bar's *open* is already past the stop or the first target,
exit at that open, not at the level. If stop and target are both touched
inside the same bar (no gap through either), the stop is assumed to hit
first (conservative, no intra-bar path).

R is computed from the actual fill and the stop distance, after fees.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from signal_shared import ExitReason, Side

from signal_data.backtester.costs import (
    CostModel,
    apply_entry_slippage,
    apply_exit_slippage,
    apply_stop_slippage,
    net_return_after_costs,
    r_multiple_after_costs,
)


@dataclass
class BarrierResult:
    exit_reason: ExitReason
    exit_price: float
    exit_time: datetime
    gap_exit: bool
    bars_held: int  # 1 if entered and exited on the fill bar
    fill_price: float
    net_return: float
    r_multiple: float


def _first_tp(side: str, take_profit: list[float]) -> float:
    tps = [float(x) for x in take_profit]
    if not tps:
        raise ValueError("take_profit is required")
    return min(tps) if side == "long" else max(tps)


def open_past_level(side: str, open_price: float, stop: float, first_tp: float) -> str | None:
    """Return 'sl' or 'tp' if the open has already gapped through a barrier, else None."""
    if side == "long":
        if open_price <= stop:
            return "sl"
        if open_price >= first_tp:
            return "tp"
    else:
        if open_price >= stop:
            return "sl"
        if open_price <= first_tp:
            return "tp"
    return None


def intra_bar_hit(side: str, bar: pd.Series, stop: float, first_tp: float) -> str | None:
    """If both levels trade in the bar, return 'sl' (conservative)."""
    high = float(bar["high"])
    low = float(bar["low"])
    if side == "long":
        stop_hit = low <= stop
        tp_hit = high >= first_tp
    else:
        stop_hit = high >= stop
        tp_hit = low <= first_tp
    if stop_hit:
        return "sl"
    if tp_hit:
        return "tp"
    return None


def evaluate_barriers(
    bars: pd.DataFrame,
    *,
    fill_index: int,
    side: str,
    stop_loss: float,
    take_profit: list[float],
    horizon_bars: int,
    cost: CostModel,
    atr: float | None = None,
    apply_level_slippage: bool = True,
) -> BarrierResult | None:
    """Evaluate a trade that is intended to fill at bars[fill_index].open.

    Delegates to ``signal_data.barriers.resolve`` (the single implementation).
    Returns None if there is no fill bar (signal at the last bar).
    """
    if fill_index >= len(bars) or horizon_bars < 1:
        return None
    from types import SimpleNamespace

    # Imported here: signal_data.barriers imports signal_data.backtester.costs,
    # so a module-level import made `import signal_data.barriers` fail when it
    # was the first import in a fresh process (circular import).
    from signal_data.barriers import resolve

    fill_open = bars.iloc[fill_index]["open_time"]
    shim = SimpleNamespace(
        side=side,
        stop_loss=float(stop_loss),
        take_profit=list(take_profit),
        horizon_bars=int(horizon_bars),
        bar_close_time=fill_open,
        entry=None,
    )
    # apply_level_slippage=False is only used in tests that want raw levels;
    # resolve always uses the CostModel. Callers that want no slippage pass
    # a zero CostModel.
    outcome = resolve(shim, bars, cost=cost, atr=atr)
    if outcome.status.value == "cancelled" or outcome.exit_time is None:
        return None
    return BarrierResult(
        exit_reason=outcome.exit_reason,
        exit_price=outcome.exit_price,
        exit_time=outcome.exit_time,
        gap_exit=outcome.gap_exit,
        bars_held=outcome.bars_held,
        fill_price=outcome.fill_price,
        net_return=outcome.net_return,
        r_multiple=outcome.r_multiple,
    )
