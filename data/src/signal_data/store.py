"""Read-only access to the locked Parquet candle store.

Official import path (stable, documented, no alternatives re-exported):

    from signal_data.store import get_candles
    from signal_data.candles import get_candles  # Backend path, same function

Importing this module has no side effects: no network, no ingestion, no writes.
``get_candles`` reads exactly one file

    {data_dir}/{asset_class}/{symbol}/{timeframe}.parquet

``data_dir`` is the store root (the directory that contains ``crypto/``,
``equity/`` and ``fx/``). Resolution order: the explicit ``data_dir``
argument, then ``SIGNAL_DATA_DIR``, then the repo default only when
``SIGNAL_ENV`` is unset or ``dev`` / ``test``. In ``staging`` / ``prod`` a
missing setting raises. There is no silent hard-coded fallback.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from signal_data.paths import TIMEFRAMES, get_store_dir
from signal_data.stale import drop_stale as _drop_stale
from signal_data.storage import read_parquet
from signal_data.symbols import asset_class_of, to_canonical


def _root(data_dir=None, store_dir=None) -> Path:
    # data_dir is the official name (store root). store_dir is the same
    # thing, kept so existing callers/tests pass an explicit root.
    explicit = data_dir if data_dir is not None else store_dir
    return get_store_dir(explicit)


def candle_path(
    symbol: str,
    timeframe: str,
    *,
    data_dir: Path | str | None = None,
    store_dir: Path | str | None = None,
) -> Path:
    """Absolute path of the single Parquet file for this series (no globbing)."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    canonical = to_canonical(symbol)
    asset_class = asset_class_of(canonical)
    return _root(data_dir, store_dir) / asset_class / canonical / f"{timeframe}.parquet"


def get_candles(
    symbol: str,
    timeframe: str,
    *,
    data_dir: Path | str | None = None,
    store_dir: Path | str | None = None,
    drop_stale: bool = True,
) -> pd.DataFrame:
    """Load one closed-bar OHLCV series from the locked store layout.

    Parameters
    ----------
    symbol:
        Any form accepted by ``to_canonical``.
    timeframe:
        One of ``15m``, ``1h``, ``4h``, ``1d``.
    data_dir:
        Store root (contains ``crypto/``, ``equity/``, ``fx/``). Overrides
        ``SIGNAL_DATA_DIR``. ``store_dir`` is an accepted alias for the same
        path (explicit, never a silent fallback).
    """
    path = candle_path(symbol, timeframe, data_dir=data_dir, store_dir=store_dir)
    if not path.is_file():
        raise FileNotFoundError(
            f"No candle file at {path}. Ingestion is explicit; nothing is fetched on read."
        )
    df = read_parquet(path)
    if drop_stale:
        df = _drop_stale(df)
    return df


def load_closed(
    symbol: str,
    timeframe: str,
    *,
    data_dir: Path | str | None = None,
    store_dir: Path | str | None = None,
    drop_stale: bool = True,
) -> pd.DataFrame:
    """Alias for ``get_candles``: closed bars only, stale rows dropped by default."""
    return get_candles(
        symbol, timeframe, data_dir=data_dir, store_dir=store_dir, drop_stale=drop_stale
    )
