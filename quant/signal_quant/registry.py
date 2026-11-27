"""Backend entry points for discovering strategies and running one bar.

Usage (Backend Engineer)::

    from signal_quant.registry import list_strategies, get_strategy, run_for_bar, generate_range

    # Discover
    for cls in list_strategies():
        print(cls.strategy_id, cls.version, cls.supported)
        print(cls.required_timeframes("1h"))

    Trend = get_strategy("trend_ema_adx")            # latest version
    Trend = get_strategy("trend_ema_adx", version="0.1.0")

    # Evaluate every strategy that supports (crypto, 1h) at one closed bar.
    # Prefers signal_data.bars.load_closed(symbol, timeframes, as_of, lookback_bars)
    # when that helper exists; otherwise a quant-side Parquet loader (or an
    # injected loader callable with the same signature plus asset_class).
    signals = run_for_bar(
        symbol="BTC-USDT",
        asset_class="crypto",
        timeframe="1h",
        as_of=as_of,          # timezone-aware UTC close of the trigger bar
        loader=None,
        data_dir=data_dir,    # or set SIGNAL_DATA_DIR; no implicit default
    )

``run_for_bar`` never emits for an unsupported (asset_class, timeframe) pair.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

import pandas as pd

from signal_quant.models import Signal
from signal_quant.strategy import LOOKBACK_BARS, Strategy

Loader = Callable[..., Mapping[str, pd.DataFrame]]


def list_strategies() -> list[type[Strategy]]:
    """Return the registered baseline strategy classes, sorted by id."""
    from signal_quant.strategies import BASELINE

    return [BASELINE[k] for k in sorted(BASELINE)]


def get_strategy(strategy_id: str, version: str | None = None) -> type[Strategy]:
    """Look up one strategy class. ``version=None`` means the registered version."""
    from signal_quant.strategies import BASELINE

    cls = BASELINE.get(strategy_id)
    if cls is None:
        raise KeyError(f"unknown strategy_id {strategy_id!r}")
    ver = getattr(cls, "version", None) or cls.strategy_version
    if version is not None and version != ver:
        raise KeyError(f"strategy {strategy_id!r} has version {ver!r}, not {version!r}")
    return cls


def _try_load_closed(symbol, timeframes, as_of, lookback_bars, data_dir=None):
    """Primary path: ``signal_data.bars.load_closed``. Always pass store_dir."""
    from signal_quant.bars import _ensure_signal_data_path

    _ensure_signal_data_path()
    from signal_data.bars import load_closed

    return load_closed(
        symbol, timeframes, as_of, lookback_bars, store_dir=data_dir
    )


def _fallback_load(symbol, asset_class, timeframes, as_of, lookback_bars, data_dir=None) -> dict[str, pd.DataFrame]:
    from signal_quant.data_loader import load_bars_by_timeframe

    bars = load_bars_by_timeframe(
        asset_class, symbol, timeframes=timeframes, as_of=as_of, data_dir=data_dir
    )
    return {
        tf: (df.tail(int(lookback_bars)) if df is not None and len(df) else df)
        for tf, df in bars.items()
    }


def _load_bars(
    symbol: str,
    asset_class: str,
    timeframes: list[str],
    as_of: datetime,
    lookback_bars: int,
    loader: Loader | None,
    data_dir=None,
) -> Mapping[str, pd.DataFrame]:
    if loader is not None:
        try:
            return loader(symbol, timeframes, as_of, lookback_bars, data_dir=data_dir)
        except TypeError:
            try:
                return loader(symbol, timeframes, as_of, lookback_bars)
            except TypeError:
                return loader(
                    symbol, timeframes, as_of, lookback_bars, asset_class=asset_class
                )
    closed = _try_load_closed(symbol, timeframes, as_of, lookback_bars, data_dir=data_dir)
    if closed is not None:
        return closed
    return _fallback_load(symbol, asset_class, timeframes, as_of, lookback_bars, data_dir=data_dir)


def run_for_bar(
    symbol: str,
    asset_class: str,
    timeframe: str,
    as_of: datetime,
    loader: Loader | None = None,
    *,
    data_dir: str | Path | None = None,
) -> list[Signal]:
    """Run every registered strategy that supports this (asset_class, timeframe).

    Signature::

        run_for_bar(symbol, asset_class, timeframe, as_of, loader=None, *, data_dir=None)

    ``data_dir`` is passed to ``signal_data.bars.load_closed(..., store_dir=)``
    and to the fallback loader. If both ``data_dir`` and ``loader`` are None,
    ``SIGNAL_DATA_DIR`` is used. If that is also unset, a ``DataDirError`` is
    raised — there is no implicit default store path.
    """
    from signal_quant.data_loader import resolve_data_dir

    resolved = resolve_data_dir(data_dir, required=(loader is None))
    out: list[Signal] = []
    ac = str(asset_class)
    pair = (ac, timeframe)
    for cls in list_strategies():
        supported = getattr(cls, "supported", None)
        if supported is not None and pair not in supported:
            continue
        if hasattr(cls, "required_timeframes"):
            req = cls.required_timeframes(timeframe)
        else:
            req = {timeframe: LOOKBACK_BARS}
        lookback = max(req.values()) if req else LOOKBACK_BARS
        tfs = list(req.keys())
        bars = _load_bars(symbol, ac, tfs, as_of, lookback, loader, data_dir=resolved)
        strat = cls(symbol=symbol, asset_class=ac)
        out.extend(strat.generate(bars, as_of))
    return out


def generate_range(
    strategy_id: str,
    symbol: str,
    asset_class: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    data_dir: str | Path | None = None,
    loader: Loader | None = None,
    version: str | None = None,
) -> list[Signal]:
    """Vectorized range: signals ``generate()`` would emit at each closed bar in ``[start, end]``.

    Signature::

        generate_range(strategy_id, symbol, asset_class, timeframe, start, end, *, data_dir=None, loader=None, version=None) -> list[Signal]

    Loads required timeframes (including a fully closed HTF when the strategy
    needs one) truncated at ``end``, with history before ``start`` for warmup.
    Indicators are computed once via ``Strategy.signals_series``. If
    ``(asset_class, timeframe)`` is unsupported, returns ``[]``.

    ``data_dir`` is the store root (or set ``SIGNAL_DATA_DIR``). There is no
    implicit default path. A ``loader`` callable, if given, is used instead of
    the parquet store; it should return frames covering warmup plus
    ``[start, end]``.
    """
    from signal_quant.bars import TF_MINUTES, to_utc
    from signal_quant.data_loader import load_bars_by_timeframe, resolve_data_dir

    cls = get_strategy(strategy_id, version)
    ac = str(asset_class)
    pair = (ac, timeframe)
    supported = getattr(cls, "supported", None)
    if supported is not None and pair not in supported:
        return []
    if hasattr(cls, "required_timeframes"):
        req = cls.required_timeframes(timeframe)
    else:
        req = {timeframe: LOOKBACK_BARS}
    tfs = list(req.keys())
    resolved = resolve_data_dir(data_dir, required=(loader is None))
    start_u = to_utc(start)
    end_u = to_utc(end)
    if loader is not None:
        minutes = TF_MINUTES.get(timeframe, 60)
        span = max(0.0, (end_u - start_u).total_seconds() / 60.0)
        lookback = max(req.values()) if req else LOOKBACK_BARS
        lookback = int(lookback) + int(span / minutes) + 5
        try:
            bars = loader(symbol, tfs, end_u, lookback, data_dir=resolved)
        except TypeError:
            try:
                bars = loader(symbol, tfs, end_u, lookback)
            except TypeError:
                bars = loader(
                    symbol, tfs, end_u, lookback, asset_class=ac
                )
    else:
        bars = load_bars_by_timeframe(
            ac, symbol, timeframes=tfs, as_of=end_u, data_dir=resolved
        )
    strat = cls(symbol=symbol, asset_class=ac)
    return strat.signals_series(bars, start_u, end_u, timeframe=timeframe)
