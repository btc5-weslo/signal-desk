"""signal-data: real-market ingestion, Parquet/DuckDB storage, event-driven backtesting."""

from __future__ import annotations

from signal_data.symbols import (
    SYMBOLS,
    to_canonical,
    to_source,
    universe_symbols,
    asset_class_of,
    SymbolError,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "SYMBOLS",
    "to_canonical",
    "to_source",
    "universe_symbols",
    "asset_class_of",
    "SymbolError",
]
