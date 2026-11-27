"""H2 — Mean reversion via RSI extremes + Bollinger in a range regime. See docs/hypotheses.md."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from signal_quant.filters import FilterConfig, FilterState, accept
from signal_quant.levels import atr_levels
from signal_quant.strategy import Strategy, context_from_bars, make_signal
from signal_quant.symbols import to_canonical_symbol
from signal_quant.strategies.common import HORIZON_DEFAULT, last_bar_context, uncalibrated_prior


class MeanReversionRsiBB(Strategy):
    strategy_id = "mean_reversion_rsi_bb"
    strategy_version = "0.1.0"
    name = "Mean reversion RSI + Bollinger"
    hypothesis_id = "H2"
    description = 'Fades an RSI extreme that also tags or exits the matching Bollinger band, only when ADX indicates a range and realized vol is not elevated.'
    hypothesis = 'When the market is ranging and realized vol is not elevated, price tends to mean-revert after an RSI extreme that also tags the matching Bollinger band.'

    def __init__(
        self,
        symbol: str,
        asset_class: str,
        *,
        rsi_low: float = 30.0,
        rsi_high: float = 70.0,
        sl_atr: float = 1.5,
        tp_r: tuple[float, ...] = (1.0, 2.0),
        cooldown_bars: int = 4,
        is_mock: bool = False,
    ) -> None:
        self.symbol = to_canonical_symbol(symbol)
        self.asset_class = asset_class
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
        self.sl_atr = sl_atr
        self.tp_r = tp_r
        self.is_mock = is_mock
        self._filters = FilterConfig(
            allow_regimes=("range",),
            block_high_vol=True,
            cooldown_bars=cooldown_bars,
        )
        self._state = FilterState()

    def signals_at(self, bars_by_timeframe: Mapping[str, pd.DataFrame], as_of: datetime) -> list:
        tf, bars = context_from_bars(bars_by_timeframe, as_of)
        ctx = last_bar_context(bars)
        return self._signals_from_ctx(tf, as_of, ctx)

    def _signals_from_ctx(self, tf, as_of, ctx, htf_name=None, htf_ctx=None) -> list:
        if ctx is None or ctx.atr is None:
            return []
        rsi = ctx.features.get("rsi")
        pct_b = ctx.features.get("bb_pct_b")
        if pd.isna(rsi) or pd.isna(pct_b):
            return []
        side = None
        if rsi <= self.rsi_low and pct_b <= 0.0:
            side = "long"
        elif rsi >= self.rsi_high and pct_b >= 1.0:
            side = "short"
        if side is None:
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
                    "rsi": float(rsi),
                    "bb_pct_b": float(pct_b),
                    "regime": ctx.regime,
                    "high_vol": ctx.high_vol,
                    "atr": ctx.atr,
                },
                rationale=(
                    f"H2 mean-reversion: RSI {float(rsi):.1f} and Bollinger %b "
                    f"{float(pct_b):.2f} in a range regime on {tf}."
                ),
            )
        ]
