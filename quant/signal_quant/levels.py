"""Entry, stop, and target helpers (ATR- and structure-based, R-multiples).

Signal.entry is the strategy *reference* price (the closed bar's close). The
backtester / live fill model uses the *next bar open* (QA checklist) — never
the signal bar's high/low as a fill. Stops and targets are absolute prices
computed from the reference entry and are held fixed in v0 (no trailing).
"""

from __future__ import annotations

from signal_quant.models import Side


def atr_levels(
    side: str,
    entry: float,
    atr: float,
    *,
    sl_atr: float = 2.0,
    tp_r: tuple[float, ...] = (1.5, 3.0),
) -> tuple[float, list[float]]:
    if atr <= 0 or sl_atr <= 0:
        raise ValueError("atr and sl_atr must be positive")
    risk = sl_atr * atr
    if side == Side.long or side == "long":
        stop = entry - risk
        tps = [entry + r * risk for r in tp_r]
    elif side == Side.short or side == "short":
        stop = entry + risk
        tps = [entry - r * risk for r in tp_r]
    else:
        raise ValueError("atr_levels requires long or short")
    return float(stop), [float(x) for x in tps]


def structure_stop(
    side: str,
    entry: float,
    swing_low: float | None,
    swing_high: float | None,
    *,
    buffer: float = 0.0,
    fallback_stop: float | None = None,
) -> float | None:
    """Structure-based stop: beyond the prior swing, with an optional buffer."""
    if side in (Side.long, "long") and swing_low is not None and not _nan(swing_low):
        stop = float(swing_low) - buffer
        if stop < entry:
            return stop
    if side in (Side.short, "short") and swing_high is not None and not _nan(swing_high):
        stop = float(swing_high) + buffer
        if stop > entry:
            return stop
    return fallback_stop


def _nan(x: float) -> bool:
    return x != x  # NaN
