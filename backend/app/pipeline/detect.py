"""Detect newly closed bars via cursors (cron poll). Idempotent."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from .hooks import ClosedBar, load_ohlcv, poll_live_update


def _as_utc(value) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def detect_new_closed_bars(
    symbols: list[str],
    timeframes: list[str],
    *,
    data_dir: str,
    cursors: dict[tuple[str, str], datetime],
) -> list[ClosedBar]:
    """Return bars with close_time after the persisted cursor.

    If Data's live.update hook is present it is preferred; otherwise we poll
    get_candles. A missing cursor is initialized to the latest close_time
    without replaying history (avoids flooding on first start).
    """
    live = poll_live_update(symbols, timeframes, data_dir=data_dir)
    if live is not None:
        # live.update returns the latest closed bar per series; still honor
        # cursors so a missing cursor initializes without replaying history.
        events = [_event_to_bar(ev) for ev in live]
        return _filter_new_bars(events, cursors)

    found: list[ClosedBar] = []
    for symbol in symbols:
        for timeframe in timeframes:
            df = load_ohlcv(symbol, timeframe, data_dir=data_dir)
            if df is None or getattr(df, "empty", True):
                continue
            work = df.sort_values("close_time")
            last_close = _as_utc(work.iloc[-1]["close_time"])
            cursor = cursors.get((symbol, timeframe))
            if cursor is None:
                cursors[(symbol, timeframe)] = last_close
                continue
            cursor_utc = _as_utc(cursor)
            newer = work[pd.to_datetime(work["close_time"], utc=True) > pd.Timestamp(cursor_utc)]
            for row in newer.itertuples(index=False):
                found.append(ClosedBar(
                    symbol=symbol,
                    timeframe=timeframe,
                    asset_class=str(getattr(row, "asset_class", "") or _asset(symbol)),
                    open_time=_as_utc(row.open_time),
                    close_time=_as_utc(row.close_time),
                ))
            if found or last_close > cursor_utc:
                cursors[(symbol, timeframe)] = last_close
    found.sort(key=lambda b: (b.close_time, b.symbol, b.timeframe))
    return found


def _asset(symbol: str) -> str:
    from signal_shared import infer_asset_class

    return infer_asset_class(symbol)


def _event_to_bar(ev) -> ClosedBar:
    if isinstance(ev, ClosedBar):
        return ev
    if isinstance(ev, dict):
        symbol = ev["symbol"]
        return ClosedBar(
            symbol=symbol,
            timeframe=ev["timeframe"],
            asset_class=ev.get("asset_class") or _asset(symbol),
            open_time=_as_utc(ev["open_time"]),
            close_time=_as_utc(ev["close_time"]),
        )
    symbol = ev.symbol
    return ClosedBar(
        symbol=symbol,
        timeframe=ev.timeframe,
        asset_class=getattr(ev, "asset_class", None) or _asset(symbol),
        open_time=_as_utc(ev.open_time),
        close_time=_as_utc(ev.close_time),
    )


def _filter_new_bars(events: list[ClosedBar], cursors: dict[tuple[str, str], datetime]) -> list[ClosedBar]:
    """Emit only bars after the cursor; initialize a missing cursor and skip."""
    found: list[ClosedBar] = []
    latest: dict[tuple[str, str], datetime] = {}
    for ev in events:
        key = (ev.symbol, ev.timeframe)
        close = _as_utc(ev.close_time)
        prev = latest.get(key)
        if prev is None or close > prev:
            latest[key] = close
        cursor = cursors.get(key)
        if cursor is None:
            cursors[key] = close
            continue
        if close > _as_utc(cursor):
            found.append(ev)
            cursors[key] = close
    for key, close in latest.items():
        cursor = cursors.get(key)
        if cursor is None or close > _as_utc(cursor):
            cursors[key] = close
    found.sort(key=lambda b: (b.close_time, b.symbol, b.timeframe))
    return found
