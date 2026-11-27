"""Canonical symbol form used on every Signal and in the store.

Store / Signal.symbol form (no slash): BTC-USDT, ETH-USDT, AAPL, EURUSD.

This module does not hand-write source mappings (BTC/USDT → BTC-USDT, etc.).
It delegates to ``signal_data.symbols.to_canonical``.
"""

from __future__ import annotations


def to_canonical_symbol(symbol: str) -> str:
    """Return the store-canonical symbol, or raise if we cannot normalize."""
    from signal_quant.bars import _ensure_signal_data_path

    _ensure_signal_data_path()
    from signal_data.symbols import to_canonical

    return to_canonical(symbol)
