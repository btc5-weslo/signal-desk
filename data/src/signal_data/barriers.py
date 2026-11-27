"""Single triple-barrier implementation used by labeling, the backtester, and the tracker.

Official import::

    from signal_data.barriers import resolve, Outcome

``resolve(signal, bars)`` fills at the next bar's open plus slippage, then
exits at the first of: stop, first take-profit, or timeout at ``horizon_bars``
(counting the fill bar). If a bar opens past the stop or the first target,
the exit is that open, not the level. If stop and target are both touched
inside the same bar (no gap through either), the stop wins. R is measured
from the actual fill and the stop distance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from signal_shared import ExitReason, SignalStatus

from signal_data.backtester.costs import (
    CostModel,
    apply_entry_slippage,
    apply_exit_slippage,
    apply_stop_slippage,
    net_return_after_costs,
    r_multiple_after_costs,
)
from signal_data.stale import drop_stale
from signal_data.timeutil import to_utc, to_utc_datetime

__all__ = ["Outcome", "resolve"]


@dataclass(frozen=True)
class Outcome:
    """Public barrier result. Extra fields support the backtester and tracker."""

    status: SignalStatus
    exit_time: datetime | None
    exit_price: float
    r_multiple: float
    bars_held: int = 0
    fill_price: float = float("nan")
    net_return: float = float("nan")
    gap_exit: bool = False
    exit_reason: ExitReason | None = None
    entry_time: datetime | None = None
    fill_index: int | None = None

    @property
    def outcome(self) -> str:
        """Alias for ``status.value`` (hit_sl / hit_tp / expired / cancelled)."""
        return self.status.value


_REQUIRED = ("open_time", "close_time", "open", "high", "low", "close")

_STATUS_FOR_REASON = {
    ExitReason.sl: SignalStatus.hit_sl,
    ExitReason.tp: SignalStatus.hit_tp,
    ExitReason.timeout: SignalStatus.expired,
}


def _cancelled() -> Outcome:
    return Outcome(
        status=SignalStatus.cancelled,
        exit_time=None,
        exit_price=float("nan"),
        r_multiple=float("nan"),
        bars_held=0,
        fill_price=float("nan"),
        net_return=float("nan"),
        gap_exit=False,
        exit_reason=None,
        entry_time=None,
        fill_index=None,
    )


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=list(_REQUIRED))
    out = df.copy()
    # Accept a close-time DatetimeIndex (Quant labeling frames).
    if "close_time" not in out.columns and isinstance(out.index, pd.DatetimeIndex):
        out["close_time"] = out.index
    if "open_time" not in out.columns and "close_time" in out.columns:
        # Infer open from close if a regular timeframe is visible; otherwise
        # leave a missing open_time only when we can still identify the next bar
        # by close order. Fill index uses open_time >= signal close, so if
        # open_time is missing we synthesize it as the previous close (or the
        # close itself for the first row) — but the locked rule is fill at
        # next *open*. Prefer an explicit open column.
        if "open" in out.columns:
            # Best-effort: previous bar's close_time is this bar's open_time
            # when the frame is a regular contiguous series.
            ct = pd.to_datetime(out["close_time"], utc=True)
            out = out.sort_values("close_time") if "close_time" in out.columns else out
            # Use close_time of previous bar as open; first bar gets close - median delta.
            shifted = ct.shift(1)
            delta = ct.diff().median()
            if pd.isna(delta) or delta <= pd.Timedelta(0):
                shifted = ct  # last resort; fill still uses the next row
            else:
                shifted = shifted.fillna(ct.iloc[0] - delta)
            out["open_time"] = shifted
    for col in _REQUIRED:
        if col not in out.columns:
            raise ValueError(f"bars missing required column {col}")
    out["open_time"] = pd.to_datetime(out["open_time"], utc=True)
    out["close_time"] = pd.to_datetime(out["close_time"], utc=True)
    out = drop_stale(out)
    out = out.sort_values("open_time").drop_duplicates(subset=["open_time"], keep="last")
    return out.reset_index(drop=True)


def _next_fill_index(bars: pd.DataFrame, bar_close_time) -> int | None:
    """Index of the first bar whose open_time >= the signal's bar_close_time."""
    if bars is None or bars.empty:
        return None
    cut = to_utc(bar_close_time)
    hits = bars.index[bars["open_time"] >= cut]
    if len(hits) == 0:
        return None
    return int(hits[0])


