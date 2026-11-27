"""Resolve SIGNAL_DATA_DIR for every signal_data / signal_quant call.

``SIGNAL_DATA_DIR`` is the store root itself: the folder that directly
contains ``crypto/``, ``equity/``, and ``fx/``. Files live at

    $SIGNAL_DATA_DIR/{asset_class}/{symbol}/{timeframe}.parquet

There is no ``SIGNAL_DATA_STORE_DIR``. Callers must pass this directory
explicitly as ``data_dir=`` and/or ``store_dir=`` (same path). The backend
never appends ``/store`` and never relies on an implicit default inside
those packages.
"""

from __future__ import annotations

import inspect
from pathlib import Path


def default_dev_data_dir() -> str:
    """Absolute path to the repo ``data/store``. Allowed only as a dev fallback."""
    return str((Path(__file__).resolve().parents[3] / "data" / "store").resolve())


def require_data_dir(data_dir: str | None) -> str:
    value = (data_dir or "").strip()
    if not value:
        raise RuntimeError("set SIGNAL_DATA_DIR; no hard-coded data path is used")
    return value


def store_dir(data_dir: str | None) -> Path:
    """Return SIGNAL_DATA_DIR as a Path (it already is the store root)."""
    return Path(require_data_dir(data_dir))


def location_kwargs(fn, data_dir: str | None) -> dict:
    """Explicit location kwargs for a signal_data or signal_quant callable.

    Pass the same store-root path as ``data_dir`` and/or ``store_dir``,
    whichever the current signature accepts. Never rely on an implicit
    default inside signal_data.
    """
    root = require_data_dir(data_dir)
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    kwargs: dict = {}
    if "data_dir" in params:
        kwargs["data_dir"] = root
    if "store_dir" in params:
        kwargs["store_dir"] = root
    if kwargs:
        return kwargs
    return {"data_dir": root}
