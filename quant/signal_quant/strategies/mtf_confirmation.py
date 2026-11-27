"""H4 — Multi-timeframe confirmation: closed HTF trend + LTF pullback. See docs/hypotheses.md.

Uses only higher-timeframe bars supplied in ``bars_by_timeframe``. Does not
resample a lower timeframe to invent a partial HTF bar. If the HTF series is
missing or not yet closed, this strategy emits nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from signal_quant.bars import TF_MINUTES, ensure_utc_index, to_utc
from signal_quant.filters import FilterConfig, FilterState, accept
from signal_quant.levels import atr_levels
from signal_quant.strategy import Strategy, context_from_bars, make_signal
from signal_quant.symbols import to_canonical_symbol
from signal_quant.strategies.common import (
    HORIZON_DEFAULT,
    context_at_index,
    feature_frames,
    last_bar_context,
    uncalibrated_prior,
)

# Preferred HTF for each trigger TF (must already be in the mapping, fully closed).
HTF_PREF = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": None}


class MtfConfirmation(Strategy):
    strategy_id = "mtf_confirmation"
    strategy_version = "0.1.0"
    name = "Multi-timeframe confirmation"
    hypothesis_id = "H4"
    description = 'Takes direction from a fully closed higher-timeframe ADX-confirmed trend and times entry on a lower-timeframe pullback to the fast EMA.'
    hypothesis = 'A fully closed higher-timeframe ADX-confirmed trend sets direction, and a lower-timeframe pullback to the fast EMA is used to time entry.'
    # 1d has no higher TF in the locked universe.
    supported = tuple((ac, tf) for ac in ("crypto", "equity", "fx") for tf in ("15m", "1h", "4h"))

    @classmethod
    def required_timeframes(cls, timeframe: str) -> dict[str, int]:
        from signal_quant.strategy import LOOKBACK_BARS

        req = {timeframe: LOOKBACK_BARS}
        htf = HTF_PREF.get(timeframe)
        if htf:
            req[htf] = LOOKBACK_BARS
        return req

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
        self.symbol = to_canonical_symbol(symbol)
        self.asset_class = asset_class
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.adx_min = adx_min
        self.sl_atr = sl_atr
        self.tp_r = tp_r
        self.is_mock = is_mock
        self._filters = FilterConfig(
            allow_regimes=("trend", "range"),
            cooldown_bars=cooldown_bars,
        )
        self._state = FilterState()

    def _htf_ctx(
        self, bars_by_timeframe: Mapping[str, pd.DataFrame], trigger_tf: str
    ):
        want = HTF_PREF.get(trigger_tf)
        if not want or want not in bars_by_timeframe:
            # Next-best: any provided TF strictly higher than the trigger.
            higher = [
                tf
                for tf in bars_by_timeframe
                if tf in TF_MINUTES and TF_MINUTES[tf] > TF_MINUTES[trigger_tf]
                and bars_by_timeframe[tf] is not None
                and len(bars_by_timeframe[tf]) > 0
            ]
            if not higher:
                return None, None
            higher.sort(key=lambda t: TF_MINUTES[t])
            want = higher[0]
        htf_bars = ensure_utc_index(bars_by_timeframe[want])
        if htf_bars.empty:
            return None, None
        ctx = last_bar_context(htf_bars, self.feature_kwargs())
        return want, ctx

    def feature_kwargs(self) -> dict:
        return {"ema_fast": self.ema_fast, "ema_slow": self.ema_slow}

    def _prepare_htf(self, window: Mapping[str, pd.DataFrame], trigger_tf: str):
        """Compute HTF features once; per-bar lookup uses only fully closed HTF bars."""
        want = HTF_PREF.get(trigger_tf)
        if not want or want not in window:
            higher = [
                tf
                for tf in window
                if tf in TF_MINUTES
                and TF_MINUTES[tf] > TF_MINUTES[trigger_tf]
                and window[tf] is not None
                and len(window[tf]) > 0
            ]
            if not higher:
                return None
            higher.sort(key=lambda t: TF_MINUTES[t])
            want = higher[0]
        htf_bars = ensure_utc_index(window[want])
        if htf_bars.empty:
            return None
        feats, reg = feature_frames(htf_bars, self.feature_kwargs())
        return {"name": want, "bars": htf_bars, "feats": feats, "reg": reg}

    def _htf_context_at(self, cache, as_of: datetime):
        if not cache:
            return None, None
        idx = cache["bars"].index
        loc = int(idx.searchsorted(to_utc(as_of), side="right")) - 1
        if loc < 0:
            return cache["name"], None
        ctx = context_at_index(cache["bars"], cache["feats"], cache["reg"], loc)
        return cache["name"], ctx

    def signals_at(self, bars_by_timeframe: Mapping[str, pd.DataFrame], as_of: datetime) -> list:
        tf, bars = context_from_bars(bars_by_timeframe, as_of)
        htf_name, htf = self._htf_ctx(bars_by_timeframe, tf)
        ctx = last_bar_context(bars, self.feature_kwargs())
        return self._signals_from_ctx(tf, as_of, ctx, htf_name=htf_name, htf_ctx=htf)

    def _signals_from_ctx(self, tf, as_of, ctx, htf_name=None, htf_ctx=None) -> list:
        htf = htf_ctx
        if htf is None or htf.adx is None or htf_name is None:
            return []
        if htf.adx < self.adx_min:
            return []
        fast, slow = htf.features["ema_fast"], htf.features["ema_slow"]
        if pd.isna(fast) or pd.isna(slow) or fast == slow:
            return []
        htf_side = "long" if fast > slow else "short"

        if ctx is None or ctx.atr is None:
            return []
        l_fast = ctx.features["ema_fast"]
        if pd.isna(l_fast):
            return []
        # Pullback-and-resume: LTF close back on the HTF side of its fast EMA
        # after having touched or crossed it (close vs EMA, current bar).
        if htf_side == "long" and not (ctx.close >= l_fast):
            return []
        if htf_side == "short" and not (ctx.close <= l_fast):
            return []
        # Require LTF not to be extended: price still near the fast EMA
        # (within 1 ATR) so this is a pullback, not a late chase.
        if abs(ctx.close - float(l_fast)) > ctx.atr:
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
        stop, tps = atr_levels(
            htf_side, ctx.close, ctx.atr, sl_atr=self.sl_atr, tp_r=self.tp_r
        )
        return [
            make_signal(
                strategy=self,
                symbol=self.symbol,
                asset_class=self.asset_class,
                timeframe=tf,
                side=htf_side,
                as_of=as_of,
                entry=ctx.close,
                stop_loss=stop,
                take_profit=tps,
                horizon_bars=HORIZON_DEFAULT[tf],
                confidence=conf,
                features_snapshot={
                    **flag,
                    "htf": htf_name,
                    "htf_ema_fast": float(fast),
                    "htf_ema_slow": float(slow),
                    "htf_adx": float(htf.adx),
                    "ltf_ema_fast": float(l_fast),
                    "regime": ctx.regime,
                    "high_vol": ctx.high_vol,
                    "atr": ctx.atr,
                },
                rationale=(
                    f"H4 MTF: closed {htf_name} trend is {htf_side} "
                    f"(ADX {htf.adx:.1f}); {tf} close is back on that side of "
                    f"its fast EMA (pullback, not resampled)."
                ),
            )
        ]
