"""Fees and slippage applied to fills.

Slippage is expressed in bps of price (default) or as a multiple of ATR when
``atr`` and ``atr_mult`` are provided. Fees are charged on both entry and exit
notional, in bps.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    atr_slippage_mult: float | None = None  # if set, slippage = atr_mult * ATR / price * 1e4 bps

    def slippage_fraction(self, *, price: float, atr: float | None = None) -> float:
        if self.atr_slippage_mult is not None:
            if atr is None or price <= 0:
                raise ValueError("ATR slippage requires a positive price and an ATR value")
            return abs(self.atr_slippage_mult) * atr / price
        return abs(self.slippage_bps) / 10_000.0

    def fee_fraction(self) -> float:
        return abs(self.fee_bps) / 10_000.0


def apply_entry_slippage(side: str, open_price: float, cost: CostModel, *, atr: float | None = None) -> float:
    """Worse fill than the open: long pays up, short sells down."""
    slip = cost.slippage_fraction(price=open_price, atr=atr)
    if side == "long":
        return open_price * (1.0 + slip)
    if side == "short":
        return open_price * (1.0 - slip)
    raise ValueError(side)


def apply_exit_slippage(side: str, price: float, cost: CostModel, *, atr: float | None = None) -> float:
    """Worse than the reference exit price for a marketable exit (timeout)."""
    slip = cost.slippage_fraction(price=price, atr=atr)
    if side == "long":
        return price * (1.0 - slip)
    if side == "short":
        return price * (1.0 + slip)
    raise ValueError(side)


def apply_stop_slippage(side: str, stop: float, cost: CostModel, *, atr: float | None = None) -> float:
    """Stop becomes a market order; fill is worse than the stop by slippage."""
    return apply_exit_slippage(side, stop, cost, atr=atr)


def net_return_after_costs(side: str, fill: float, exit_price: float, cost: CostModel) -> float:
    """Fractional return on notional after entry+exit fees. Prices already include slippage."""
    fee = cost.fee_fraction()
    if side == "long":
        gross = (exit_price - fill) / fill
    else:
        gross = (fill - exit_price) / fill
    # fees on entry notional and exit notional, expressed vs entry
    fee_drag = fee + fee * (exit_price / fill)
    return gross - fee_drag


def r_multiple_after_costs(side: str, fill: float, stop: float, exit_price: float, cost: CostModel) -> float:
    """R uses the actual fill and the stop distance; PnL is after fees (and slipped prices)."""
    if side == "long":
        risk = fill - stop
        pnl = (exit_price - fill) - cost.fee_fraction() * fill - cost.fee_fraction() * exit_price
    else:
        risk = stop - fill
        pnl = (fill - exit_price) - cost.fee_fraction() * fill - cost.fee_fraction() * exit_price
    if risk == 0:
        return float("nan")
    return pnl / risk
