"""Canonical contracts imported from ``signal_shared`` (Lead Architect, v1).

Do not fork Signal, Strategy, Candle, Trade, or BacktestReport in this package.
"""

from __future__ import annotations

try:
    from signal_shared import (
        TIMEFRAMES,
        AssetClass,
        BacktestFlag,
        BacktestReport,
        Candle,
        ExitReason,
        OOSWindow,
        Side,
        Signal,
        SignalStatus,
        Strategy as StrategyMeta,
        Trade,
    )
except ImportError as exc:  # pragma: no cover
    # TODO: this shim exists only if signal_shared is not installed. Do not
    # evolve a second contract here — fix the dependency instead.
    raise ImportError(
        "signal_quant requires signal_shared. "
        "Install the workspace package (uv sync in quant/) rather than copying models."
    ) from exc

__all__ = [
    "TIMEFRAMES",
    "AssetClass",
    "BacktestFlag",
    "BacktestReport",
    "Candle",
    "ExitReason",
    "OOSWindow",
    "Side",
    "Signal",
    "SignalStatus",
    "StrategyMeta",
    "Trade",
]
