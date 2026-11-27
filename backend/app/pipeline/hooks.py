"""Thin adapters around Quant/Data APIs. Missing imports fail loudly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

# Import costs first so signal_data.backtester's package init finishes
# before barriers, avoiding a circular import in Data (barriers -> costs
# -> backtester.__init__ -> engine -> barriers.resolve).
import signal_data.backtester.costs as _signal_data_costs  # noqa: F401
from signal_data.barriers import resolve as resolve_outcome
from signal_data.candles import get_candles
from signal_data.live import update as live_update
from signal_data.masks import gap_segments, is_stale
from signal_quant.registry import run_for_bar as quant_run_for_bar
from signal_shared import Signal, infer_asset_class, normalize_symbol

from app.core.data_dir import location_kwargs


@dataclass(frozen=True)
class ClosedBar:
    symbol: str
    timeframe: str
    asset_class: str
    open_time: datetime
    close_time: datetime


def load_ohlcv(symbol: str, timeframe: str, *, data_dir: str):
    """Load closed bars. Official get_candles/load_closed drop stale rows by default."""
    try:
        return get_candles(symbol, timeframe, **location_kwargs(get_candles, data_dir))
    except FileNotFoundError:
        return None


def apply_stale_and_gaps(df, timeframe: str):
    """Drop stale bars and apply the gap-reset rule from signal_data.masks."""
    if df is None or getattr(df, "empty", False):
        return df
    mask = is_stale(df)
    out = df.loc[~mask].copy() if mask is not None and getattr(mask, "any", lambda: False)() else df
    gap_segments(out, timeframe)
    return out


def slice_closed(df, as_of: datetime):
    """Keep only bars with close_time <= as_of (no lookahead)."""
    if df is None or getattr(df, "empty", False):
        return df
    import pandas as pd

    cut = pd.Timestamp(as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC))
    if cut.tzinfo is None:
        cut = cut.tz_localize("UTC")
    else:
        cut = cut.tz_convert("UTC")
    ts = pd.to_datetime(df["close_time"], utc=True)
    return df.loc[ts <= cut].copy()


def bars_by_timeframe(
    symbol: str, timeframes: list[str], *, data_dir: str, as_of: datetime,
) -> dict:
    out = {}
    for tf in timeframes:
        df = load_ohlcv(symbol, tf, data_dir=data_dir)
        if df is None:
            continue
        df = apply_stale_and_gaps(df, tf)
        df = slice_closed(df, as_of)
        if df is not None and not getattr(df, "empty", True):
            out[tf] = df
    return out


def _loader_for(data_dir: str):
    """Loader callable matching ``signal_quant.registry.run_for_bar``."""

    def loader(symbol, timeframes, as_of, lookback_bars, asset_class=None):
        out = {}
        for tf in timeframes:
            df = load_ohlcv(symbol, tf, data_dir=data_dir)
            if df is None:
                continue
            df = apply_stale_and_gaps(df, tf)
            df = slice_closed(df, as_of)
            if lookback_bars and df is not None and not getattr(df, "empty", True):
                df = df.tail(int(lookback_bars))
            if df is not None and not getattr(df, "empty", True):
                out[tf] = df
        return out

    return loader


def run_for_bar(
    symbol: str,
    timeframe: str,
    as_of: datetime,
    *,
    data_dir: str,
    timeframes: list[str] | None = None,
) -> list[Signal]:
    """Run registered strategies at a closed bar via ``signal_quant.registry.run_for_bar``.

    ``timeframes`` is accepted from the pipeline; Quant selects the required
    set through ``required_timeframes``.
    """
    del timeframes
    symbol = normalize_symbol(symbol)
    return list(quant_run_for_bar(
        symbol, infer_asset_class(symbol), timeframe, as_of,
        loader=_loader_for(data_dir),
        data_dir=data_dir,
    ))


def resolve_barriers(signal: Signal, bars):
    """Score an open signal against later bars via ``signal_data.barriers.resolve``.

    ``resolve`` returns an ``Outcome``. This adapter yields
    ``(updated_signal, audit)`` so the tracker can read ``status`` / ``exit_*``.
    """
    result = resolve_outcome(signal, bars)
    if isinstance(result, tuple) and len(result) == 2:
        return result
    updated = signal.model_copy(update={"status": result.status})
    return updated, result


def poll_live_update(symbols: list[str], timeframes: list[str], *, data_dir: str):
    """Call Data's live update hook with an explicit store location."""
    return live_update(symbols, timeframes, **location_kwargs(live_update, data_dir))
