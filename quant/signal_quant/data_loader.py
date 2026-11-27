"""Load closed OHLCV bars from the Data Engineer's store for ``generate``.

Layout (locked, under the store root you pass in):

    {data_dir}/{asset_class}/{symbol}/{timeframe}.parquet

The store root is an explicit ``data_dir`` / ``root`` argument, or the
``SIGNAL_DATA_DIR`` environment variable. There is no implicit default path.

Columns: open_time, close_time (UTC), open, high, low, close, volume, source.
Closed bars only. Symbols are canonical: BTC-USDT, AAPL, EURUSD (no slash).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from signal_quant.bars import ensure_utc_index, truncate_at
from signal_quant.models import TIMEFRAMES
from signal_quant.symbols import to_canonical_symbol

SIGNAL_DATA_DIR_ENV = "SIGNAL_DATA_DIR"
ASSET_CLASSES = ("crypto", "equity", "fx")
PARQUET_COLUMNS = (
    "open_time",
    "close_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
)


class DataDirError(ValueError):
    """Raised when no store root was given and SIGNAL_DATA_DIR is unset."""


def resolve_data_dir(
    data_dir: Path | str | None = None,
    *,
    root: Path | str | None = None,
    required: bool = True,
) -> Path | None:
    """Return the store root from an explicit argument or ``SIGNAL_DATA_DIR``.

    ``root`` is accepted as an alias of ``data_dir`` (existing call sites).
    Never falls back to a hard-coded path.
    """
    explicit = data_dir if data_dir is not None else root
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get(SIGNAL_DATA_DIR_ENV)
    if env:
        return Path(env)
    if required:
        raise DataDirError(
            "No data directory given. Pass data_dir=... (or --data-dir) "
            f"or set the {SIGNAL_DATA_DIR_ENV} environment variable. "
            "There is no implicit default store path."
        )
    return None


def store_root(
    root: Path | str | None = None,
    *,
    data_dir: Path | str | None = None,
) -> Path:
    """Resolve the store root or raise ``DataDirError``."""
    resolved = resolve_data_dir(data_dir=data_dir, root=root, required=True)
    assert resolved is not None
    return resolved


def series_path(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    root: Path | str | None = None,
    data_dir: Path | str | None = None,
) -> Path:
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"asset_class must be one of {ASSET_CLASSES}, got {asset_class!r}")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES)}, got {timeframe!r}")
    canon = to_canonical_symbol(symbol)
    return store_root(root=root, data_dir=data_dir) / asset_class / canon / f"{timeframe}.parquet"


def load_series(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    root: Path | str | None = None,
    data_dir: Path | str | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Load one Parquet series. Empty frame with the locked columns if missing."""
    canon = to_canonical_symbol(symbol)
    base = store_root(root=root, data_dir=data_dir)
    path = series_path(asset_class, canon, timeframe, root=base)
    if not path.exists():
        return pd.DataFrame(columns=list(PARQUET_COLUMNS))
    df = pd.read_parquet(path)
    if df.empty:
        return pd.DataFrame(columns=list(PARQUET_COLUMNS))
    out = df.copy()
    missing = [c for c in ("open", "high", "low", "close", "close_time") if c not in out.columns]
    if missing:
        raise ValueError(f"{asset_class}/{canon}/{timeframe} missing columns {missing}")
    out["close_time"] = pd.to_datetime(out["close_time"], utc=True)
    if "open_time" in out.columns:
        out["open_time"] = pd.to_datetime(out["open_time"], utc=True)
    out = ensure_utc_index(out)
    if as_of is not None:
        out = truncate_at(out, as_of)
    return out


def load_bars_by_timeframe(
    asset_class: str,
    symbol: str,
    *,
    timeframes: Iterable[str] | None = None,
    as_of: datetime | None = None,
    root: Path | str | None = None,
    data_dir: Path | str | None = None,
) -> dict[str, pd.DataFrame]:
    """Load every requested timeframe for one canonical symbol.

    Does not resample a lower TF to invent a partial higher-TF bar — each
    timeframe is read from its own Parquet (already closed bars only).
    """
    tfs = list(timeframes) if timeframes is not None else sorted(TIMEFRAMES)
    base = store_root(root=root, data_dir=data_dir)
    return {
        tf: load_series(asset_class, symbol, tf, root=base, as_of=as_of)
        for tf in tfs
    }


def list_available_series(
    *,
    root: Path | str | None = None,
    data_dir: Path | str | None = None,
) -> list[tuple[str, str, str, Path]]:
    """Return (asset_class, symbol, timeframe, path) for every existing Parquet."""
    base = store_root(root=root, data_dir=data_dir)
    found: list[tuple[str, str, str, Path]] = []
    if not base.exists():
        return found
    for ac in ASSET_CLASSES:
        ac_dir = base / ac
        if not ac_dir.is_dir():
            continue
        for sym_dir in sorted(p for p in ac_dir.iterdir() if p.is_dir()):
            symbol = to_canonical_symbol(sym_dir.name)
            for tf in sorted(TIMEFRAMES):
                path = sym_dir / f"{tf}.parquet"
                if path.is_file():
                    found.append((ac, symbol, tf, path))
    return found
