"""Candle access for GET /v1/candles.

Uses only ``signal_data.candles.get_candles``, always passing the store root
explicitly as ``data_dir=`` / ``store_dir=`` (same path: SIGNAL_DATA_DIR).
The official function takes no limit/end; this adapter slices after the call.

``asset_class`` comes from the canonical symbol or an explicit query param.
``source`` is copied per bar from the store column; a file may contain
multiple sources (plus a boolean `source_seam` changeover flag or other
extra columns, which are ignored and never exposed on the API). Never assume
one source per file. Never synthesizes bars. Does not import
``signal_data.ingestion`` (or any module with import-time side effects) and
does not mutate sys.path.
"""
from __future__ import annotations

from datetime import UTC, datetime

from signal_data.candles import get_candles
from signal_shared import TIMEFRAMES, Candle, normalize_symbol

from app.core.data_dir import location_kwargs, require_data_dir


class CandleNotFound(Exception):
    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        super().__init__(f"no candle data for symbol={symbol} timeframe={timeframe}")


class BadCandleRequest(ValueError):
    pass


def _to_candles(rows) -> list[Candle]:
    if rows is None:
        return []
    if hasattr(rows, "to_dicts"):
        rows = rows.to_dicts()
    elif hasattr(rows, "to_dict"):
        rows = rows.to_dict(orient="records")
    out: list[Candle] = []
    for row in rows:
        if isinstance(row, Candle):
            out.append(row)
        else:
            payload = dict(row)
            if "time" not in payload and "open_time" in payload:
                payload["time"] = payload["open_time"]
            allowed = {"time", "open", "high", "low", "close", "volume", "source"}
            payload = {k: v for k, v in payload.items() if k in allowed}
            out.append(Candle.model_validate(payload))
    return out


def _slice(candles: list[Candle], limit: int, end: datetime | None) -> list[Candle]:
    candles = sorted(candles, key=lambda c: c.time)
    if end is not None:
        end_utc = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
        candles = [c for c in candles if c.time <= end_utc]
    return candles[-limit:] if len(candles) > limit else candles


def load_candles(
    *, symbol: str, timeframe: str, limit: int, end: datetime | None,
    data_dir: str, asset_class: str | None = None,
) -> list[Candle]:
    try:
        symbol = normalize_symbol(symbol, asset_class)
    except ValueError as e:
        raise BadCandleRequest(str(e)) from e
    if timeframe not in TIMEFRAMES:
        raise BadCandleRequest(f"timeframe must be one of {sorted(TIMEFRAMES)}")

    data_dir = require_data_dir(data_dir)
    loc = location_kwargs(get_candles, data_dir)
    try:
        rows = get_candles(symbol, timeframe, **loc)
    except FileNotFoundError as e:
        raise CandleNotFound(symbol, timeframe) from e
    candles = _slice(_to_candles(rows), limit, end)
    if not candles:
        raise CandleNotFound(symbol, timeframe)
    return candles
