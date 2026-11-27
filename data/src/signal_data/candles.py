"""Official Backend import path for candle reads.

    from signal_data.candles import get_candles

This module re-exports ``get_candles``, ``load_closed``, and ``candle_path``
from ``signal_data.store``. Importing it has no side effects: no network, no
ingestion, and no writes. ``get_candles`` / ``load_closed`` read exactly one
file,

    store/{asset_class}/{symbol}/{timeframe}.parquet

and drop stale bars (volume == 0 and open == high == low == close) by default.
"""

from __future__ import annotations

from signal_data.store import candle_path, get_candles, load_closed

__all__ = ["get_candles", "load_closed", "candle_path"]
