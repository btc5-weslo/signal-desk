"""Live closed-bar hook.

    from signal_data.live import update, BarClosed

    bars = update(symbols, timeframes)

Returns the most recently fully closed bar for each (symbol, timeframe).
Publishes to Redis channel ``bars:closed`` only when ``REDIS_URL`` is set.
Importing this module never connects to Redis or the network.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from signal_data.store import get_candles
from signal_data.symbols import asset_class_of, to_canonical
from signal_data.timeutil import now_utc, to_utc, to_utc_datetime

REDIS_CHANNEL = "bars:closed"


@dataclass(frozen=True)
class BarClosed:
    symbol: str
    timeframe: str
    asset_class: str
    open_time: datetime
    close_time: datetime
    close: float | None = None
    source: str | None = None


def _latest_closed(
    symbols: list[str],
    timeframes: list[str],
    *,
    data_dir: Path | str | None = None,
    store_dir: Path | str | None = None,
    as_of: datetime | pd.Timestamp | None = None,
) -> list[BarClosed]:
    cut = to_utc(as_of) if as_of is not None else now_utc()
    out: list[BarClosed] = []
    for raw_symbol in symbols:
        symbol = to_canonical(raw_symbol)
        ac = asset_class_of(symbol)
        for tf in timeframes:
            try:
                df = get_candles(symbol, tf, data_dir=data_dir, store_dir=store_dir, drop_stale=True)
            except FileNotFoundError:
                continue
            if df is None or df.empty:
                continue
            work = df.copy()
            work["close_time"] = pd.to_datetime(work["close_time"], utc=True)
            closed = work.loc[work["close_time"] <= cut]
            if closed.empty:
                continue
            row = closed.iloc[-1]
            out.append(
                BarClosed(
                    symbol=symbol,
                    timeframe=tf,
                    asset_class=ac,
                    open_time=to_utc_datetime(row["open_time"]),
                    close_time=to_utc_datetime(row["close_time"]),
                    close=float(row["close"]) if pd.notna(row["close"]) else None,
                    source=str(row["source"]) if "source" in closed.columns else None,
                )
            )
    return out


def _publish_redis(url: str, bars: list[BarClosed]) -> None:
    # Imported only when REDIS_URL is set, and never at module import time.
    # If the optional redis package is missing, do not swallow the error —
    # a set REDIS_URL means the caller asked to publish.
    try:
        import redis  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "REDIS_URL is set but the redis package is not installed. "
            "Install redis or unset REDIS_URL."
        ) from exc

    client = redis.Redis.from_url(url)
    try:
        for bar in bars:
            payload = asdict(bar)
            for key in ("open_time", "close_time"):
                val = payload[key]
                if hasattr(val, "isoformat"):
                    payload[key] = val.isoformat()
            client.publish(REDIS_CHANNEL, json.dumps(payload))
    finally:
        try:
            client.close()
        except Exception:
            pass


def update(
    symbols: list[str],
    timeframes: list[str],
    *,
    data_dir: Path | str | None = None,
    store_dir: Path | str | None = None,
    as_of: datetime | pd.Timestamp | None = None,
    redis_url: str | None = None,
) -> list[BarClosed]:
    """Return newly observed closed bars.

    Redis publishing happens only when ``REDIS_URL`` (or the ``redis_url``
    argument) is set. Unset, this never imports or contacts Redis.
    """
    closed = _latest_closed(symbols, timeframes, data_dir=data_dir, store_dir=store_dir, as_of=as_of)
    url = redis_url if redis_url is not None else os.environ.get("REDIS_URL")
    if url:
        _publish_redis(url, closed)
    return closed
