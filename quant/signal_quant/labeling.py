"""Triple-barrier labeling (Data Engineer, v1).

A trade opened on the fill (next bar open after the signal bar) ends at the
first of:

- stop_loss touched,
- the first take_profit touched,
- timeout at horizon_bars after the fill bar.

If stop and a target are both touched *within the same bar*, the outcome is
a stop (``hit_sl``). These labels — outcome, R multiple, bars held — are what
confidence calibration trains on. This module does not report performance.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from signal_quant.bars import ensure_utc_index


def _try_import_resolve():
    """Return official ``signal_data.barriers.resolve``. Missing import fails loudly."""
    from signal_quant.bars import _ensure_signal_data_path

    _ensure_signal_data_path()
    from signal_data.barriers import resolve

    return resolve



def _as_outcome_str(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        return str(value.value)
    return str(value)


def _normalize_resolve(result) -> dict:
    """Map a resolve() return value onto the labeling dict this package uses."""
    if result is None:
        return {
            "outcome": "cancelled",
            "r_multiple": float("nan"),
            "bars_held": 0,
            "exit_price": float("nan"),
            "exit_time": None,
        }
    if isinstance(result, dict):
        return {
            "outcome": result.get("outcome", result.get("exit_reason", result.get("reason"))),
            "r_multiple": float(result.get("r_multiple", result.get("R", result.get("r", float("nan"))))),
            "bars_held": int(result.get("bars_held", result.get("barsHeld", 0) or 0)),
            "exit_price": float(result.get("exit_price", result.get("exit", float("nan")))),
            "exit_time": result.get("exit_time", result.get("exit_at")),
        }
    # Attribute-style result (dataclass / pydantic / namedtuple).
    outcome = _as_outcome_str(getattr(result, "outcome", None)) or _as_outcome_str(
        getattr(result, "status", None)
    ) or _as_outcome_str(getattr(result, "exit_reason", None)) or _as_outcome_str(
        getattr(result, "reason", None)
    )
    r = getattr(result, "r_multiple", None)
    if r is None:
        r = getattr(result, "R", getattr(result, "r", float("nan")))
    return {
        "outcome": outcome,
        "r_multiple": float(r) if r is not None else float("nan"),
        "bars_held": int(getattr(result, "bars_held", 0) or 0),
        "exit_price": float(getattr(result, "exit_price", float("nan"))),
        "exit_time": getattr(result, "exit_time", None),
    }


def label_signal(signal, bars: pd.DataFrame) -> dict:
    """Label one ``Signal`` against a bar frame.

    Delegates to ``signal_data.barriers.resolve(signal, bars)`` when that
    function exists. Otherwise uses the thin local fallback below (TODO:
    delete the fallback once ``resolve`` ships).
    """
    resolve = _try_import_resolve()
    if resolve is not None:
        return _normalize_resolve(resolve(signal, bars))
    # TODO: remove this fallback when signal_data.barriers.resolve is the only path.
    df = ensure_utc_index(bars)
    as_of = pd.Timestamp(signal.bar_close_time)
    if as_of.tzinfo is None:
        as_of = as_of.tz_localize("UTC")
    else:
        as_of = as_of.tz_convert("UTC")
    matches = df.index.get_indexer([as_of], method=None)
    signal_index = int(matches[0]) if len(matches) and matches[0] != -1 else None
    if signal_index is None or signal_index < 0:
        # closest close_time <= as_of
        le = df.index[df.index <= as_of]
        if len(le) == 0:
            return {
                "outcome": "cancelled",
                "r_multiple": float("nan"),
                "bars_held": 0,
                "exit_price": float("nan"),
                "exit_time": None,
            }
        signal_index = int(df.index.get_loc(le[-1]))
    tps = list(signal.take_profit or [])
    return _fallback_label_triple_barrier(
        df,
        signal_index=signal_index,
        side=str(signal.side.value if hasattr(signal.side, "value") else signal.side),
        stop_loss=float(signal.stop_loss),
        take_profit=tps,
        horizon_bars=int(signal.horizon_bars),
        entry_price=None if signal.entry is None else float(signal.entry),
    )


def _touched(side: str, bar: pd.Series, level: float, *, is_stop: bool) -> bool:
    high, low = float(bar["high"]), float(bar["low"])
    if side == "long":
        return (low <= level) if is_stop else (high >= level)
    if side == "short":
        return (high >= level) if is_stop else (low <= level)
    raise ValueError(side)


def _r_multiple(side: str, entry: float, stop: float, exit_price: float) -> float:
    risk = (entry - stop) if side == "long" else (stop - entry)
    if risk == 0:
        return float("nan")
    pnl = (exit_price - entry) if side == "long" else (entry - exit_price)
    return float(pnl / risk)


def _fallback_label_triple_barrier(
    bars: pd.DataFrame,
    *,
    signal_index: int,
    side: str,
    stop_loss: float,
    take_profit: Iterable[float],
    horizon_bars: int,
    entry_price: float | None = None,
) -> dict:
    """Local triple-barrier implementation.

    TODO: delete once ``signal_data.barriers.resolve(signal, bars)`` is the
    only implementation (do not keep a second long-term copy).
    """
    df = ensure_utc_index(bars)
    tps = sorted(float(x) for x in take_profit)
    if side == "short":
        tps = sorted(tps, reverse=True)
    fill_i = signal_index + 1
    if fill_i >= len(df) or horizon_bars < 1:
        return {
            "outcome": "cancelled",
            "r_multiple": float("nan"),
            "bars_held": 0,
            "exit_price": float("nan"),
            "exit_time": None,
        }
    entry = float(df["open"].iloc[fill_i] if entry_price is None else entry_price)
    last_i = min(fill_i + horizon_bars - 1, len(df) - 1)
    for i in range(fill_i, last_i + 1):
        bar = df.iloc[i]
        stop_hit = _touched(side, bar, stop_loss, is_stop=True)
        tp_hit = next((tp for tp in tps if _touched(side, bar, tp, is_stop=False)), None)
        if stop_hit and tp_hit is not None:
            return {
                "outcome": "hit_sl",
                "r_multiple": _r_multiple(side, entry, stop_loss, stop_loss),
                "bars_held": i - fill_i + 1,
                "exit_price": float(stop_loss),
                "exit_time": df.index[i],
            }
        if stop_hit:
            return {
                "outcome": "hit_sl",
                "r_multiple": _r_multiple(side, entry, stop_loss, stop_loss),
                "bars_held": i - fill_i + 1,
                "exit_price": float(stop_loss),
                "exit_time": df.index[i],
            }
        if tp_hit is not None:
            return {
                "outcome": "hit_tp",
                "r_multiple": _r_multiple(side, entry, stop_loss, tp_hit),
                "bars_held": i - fill_i + 1,
                "exit_price": float(tp_hit),
                "exit_time": df.index[i],
            }
    exit_price = float(df["close"].iloc[last_i])
    return {
        "outcome": "expired",
        "r_multiple": _r_multiple(side, entry, stop_loss, exit_price),
        "bars_held": last_i - fill_i + 1,
        "exit_price": exit_price,
        "exit_time": df.index[last_i],
    }


def label_triple_barrier(
    bars: pd.DataFrame,
    *,
    signal_index: int,
    side: str,
    stop_loss: float,
    take_profit: Iterable[float],
    horizon_bars: int,
    entry_price: float | None = None,
) -> dict:
    """Label one trade.

    ``signal_index`` is the bar at whose close the signal was generated.
    Fill is the open of ``signal_index + 1`` (or ``entry_price`` if given).
    Path evaluation starts on the fill bar and runs for ``horizon_bars`` bars.

    When ``signal_data.barriers.resolve`` is importable this constructs a
    minimal signal-like object and delegates; otherwise it uses the thin
    fallback (TODO: remove the fallback once resolve ships).
    """
    resolve = _try_import_resolve()
    if resolve is not None:
        # Pass bars through unchanged; only read the close time for the shim.
        if "close_time" in bars.columns:
            as_of = pd.to_datetime(bars["close_time"].iloc[signal_index], utc=True)
        else:
            as_of = ensure_utc_index(bars).index[signal_index]
        shim = _SignalShim(
            side=side,
            stop_loss=float(stop_loss),
            take_profit=list(take_profit),
            horizon_bars=int(horizon_bars),
            bar_close_time=as_of,
            entry=entry_price,
        )
        return _normalize_resolve(resolve(shim, bars))
    return _fallback_label_triple_barrier(
        bars,
        signal_index=signal_index,
        side=side,
        stop_loss=stop_loss,
        take_profit=take_profit,
        horizon_bars=horizon_bars,
        entry_price=entry_price,
    )


class _SignalShim:
    """Minimal signal-like object for ``resolve(signal, bars)``."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def label_signals(bars: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    """Vector of labels for an ``as_frame``-style signal frame (synthetic or research)."""
    df = ensure_utc_index(bars)
    records = []
    for i, (ts, row) in enumerate(signals.iterrows()):
        side = row.get("side", "flat")
        if side in (None, "flat") or pd.isna(row.get("stop_loss", np.nan)):
            records.append(
                {"outcome": None, "r_multiple": np.nan, "bars_held": 0, "exit_price": np.nan}
            )
            continue
        tps = row["take_profit"] if "take_profit" in signals.columns else []
        if not isinstance(tps, (list, tuple)):
            tps = []
        records.append(
            label_triple_barrier(
                df,
                signal_index=i,
                side=str(side),
                stop_loss=float(row["stop_loss"]),
                take_profit=tps,
                horizon_bars=int(row.get("horizon_bars", 1) or 1),
                entry_price=None,
            )
        )
    return pd.DataFrame(records, index=signals.index)
