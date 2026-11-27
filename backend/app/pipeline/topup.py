"""Light incremental top-up of the store from ccxt:binanceus (in-process scheduler).

Fetches from a few bars before each series' last stored open through now, one
series at a time. After the first catch-up that is only the newest candles.
api.binance.com is never called. Bars merge on open_time with the data layer's
rules: binance_vision wins duplicates, each bar keeps its source, seams are
flagged.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd
from signal_data.cleaning import clean_ohlcv
from signal_data.ingestion.crypto import _exchange, _paginate
from signal_data.storage import merge_on_open_time, read_series, write_series
from signal_data.timeutil import TF_DELTA

EXCHANGE = "binanceus"
OVERLAP_BARS = 3
log = logging.getLogger("app.pipeline.topup")
_ex = None


def _exchange_once():
    global _ex
    if _ex is None:
        _ex = _exchange(EXCHANGE)
    return _ex


def topup_store(symbols: list[str], timeframes: list[str], *, data_dir: str) -> dict:
    """Return {"series": n, "new_bars": n, "errors": n}. One failure never stops the rest."""
    added = errors = 0
    for symbol in symbols:
        for tf in timeframes:
            try:
                existing = read_series("crypto", symbol, tf, data_dir=data_dir)
                if existing.empty:
                    raise RuntimeError("no stored series")
                start = pd.Timestamp(existing["open_time"].iloc[-1]) - TF_DELTA[tf] * OVERLAP_BARS
                now = datetime.now(UTC)
                bars = _paginate(_exchange_once(), symbol.replace("-", "/"), tf,
                                 start.to_pydatetime(), now + TF_DELTA[tf])
                as_of = datetime.now(UTC)
                cleaned, _ = clean_ohlcv(bars, symbol=symbol, asset_class="crypto", timeframe=tf,
                                         source=f"ccxt:{EXCHANGE}", as_of=as_of)
                if cleaned.empty:
                    continue
                merged = merge_on_open_time(existing, cleaned)
                if len(merged) > len(existing):
                    write_series(merged, "crypto", symbol, tf, as_of=as_of, data_dir=data_dir)
                    added += len(merged) - len(existing)
            except Exception:  # logged; the other series and the next cycle continue
                errors += 1
                log.exception("top-up failed for %s %s", symbol, tf)
    return {"series": len(symbols) * len(timeframes), "new_bars": added, "errors": errors}
