"""Strategy protocol the backtester drives bar-by-bar, plus a placeholder SMA baseline.

The SMA 20/50 crossover is a pipeline-validation placeholder, not a trading
recommendation. It is clearly labeled in strategy_id, rationale, and reports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import uuid4

import numpy as np
import pandas as pd
from signal_shared import AssetClass, Side, Signal, SignalStatus

from signal_data.stale import drop_stale
from signal_data.symbols import asset_class_of, to_canonical
from signal_data.timeutil import to_utc, to_utc_datetime


@runtime_checkable
class BarStrategy(Protocol):
    """Bar-by-bar signal generator.

    ``bars_by_timeframe`` is already sliced: every frame contains only bars
    with close_time <= as_of. Higher timeframes contain only fully closed bars.
    """

    def generate(
        self,
        bars_by_timeframe: dict[str, pd.DataFrame],
        as_of: datetime,
    ) -> list[Signal]:
        ...


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


class SmaCrossoverPlaceholder:
    """PLACEHOLDER strategy for pipeline validation — not a recommendation.

    Long on SMA(fast) crossing above SMA(slow), short on a cross below.
    ``entry`` is the reference close of the signal bar. stop_loss and the
    first take_profit are absolute prices at ``stop_atr`` / ``tp_atr`` multiples
    of ATR(atr_period).
    """

    strategy_id = "sma_crossover_placeholder"
    strategy_version = "v1-placeholder"
    pipeline_check_only = True

    def __init__(
        self,
        *,
        symbol: str,
        timeframe: str = "1d",
        fast: int = 20,
        slow: int = 50,
        atr_period: int = 14,
        stop_atr: float = 2.0,
        tp_atr: float = 3.0,
        horizon_bars: int = 20,
        confidence: float = 0.5,
    ) -> None:
        if fast >= slow:
            raise ValueError("fast SMA period must be < slow SMA period")
        self.symbol = to_canonical(symbol)
        self.asset_class = AssetClass(asset_class_of(self.symbol))
        self.timeframe = timeframe
        self.fast = int(fast)
        self.slow = int(slow)
        self.atr_period = int(atr_period)
        self.stop_atr = float(stop_atr)
        self.tp_atr = float(tp_atr)
        self.horizon_bars = int(horizon_bars)
        self.confidence = float(confidence)

    def generate(self, bars_by_timeframe: dict[str, pd.DataFrame], as_of: datetime) -> list[Signal]:
        df = bars_by_timeframe.get(self.timeframe)
        if df is None or len(df) < self.slow + 2:
            return []
        bars = drop_stale(df.copy())
        if "close_time" in bars.columns:
            ct = pd.to_datetime(bars["close_time"], utc=True)
            cut = to_utc(as_of)
            bars = bars.loc[ct <= cut]
        if len(bars) < self.slow + 2:
            return []
        # Only emit when the latest bar just closed at as_of (or is the last
        # available closed bar at as_of).
        last = bars.iloc[-1]
        last_close_time = to_utc(last["close_time"])
        if last_close_time > to_utc(as_of):
            return []

        close = bars["close"].astype(float)
        high = bars["high"].astype(float)
        low = bars["low"].astype(float)
        sma_f = close.rolling(self.fast, min_periods=self.fast).mean()
        sma_s = close.rolling(self.slow, min_periods=self.slow).mean()
        atr = _atr(high, low, close, self.atr_period)

        i = len(bars) - 1
        if i < 1:
            return []
        f0, f1 = float(sma_f.iloc[i - 1]), float(sma_f.iloc[i])
        s0, s1 = float(sma_s.iloc[i - 1]), float(sma_s.iloc[i])
        if not np.isfinite([f0, f1, s0, s1, float(atr.iloc[i]), float(close.iloc[i])]).all():
            return []
        cross_up = f0 <= s0 and f1 > s1
        cross_down = f0 >= s0 and f1 < s1
        if not cross_up and not cross_down:
            return []

        side = Side.long if cross_up else Side.short
        entry = float(close.iloc[i])  # reference close
        atr_val = float(atr.iloc[i])
        if atr_val <= 0:
            return []
        if side == Side.long:
            stop = entry - self.stop_atr * atr_val
            tp = entry + self.tp_atr * atr_val
            if not (stop < entry < tp):
                return []
        else:
            stop = entry + self.stop_atr * atr_val
            tp = entry - self.tp_atr * atr_val
            if not (stop > entry > tp):
                return []

        bar_close = to_utc_datetime(last_close_time)
        rationale = (
            "PLACEHOLDER SMA {fast}/{slow} crossover for pipeline validation, "
            "not a recommendation. {side} when SMA{fast} crossed SMA{slow}; "
            "stop/target are {stop_atr} / {tp_atr} ATR({atr_period}) absolute prices."
        ).format(
            fast=self.fast, slow=self.slow, side=side.value,
            stop_atr=self.stop_atr, tp_atr=self.tp_atr, atr_period=self.atr_period,
        )
        return [
            Signal(
                id=f"sma-{self.symbol}-{bar_close.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                symbol=self.symbol,
                asset_class=self.asset_class,
                timeframe=self.timeframe,
                side=side,
                generated_at=bar_close,
                bar_close_time=bar_close,
                entry=entry,
                stop_loss=float(stop),
                take_profit=[float(tp)],
                horizon_bars=self.horizon_bars,
                confidence=self.confidence,
                features_snapshot={
                    "sma_fast": f1,
                    "sma_slow": s1,
                    "atr": atr_val,
                    "placeholder": True,
                },
                rationale=rationale[:500],
                status=SignalStatus.active,
                is_mock=False,
            )
        ]


def as_frame(
    strategy: BarStrategy,
    bars: pd.DataFrame,
    *,
    timeframe: str,
    higher: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Replay ``strategy.generate`` bar by bar for QA truncation tests.

    Each call receives a prefix of ``bars`` with close_time <= that bar's close
    (and any higher-timeframe frames similarly truncated). The result is indexed
    like ``bars`` with side / entry / stop_loss / take_profit / confidence.
    """
    work = bars.copy().reset_index(drop=True)
    if "close_time" not in work.columns:
        raise ValueError("bars need a close_time column")
    work["close_time"] = pd.to_datetime(work["close_time"], utc=True)
    rows = []
    for i in range(len(work)):
        as_of = work.iloc[i]["close_time"]
        sliced = {timeframe: work.iloc[: i + 1].copy()}
        if higher:
            for tf, hdf in higher.items():
                h = hdf.copy()
                h["close_time"] = pd.to_datetime(h["close_time"], utc=True)
                sliced[tf] = h.loc[h["close_time"] <= as_of].copy()
        sigs = strategy.generate(sliced, as_of.to_pydatetime())
        if not sigs:
            rows.append({"side": "flat", "entry": np.nan, "stop_loss": np.nan, "take_profit": None, "confidence": np.nan})
        else:
            s = sigs[-1]
            rows.append(
                {
                    "side": s.side.value,
                    "entry": s.entry,
                    "stop_loss": s.stop_loss,
                    "take_profit": list(s.take_profit),
                    "confidence": s.confidence,
                }
            )
    return pd.DataFrame(rows, index=bars.index if not isinstance(bars.index, pd.RangeIndex) or len(bars.index) == len(work) else None)
