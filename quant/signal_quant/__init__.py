"""Quant signal engine (v0).

Public surface used by Data (backtester) and QA (truncation / lookahead audits):

- ``Strategy.generate(bars_by_timeframe, as_of) -> list[Signal]``
- ``as_frame(strategy, df)`` replays ``generate`` bar by bar (the only frame adapter)
- ``load_bars_by_timeframe`` reads the Data store (canonical symbols)
- Causal, vectorized feature functions in ``signal_quant.features``
"""

from signal_quant.adapters import as_frame, qa_strategy_fn
from signal_quant.data_loader import list_available_series, load_bars_by_timeframe, load_series
from signal_quant.models import (
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
    StrategyMeta,
    Trade,
)
from signal_quant.registry import get_strategy, list_strategies, run_for_bar
from signal_quant.strategy import Strategy
from signal_quant.symbols import to_canonical_symbol

__all__ = [
    "AssetClass",
    "BacktestFlag",
    "BacktestReport",
    "Candle",
    "ExitReason",
    "OOSWindow",
    "Side",
    "Signal",
    "SignalStatus",
    "Strategy",
    "get_strategy",
    "list_strategies",
    "run_for_bar",
    "StrategyMeta",
    "TIMEFRAMES",
    "Trade",
    "as_frame",
    "list_available_series",
    "load_bars_by_timeframe",
    "load_series",
    "qa_strategy_fn",
    "to_canonical_symbol",
]
