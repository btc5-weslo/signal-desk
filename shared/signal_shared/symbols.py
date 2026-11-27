"""Strict canonical-symbol check for the API and shared contract.

This is intentionally stricter than ``signal_data.symbols.to_canonical`` /
``to_source``. Data's helpers map vendor aliases (BTCUSDT, BTC/USDT,
EURUSD=X, aapl.us, …) onto the canonical form at ingest. Once a symbol is
on the wire (Signal, query params, candles) it must already be canonical;
``normalize_symbol`` rejects those aliases so the two modules do not fight.
"""
from __future__ import annotations

import re

# crypto: BASE-QUOTE (BTC-USDT). equity: uppercase ticker, optional class
# suffix (AAPL, BRK.B). fx: six uppercase letters (EURUSD).
_CRYPTO = re.compile(r"^[A-Z0-9]{2,10}-[A-Z0-9]{2,10}$")
_FX = re.compile(r"^[A-Z]{6}$")
# 1-5 letters, optional single-letter class share (BRK.B). 6 undotted letters are FX.
_EQUITY = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")


def _class_of_form(symbol: str) -> str | None:
    if _CRYPTO.fullmatch(symbol):
        return "crypto"
    if _FX.fullmatch(symbol):
        return "fx"
    if _EQUITY.fullmatch(symbol):
        return "equity"
    return None


def normalize_symbol(symbol: str, asset_class: str | None = None) -> str:
    """Return ``symbol`` if it is already in canonical form; else raise ValueError.

    Accepts only:
    - crypto: ``BASE-QUOTE`` (e.g. BTC-USDT) — not BTCUSDT, BTC/USDT, lowercase
    - equity: uppercase ticker (AAPL) or class shares (BRK.B)
    - fx: six uppercase letters (EURUSD) — not EURUSD=X, EUR/USD, lowercase
    """
    if not isinstance(symbol, str) or not symbol or symbol != symbol.strip():
        raise ValueError("symbol must be a non-empty canonical ticker")
    form = _class_of_form(symbol)
    if form is None:
        raise ValueError(
            f"invalid symbol {symbol!r}: use canonical form "
            "(crypto BASE-QUOTE like BTC-USDT, equity AAPL or BRK.B, fx EURUSD)"
        )
    if asset_class is not None:
        ac = asset_class.value if hasattr(asset_class, "value") else asset_class
        if ac != form:
            raise ValueError(f"symbol {symbol!r} is {form}, but asset_class={ac!r}")
    return symbol


def infer_asset_class(symbol: str) -> str:
    """Asset class implied by a canonical symbol's form."""
    canonical = normalize_symbol(symbol)
    form = _class_of_form(canonical)
    if form is None:
        raise ValueError(f"invalid symbol {canonical!r}")
    return form
