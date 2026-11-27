"""Generic frame adapter for QA and any caller that wants a full-series view.

There is intentionally *no* per-strategy vectorized ``to_frame``. ``as_frame``
replays ``strategy.generate(bars_by_timeframe, as_of)`` at each bar close of
``df``, truncating to closed bars and building higher timeframes from fully
closed bars only — the same contract the Data backtester and the live pipeline
use. Bars with no signal are ``side='flat'`` with NaN entry/stop/confidence.

QA's truncation audit should wrap a Strategy with ``qa_strategy_fn``.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from signal_quant.bars import (
    bars_by_timeframe_from_base,
    ensure_utc_index,
    higher_timeframes,
    infer_timeframe,
)
from signal_quant.strategy import Strategy

AS_FRAME_COLUMNS = ["side", "entry", "stop_loss", "confidence"]


def _empty_row() -> dict:
    return {
        "side": "flat",
        "entry": np.nan,
        "stop_loss": np.nan,
        "confidence": np.nan,
    }


def _pick_signal(signals: list, as_of: pd.Timestamp) -> dict:
    if not signals:
        return _empty_row()
    # Prefer non-flat signals; if several, the highest calibrated confidence.
    scored = []
    for s in signals:
        side = s.side.value if hasattr(s.side, "value") else str(s.side)
        if side == "flat":
            continue
        scored.append((float(s.confidence), s))
    chosen = max(scored, key=lambda x: x[0])[1] if scored else signals[0]
    side = chosen.side.value if hasattr(chosen.side, "value") else str(chosen.side)
    if side == "flat":
        return _empty_row()
    return {
        "side": side,
        "entry": np.nan if chosen.entry is None else float(chosen.entry),
        "stop_loss": np.nan if chosen.stop_loss is None else float(chosen.stop_loss),
        "confidence": float(chosen.confidence),
    }


def as_frame(
    strategy: Strategy,
    df: pd.DataFrame,
    *,
    base_timeframe: str | None = None,
    higher: list[str] | None = None,
    warmup: int = 0,
) -> pd.DataFrame:
    """Replay ``generate`` bar by bar over ``df``.

    Parameters
    ----------
    strategy:
        Any object implementing ``generate(bars_by_timeframe, as_of)``.
    df:
        Single-timeframe OHLCV bars (the trigger / base timeframe).
    base_timeframe:
        If omitted, inferred from median bar spacing.
    higher:
        Higher timeframes to build from fully closed base bars. Defaults to
        every v1 timeframe strictly above the base.
    warmup:
        Skip ``generate`` for the first ``warmup`` bars (emit flat). Features
        inside ``generate`` still see only the truncated window.
    """
    reset = getattr(strategy, "reset", None)
    if callable(reset):
        reset()
    bars = ensure_utc_index(df)
    base_tf = base_timeframe or infer_timeframe(bars)
    htf = higher if higher is not None else higher_timeframes(base_tf)
    rows: list[dict] = []
    for i in range(len(bars)):
        if i < warmup:
            rows.append(_empty_row())
            continue
        as_of = bars.index[i].to_pydatetime()
        window = bars.iloc[: i + 1]
        ac = getattr(strategy, "asset_class", None)
        mapping = bars_by_timeframe_from_base(
            window, as_of, base_timeframe=base_tf, higher=htf, asset_class=ac
        )
        signals = strategy.generate(mapping, as_of)
        row = _pick_signal(list(signals or []), bars.index[i])
        rows.append(row)
    frame = pd.DataFrame(rows, index=bars.index, columns=AS_FRAME_COLUMNS)
    return _apply_cooldown(frame, strategy)


def _apply_cooldown(frame: pd.DataFrame, strategy: Strategy) -> pd.DataFrame:
    """Space non-flat emits in the replay only. ``generate`` stays a pure function."""
    cfg = getattr(strategy, "_filters", None)
    n = int(getattr(cfg, "cooldown_bars", 0) or 0) if cfg is not None else 0
    if n <= 0 or frame.empty:
        return frame
    out = frame.copy()
    last = None
    for i, (ts, row) in enumerate(out.iterrows()):
        if row["side"] == "flat":
            continue
        if last is not None and (i - last) < n:
            out.iloc[i] = {"side": "flat", "entry": np.nan, "stop_loss": np.nan, "confidence": np.nan}
            continue
        last = i
    return out


def qa_strategy_fn(strategy: Strategy, **as_frame_kwargs) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Adapter in the shape QA's ``truncation_test(strategy_fn, df, ...)`` expects."""

    def _fn(df: pd.DataFrame) -> pd.DataFrame:
        return as_frame(strategy, df, **as_frame_kwargs)

    return _fn
