"""H3 — Donchian breakout with volume confirmation. See docs/hypotheses.md."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from signal_quant.filters import FilterConfig, FilterState, accept
from signal_quant.levels import atr_levels
from signal_quant.strategy import Strategy, context_from_bars, make_signal
from signal_quant.symbols import to_canonical_symbol
from signal_quant.strategies.common import HORIZON_DEFAULT, last_bar_context, uncalibrated_prior


class BreakoutDonchian(Strategy):
    strategy_id = "breakout_donchian"
    strategy_version = "0.1.0"
    name = "Donchian breakout"
    hypothesis_id = "H3"
    description = 'Trades a close beyond the prior N-bar Donchian high or low when volume ratio is above a threshold, with an ATR stop and R-multiple targets.'
    hypothesis = 'A close beyond the prior Donchian channel, accompanied by volume above a threshold, tends to mark the start of a short expansion move.'

    def __init__(
        self,
        symbol: str,
        asset_class: str,
        *,
        donchian_window: int = 20,
        volume_min: float = 1.2,
        sl_atr: float = 2.0,
        tp_r: tuple[float, ...] = (1.5, 3.0),
        cooldown_bars: int = 8,
        is_mock: bool = False,
    ) -> None:
        self.symbol = to_canonical_symbol(symbol)
        self.asset_class = asset_class
        self.donchian_window = donchian_window
        self.volume_min = volume_min
        self.sl_atr = sl_atr
        self.tp_r = tp_r
        self.is_mock = is_mock
        # Breakouts are allowed in range (start of expansion) or early trend.
        self._filters = FilterConfig(
            allow_regimes=("range", "trend"),
            block_high_vol=False,
            cooldown_bars=cooldown_bars,
        )
        self._state = FilterState()

    def feature_kwargs(self) -> dict:
        return {"donchian_window": self.donchian_window}

    def signals_at(self, bars_by_timeframe: Mapping[str, pd.DataFrame], as_of: datetime) -> list:
        tf, bars = context_from_bars(bars_by_timeframe, as_of)
        ctx = last_bar_context(bars, self.feature_kwargs())
        return self._signals_from_ctx(tf, as_of, ctx)

    def _signals_from_ctx(self, tf, as_of, ctx, htf_name=None, htf_ctx=None) -> list:
        if ctx is None or ctx.atr is None:
            return []
        hh, ll = ctx.features.get("donchian_high"), ctx.features.get("donchian_low")
        vratio = ctx.features.get("volume_ratio")
        if pd.isna(hh) or pd.isna(ll) or pd.isna(vratio):
            return []
        if vratio < self.volume_min:
            return []
        side = None
        if ctx.close > hh:
            side = "long"
        elif ctx.close < ll:
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
                rationale=(
                    f"H3 breakout: close {ctx.close:.4g} beyond Donchian "
                    f"{self.donchian_window} ({'high' if side == 'long' else 'low'}) "
                    f"with volume ratio {float(vratio):.2f} on {tf}."
                ),
                confidence=conf,
                features_snapshot={
                    **flag,
                    "donchian_high": float(hh),
                    "donchian_low": float(ll),
                    "volume_ratio": float(vratio),
                    "regime": ctx.regime,
                    "high_vol": ctx.high_vol,
                    "atr": ctx.atr,
                },
            )
        ]
