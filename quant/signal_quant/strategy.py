"""Common Strategy interface used by the Data backtester and live pipeline.

The public method is ``generate(bars_by_timeframe, as_of) -> list[Signal]``.
The base implementation truncates every timeframe to ``close_time <= as_of``
before calling ``signals_at``, so a strategy cannot see future bars even when
QA's lookahead gate (or a sloppy caller) passes a longer history.

``generate`` is a pure function of its arguments: subclasses must not keep
cooldown or other running state that would change a second call at the same
as_of. Cooldown is applied by ``as_frame`` / the backtester after the fact.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

import numpy as np
import pandas as pd

from signal_quant.bars import ensure_utc_index, to_utc, truncate_all
from signal_quant.ml_policy import policy_flags
from signal_quant.models import AssetClass, Side, Signal, SignalStatus
from signal_quant.symbols import to_canonical_symbol

# Floats in features_snapshot are rounded so the QA gate's 1e-9 compare is stable
# and no run-time clocks or unordered dumps leak into the snapshot.
_SNAPSHOT_DIGITS = 12


def deterministic_snapshot(data: dict[str, Any], *, ndigits: int = _SNAPSHOT_DIGITS) -> dict[str, Any]:
    """JSON-safe, key-sorted, rounded snapshot. No clocks, no numpy scalars."""

    def conv(v: Any) -> Any:
        if isinstance(v, dict):
            return {str(k): conv(v[k]) for k in sorted(v, key=lambda x: str(x))}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        if isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)):
            return int(v)
        if isinstance(v, (float, np.floating)):
            x = float(v)
            if x != x or x in (float("inf"), float("-inf")):
                return None
            return round(x, ndigits)
        # datetimes that represent *feature* values should be ISO UTC; do not
        # insert "now". If a clock sneaks in, stringify it deterministically.
        if isinstance(v, (datetime, pd.Timestamp)):
            ts = to_utc(v)
            return ts.isoformat()
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return v

    return conv(dict(data))


# Locked universe used for the default ``supported`` set.
_ASSET_CLASSES = ("crypto", "equity", "fx")
_TIMEFRAMES = ("15m", "1h", "4h", "1d")
# Warmup: vol_lookback 100 + EMA 48 + a little headroom.
LOOKBACK_BARS = 200


class Strategy(ABC):
    """Runnable strategy. Not the same object as ``signal_shared.Strategy`` metadata."""

    strategy_id: str
    strategy_version: str
    version: str  # alias of strategy_version; set in __init_subclass__
    name: str
    hypothesis_id: str
    description: str
    hypothesis: str
    is_mock: bool = False  # set True for synthetic smoke runs
    supported: tuple[tuple[str, str], ...] = tuple(
        (ac, tf) for ac in _ASSET_CLASSES for tf in _TIMEFRAMES
    )

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        ver = getattr(cls, "strategy_version", None)
        if ver and not cls.__dict__.get("version"):
            cls.version = ver

    @classmethod
    def required_timeframes(cls, timeframe: str) -> dict[str, int]:
        """Timeframes ``generate`` needs, mapped to lookback bars."""
        return {timeframe: LOOKBACK_BARS}

    def generate(
        self,
        bars_by_timeframe: Mapping[str, pd.DataFrame],
        as_of: datetime,
    ) -> list[Signal]:
        """Return 0..N signals using only data with close_time <= as_of.

        Subclasses implement ``signals_at`` on an already-truncated mapping.
        Do not override ``generate`` — that would skip the mandatory truncate
        and the defensive stale / missing-as_of / unsupported-pair guards.
        """
        window = truncate_all(bars_by_timeframe, as_of)
        try:
            tf, bars = context_from_bars(window, as_of)
        except ValueError:
            return []
        if bars is None or bars.empty:
            return []
        as_of_utc = to_utc(as_of)
        last_close = to_utc(bars.index[-1])
        if last_close != as_of_utc:
            # Defensive: as_of bar is missing (load_closed / get_candles dropped it).
            return []
        from signal_quant.masks import is_stale

        if bool(is_stale(bars).iloc[-1]):
            # Defensive: raw store may still carry a stale placeholder at as_of.
            return []
        ac = getattr(self, "asset_class", None)
        if ac is not None:
            pair = (str(ac), tf)
            supported = getattr(self, "supported", None)
            if supported is not None and pair not in supported:
                return []
        return self.signals_at(window, as_of)

    @abstractmethod
    def signals_at(
        self,
        bars_by_timeframe: Mapping[str, pd.DataFrame],
        as_of: datetime,
    ) -> list[Signal]:
        """Emit signals. ``bars_by_timeframe`` is already truncated at as_of."""

    def feature_kwargs(self) -> dict[str, Any]:
        """Keyword arguments passed to ``compute_features`` for this instance."""
        return {}

    def _prepare_htf(self, window: Mapping[str, pd.DataFrame], trigger_tf: str):
        """Optional precomputed higher-timeframe frames. Default: unused."""
        return None

    def _htf_context_at(self, cache, as_of: datetime):
        return None, None

    def _signals_from_ctx(
        self,
        tf: str,
        as_of: datetime,
        ctx,
        htf_name: str | None = None,
        htf_ctx=None,
    ) -> list[Signal]:
        """Emit 0..N signals from a precomputed last-bar context. Subclasses implement."""
        raise NotImplementedError

    def signals_series(
        self,
        bars_by_timeframe: Mapping[str, pd.DataFrame],
        start: datetime,
        end: datetime,
        *,
        timeframe: str | None = None,
    ) -> list[Signal]:
        """Return the signals ``generate()`` would emit at each closed trigger bar in ``[start, end]``.

        Indicators are computed once on the frame truncated at ``end``. Only
        data up to each bar is used (features are causal; no lookahead).
        Higher timeframes include only bars whose close is ``<=`` that bar's
        close (fully closed HTF bars). Stale or missing as_of bars emit nothing,
        matching ``generate``.

        Signature::

            signals_series(bars_by_timeframe, start, end, *, timeframe=None) -> list[Signal]
        """
        from signal_quant.bars import TF_MINUTES, ensure_utc_index
        from signal_quant.strategies.common import context_at_index, feature_frames

        start_u = to_utc(start)
        end_u = to_utc(end)
        if start_u > end_u:
            return []
        window = truncate_all(bars_by_timeframe, end_u)
        tf = timeframe
        if tf is None:
            ranked = [
                (TF_MINUTES[name], name)
                for name, df in window.items()
                if name in TF_MINUTES and df is not None and len(df)
            ]
            if not ranked:
                return []
            ranked.sort()
            tf = ranked[0][1]
        if tf not in window or window[tf] is None:
            return []
        ac = getattr(self, "asset_class", None)
        supported = getattr(self, "supported", None)
        if ac is not None and supported is not None and (str(ac), tf) not in supported:
            return []
        bars = ensure_utc_index(window[tf])
        if bars.empty:
            return []
        feats, reg = feature_frames(bars, self.feature_kwargs())
        htf_cache = self._prepare_htf(window, tf)
        lo = int(bars.index.searchsorted(start_u, side="left"))
        hi = int(bars.index.searchsorted(end_u, side="right"))
        out: list[Signal] = []
        stale = feats["is_stale"] if "is_stale" in feats.columns else None
        for i in range(lo, hi):
            as_of_ts = bars.index[i]
            if stale is not None and bool(stale.iloc[i]):
                continue
            ctx = context_at_index(bars, feats, reg, i)
            if ctx is None:
                continue
            htf_name, htf_ctx = (None, None)
            if htf_cache is not None:
                htf_name, htf_ctx = self._htf_context_at(htf_cache, as_of_ts)
            as_of_dt = as_of_ts.to_pydatetime() if hasattr(as_of_ts, "to_pydatetime") else as_of_ts
            out.extend(
                self._signals_from_ctx(tf, as_of_dt, ctx, htf_name=htf_name, htf_ctx=htf_ctx)
            )
        return out

    def reset(self) -> None:
        """Clear adapter-side state. ``generate`` itself must stay stateless."""
        state = getattr(self, "_state", None)
        if state is not None and hasattr(state, "last_emit_index"):
            state.last_emit_index = None

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.strategy_id,
            "version": self.strategy_version,
            "name": self.name,
            "hypothesis": self.hypothesis_id,
        }


def normalize_as_of(as_of: datetime) -> datetime:
    ts = to_utc(as_of)
    return ts.to_pydatetime()


def snapshot_policy(asset_class: str | AssetClass, timeframe: str) -> dict[str, Any]:
    return policy_flags(str(asset_class), timeframe)


def make_signal(
    *,
    strategy: Strategy,
    symbol: str,
    asset_class: str | AssetClass,
    timeframe: str,
    side: str | Side,
    as_of: datetime,
    entry: float | None,
    stop_loss: float | None,
    take_profit: list[float],
    horizon_bars: int,
    confidence: float,
    features_snapshot: dict[str, Any],
    rationale: str,
    status: SignalStatus = SignalStatus.active,
) -> Signal:
    as_of_dt = normalize_as_of(as_of)
    snap = deterministic_snapshot({**dict(features_snapshot), **snapshot_policy(asset_class, timeframe)})
    ac = asset_class if isinstance(asset_class, AssetClass) else AssetClass(asset_class)
    sd = side if isinstance(side, Side) else Side(side)
    tps = [round(float(x), _SNAPSHOT_DIGITS) for x in take_profit]
    entry_v = None if entry is None else round(float(entry), _SNAPSHOT_DIGITS)
    stop_v = None if stop_loss is None else round(float(stop_loss), _SNAPSHOT_DIGITS)
    return Signal(
        id=str(uuid4()),
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        symbol=to_canonical_symbol(symbol),
        asset_class=ac,
        timeframe=timeframe,
        side=sd,
        generated_at=as_of_dt,
        bar_close_time=as_of_dt,
        entry=entry_v,
        stop_loss=stop_v,
        take_profit=tps,
        horizon_bars=horizon_bars,
        confidence=float(confidence),
        features_snapshot=snap,
        rationale=rationale[:500],
        status=status,
        is_mock=bool(getattr(strategy, "is_mock", False)),
        # Uncalibrated until Data exports trades and a named calibration run exists.
        confidence_calibrated=False,
        calibration_run_id=None,
    )


def context_from_bars(
    bars_by_timeframe: Mapping[str, pd.DataFrame],
    as_of: datetime,
    *,
    prefer: str | None = None,
) -> tuple[str, pd.DataFrame]:
    """Pick the trigger timeframe (just closed at as_of) and its truncated frame."""
    from signal_quant.bars import timeframe_just_closed, TF_MINUTES

    tf = prefer or timeframe_just_closed(bars_by_timeframe, as_of)
    if tf is None:
        candidates = []
        for k, v in bars_by_timeframe.items():
            if v is None or len(v) == 0 or k not in TF_MINUTES:
                continue
            candidates.append((TF_MINUTES[k], k))
        if not candidates:
            raise ValueError("bars_by_timeframe is empty at as_of")
        candidates.sort()
        tf = candidates[0][1]
    return tf, ensure_utc_index(bars_by_timeframe[tf])