def _first_tp(side: str, take_profit: list[float] | None) -> float | None:
    tps = [float(x) for x in (take_profit or [])]
    if not tps:
        return None
    return min(tps) if side == "long" else max(tps)


def _open_past(side: str, open_price: float, stop: float, first_tp: float | None) -> str | None:
    if side == "long":
        if open_price <= stop:
            return "sl"
        if first_tp is not None and open_price >= first_tp:
            return "tp"
    else:
        if open_price >= stop:
            return "sl"
        if first_tp is not None and open_price <= first_tp:
            return "tp"
    return None


def _intra_bar(side: str, bar: pd.Series, stop: float, first_tp: float | None) -> str | None:
    high, low = float(bar["high"]), float(bar["low"])
    if side == "long":
        stop_hit = low <= stop
        tp_hit = first_tp is not None and high >= first_tp
    else:
        stop_hit = high >= stop
        tp_hit = first_tp is not None and low <= first_tp
    if stop_hit:
        return "sl"
    if tp_hit:
        return "tp"
    return None


def _side_of(signal) -> str:
    side = getattr(signal, "side", signal)
    return side.value if hasattr(side, "value") else str(side)


def resolve(signal, bars: pd.DataFrame, *, cost: CostModel | None = None, atr: float | None = None) -> Outcome:
    """Score one signal against later bars.

    Parameters
    ----------
    signal:
        A ``Signal`` (or a signal-like object with ``side``, ``stop_loss``,
        ``take_profit``, ``horizon_bars``, ``bar_close_time``). ``entry`` is
        the reference close, not the fill.
    bars:
        OHLCV frame with ``open_time`` / ``close_time`` (or a close-time
        DatetimeIndex). Stale rows are ignored.
    cost:
        Fees and slippage. When omitted, both are zero (labeling / unit tests).
        The backtester always passes its ``CostModel``.
    """
    cost = cost or CostModel(fee_bps=0.0, slippage_bps=0.0)
    work = _prepare(bars)
    horizon = int(getattr(signal, "horizon_bars", 0) or 0)
    fill_i = _next_fill_index(work, signal.bar_close_time)
    if fill_i is None or horizon < 1 or fill_i >= len(work):
        return _cancelled()

    side = _side_of(signal)
    stop = float(signal.stop_loss)
    first_tp = _first_tp(side, list(getattr(signal, "take_profit", None) or []))
    last_i = min(fill_i + horizon - 1, len(work) - 1)

    fill_bar = work.iloc[fill_i]
    raw_open = float(fill_bar["open"])
    fill_price = apply_entry_slippage(side, raw_open, cost, atr=atr)
    entry_time = to_utc_datetime(fill_bar["open_time"])

    def _time(i: int, use_open: bool) -> datetime:
        col = "open_time" if use_open else "close_time"
        return to_utc_datetime(work.iloc[i][col])

    def _finish(reason: ExitReason, price: float, i: int, *, gap: bool) -> Outcome:
        return Outcome(
            status=_STATUS_FOR_REASON[reason],
            exit_time=_time(i, use_open=gap),
            exit_price=float(price),
            r_multiple=r_multiple_after_costs(side, fill_price, stop, price, cost),
            bars_held=i - fill_i + 1,
            fill_price=fill_price,
            net_return=net_return_after_costs(side, fill_price, price, cost),
            gap_exit=gap,
            exit_reason=reason,
            entry_time=entry_time,
            fill_index=fill_i,
        )

    for i in range(fill_i, last_i + 1):
        bar = work.iloc[i]
        raw_open_i = float(bar["open"])
        gap = _open_past(side, raw_open_i, stop, first_tp)
        if gap is not None:
            reason = ExitReason.sl if gap == "sl" else ExitReason.tp
            return _finish(reason, raw_open_i, i, gap=True)
        hit = _intra_bar(side, bar, stop, first_tp)
        if hit == "sl":
            px = apply_stop_slippage(side, stop, cost, atr=atr)
            return _finish(ExitReason.sl, px, i, gap=False)
        if hit == "tp":
            return _finish(ExitReason.tp, float(first_tp), i, gap=False)

    close_px = float(work.iloc[last_i]["close"])
    exit_px = apply_exit_slippage(side, close_px, cost, atr=atr)
    return _finish(ExitReason.timeout, exit_px, last_i, gap=False)
