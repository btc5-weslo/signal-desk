"""Event-driven backtester, walk-forward, and purged/embargoed CV."""

from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import run_backtest, slice_bars, BacktestRun
from signal_data.backtester.purged_cv import purged_embargo_splits, splits_from_bars
from signal_data.backtester.strategy import BarStrategy, SmaCrossoverPlaceholder, as_frame
from signal_data.backtester.walk_forward import walk_forward, rolling_windows

__all__ = [
    "CostModel",
    "run_backtest",
    "slice_bars",
    "BacktestRun",
    "purged_embargo_splits",
    "splits_from_bars",
    "BarStrategy",
    "SmaCrossoverPlaceholder",
    "as_frame",
    "walk_forward",
    "rolling_windows",
]
