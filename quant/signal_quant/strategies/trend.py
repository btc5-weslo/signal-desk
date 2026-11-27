"""H1 — Trend following via EMA relationship + ADX gate. See docs/hypotheses.md."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from signal_quant.filters import FilterConfig, FilterState, accept
from signal_quant.levels import atr_levels
from signal_quant.strategy import Strategy, context_from_bars, make_signal
from signal_quant.symbols import to_canonical_symbol
from signal_quant.strategies.common import HORIZON_DEFAULT, last_bar_context, uncalibrated_prior


class TrendEmaAdx(Strategy):
    strategy_id = "trend_ema_adx"
    strategy_version = "0.1.0"
    name = "Trend EMA + ADX"
    hypothesis_id = "H1"
    description = 'Uses an ADX gate and plus/minus DI confirmation on a shorter-versus-longer EMA relationship to set trade direction, with ATR-multiple stops and R-multiple targets.'
    hypothesis = 'Trends tend to persist after a shorter-versus-longer EMA relationship is confirmed by ADX and plus/minus DI.'

    def __init__(
        self,
        symbol: str,
        asset_class: str,
        *,
        ema_fast: int = 12,
        ema_slow: int = 48,
        adx_min: float = 20.0,
        sl_atr: float = 2.0,
        tp_r: tuple[float, ...] = (1.5, 3.0),
        cooldown_bars: int = 4,
        is_mock: bool = False,
    ) -> None:
        if ema_fast >= ema_slow:
            raise ValueError("ema_fast must be < ema_slow")
        self.symbol = to_canonical_symbol(symbol)
        self.asset_class = asset_class
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.adx_min = adx_min
        self.sl_atr = sl_atr
        self.tp_r = tp_r
        self.is_mock = is_mock
        self._filters = FilterConfig(
            allow_regimes=("trend",),
            block_high_vol=False,
            cooldown_bars=cooldown_bars,
        )
        self._state = FilterState()

    def feature_kwargs(self) -> dict:
        return {"ema_fast": self.ema_fast, "ema_slow": self.ema_slow}

    def signals_at(self, bars_by_timeframe: Mapping[str, pd.DataFrame], as_of: datetime) -> list:
        tf, bars = context_from_bars(bars_by_timeframe, as_of)
        ctx = last_bar_context(bars, self.feature_kwargs())
        return self._signals_from_ctx(tf, as_of, ctx)

    def _signals_from_ctx(self, tf, as_of, ctx, htf_name=None, htf_ctx=None) -> list:
        if ctx is None or ctx.atr is None or ctx.adx is None:
            return []
        if ctx.adx < self.adx_min:
            return []
        fast, slow = ctx.features["ema_fast"], ctx.features["ema_slow"]
        if pd.isna(fast) or pd.isna(slow):
            return []
        if fast > slow:
            side = "long"
        elif fast < slow:
            side = "short"
        else:
            return []
        # Require the crossover / relationship to be confirmed by DI direction.
        plus_di, minus_di = ctx.features.get("plus_di"), ctx.features.get("minus_di")
        if side == "long" and not (pd.notna(plus_di) and plus_di > minus_di):
            return []
        if side == "short" and not (pd.notna(minus_di) and minus_di > plus_di):
            return []
        conf, flag = uncalibrated_prior()
        if not accept(
            regime=ctx.regime,
            high_vol=ctx.high_vol,
            confidence=conf,
            bar_index=ctx.index,
            state=FilterState(),  # fresh: generate is stateless
            cfg=self._filters,
        ):
            return []
        stop, tps = atr_levels(side, ctx.close, ctx.atr, sl_atr=self.sl_atr, tp_r=self.tp_r)
        return [
            make_signal(
                strategy=self,
                symbol=self.symbol,
                asset_class=self.asset_class,
                timeframe=tf,
                side=side,
                as_of=as_of,
                entry=ctx.close,
                stop_loss=stop,
                take_profit=tps,
                horizon_bars=HORIZON_DEFAULT[tf],
                confidence=conf,
                features_snapshot={
                    **flag,
                    "ema_fast": float(fast),
                    "ema_slow": float(slow),
                    "adx": float(ctx.adx),
                    "regime": ctx.regime,
                    "high_vol": ctx.high_vol,
                    "atr": ctx.atr,
                },
                rationale=(
                    f"H1 trend: ema{self.ema_fast} "
                    f"{'>' if side == 'long' else '<'} ema{self.ema_slow} "
                    f"and ADX {ctx.adx:.1f} >= {self.adx_min} on {tf}."
                ),
            )
        ]
