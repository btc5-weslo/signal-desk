"""Primary import of ``signal_data.live.update``.

The store root is ``data_dir`` / ``SIGNAL_DATA_DIR`` (the folder that
contains crypto/, equity/, and fx/). It is passed through as ``store_dir=``,
the keyword ``signal_data.live.update`` takes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from signal_quant.bars import _ensure_signal_data_path
from signal_quant.data_loader import resolve_data_dir


def update(
    symbols: list[str],
    timeframes: list[str],
    *,
    data_dir: Path | str | None = None,
    as_of: datetime | pd.Timestamp | None = None,
    redis_url: str | None = None,
):
    """Delegate to ``signal_data.live.update`` with an explicit store root."""
    _ensure_signal_data_path()
    from signal_data.live import update as _update  # type: ignore

    store = resolve_data_dir(data_dir, required=True)
    return _update(symbols, timeframes, store_dir=store, as_of=as_of, redis_url=redis_url)
