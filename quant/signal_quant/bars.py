"""Bar-window helpers used by the backtester adapter and strategies.

Rules (Data Engineer + Lead Architect, v1):

- Every timeframe passed into ``generate`` is already truncated at ``as_of``.
- Higher timeframes contain *only fully closed* bars. Strategies must not
  resample a lower timeframe to invent a partial higher-timeframe bar.
- Building higher timeframes from a single lower-TF series is the job of
  ``as_frame`` / the Data backtester, using ``signal_data``'s ``resample_closed``
  (session-aware for equity / FX). Quant does not own that logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

import pandas as pd

from signal_quant.models import TIMEFRAMES

TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
TF_RULE = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
OHLCV = ("open", "high", "low", "close", "volume")
_INFER_TOLERANCE = {
    "15m": (10, 20),
    "1h": (45, 75),
    "4h": (200, 280),
    "1d": (1200, 2000),
}


def to_utc(ts: datetime | pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy indexed by bar close time (UTC), sorted, OHLCV columns present."""
    out = df.copy()
    if "close_time" in out.columns:
        idx = pd.DatetimeIndex(pd.to_datetime(out["close_time"], utc=True))
        out.index = idx
    elif "timestamp" in out.columns and not isinstance(out.index, pd.DatetimeIndex):
        idx = pd.DatetimeIndex(pd.to_datetime(out["timestamp"], utc=True))
        out.index = idx
    if not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError("bars need a DatetimeIndex or a close_time/timestamp column")
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    out = out.sort_index()
    if out.index.has_duplicates:
        out = out[~out.index.duplicated(keep="last")]
    missing = [c for c in ("open", "high", "low", "close") if c not in out.columns]
    if missing:
        raise ValueError(f"bars missing required columns: {missing}")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    # QA's generate() gate requires a UTC close_time column (not only an index).
    out = out.copy()
    out["close_time"] = out.index
    return out


def infer_timeframe(df: pd.DataFrame) -> str:
    idx = ensure_utc_index(df).index
    if len(idx) < 2:
        raise ValueError("need at least two bars to infer timeframe")
    minutes = idx.to_series().diff().dt.total_seconds().median() / 60.0
    for tf, (lo, hi) in _INFER_TOLERANCE.items():
        if lo <= minutes <= hi:
            return tf
    raise ValueError(f"cannot infer timeframe from median spacing {minutes:.1f} minutes")


def higher_timeframes(base_tf: str) -> list[str]:
    if base_tf not in TF_MINUTES:
        raise ValueError(f"unknown timeframe {base_tf}")
    base = TF_MINUTES[base_tf]
    return [tf for tf, m in TF_MINUTES.items() if m > base]


def truncate_at(df: pd.DataFrame, as_of: datetime | pd.Timestamp) -> pd.DataFrame:
    """Keep bars whose close time is <= as_of (closed bars only)."""
    out = ensure_utc_index(df)
    cut = to_utc(as_of)
    return out.loc[out.index <= cut]


def _ensure_signal_data_path() -> None:
    """Make ``signal_data`` importable from the sibling data package without a pip install."""
    import sys
    from pathlib import Path as _Path

    src = _Path(__file__).resolve().parents[2] / "data" / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def import_data_resample_closed():
    """Return official ``signal_data.resample.resample_closed``. Missing import fails loudly."""
    _ensure_signal_data_path()
    from signal_data.resample import resample_closed

    return resample_closed


def _call_data_resample_closed(
    fn,
    df: pd.DataFrame,
    target_tf: str,
    as_of: datetime | pd.Timestamp,
    *,
    asset_class: str | None = None,
):
    import inspect

    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    kwargs = {}
    if "df" in params:
        kwargs["df"] = df
    elif "bars" in params:
        kwargs["bars"] = df
    if "target_tf" in params:
        kwargs["target_tf"] = target_tf
    elif "timeframe" in params:
        kwargs["timeframe"] = target_tf
    elif "tf" in params:
        kwargs["tf"] = target_tf
    if "as_of" in params:
        kwargs["as_of"] = as_of
    if "asset_class" in params and asset_class is not None:
        kwargs["asset_class"] = asset_class
    if kwargs:
        try:
            return fn(**kwargs)
        except TypeError:
            pass
    try:
        return fn(df, target_tf, as_of, asset_class=asset_class)
    except TypeError:
        return fn(df, target_tf, as_of)


def _source_minutes(df: pd.DataFrame) -> int:
    idx = ensure_utc_index(df).index
    if len(idx) < 2:
        raise ValueError("need at least two bars to infer source timeframe")
    minutes = idx.to_series().diff().dt.total_seconds().median() / 60.0
    for tf, (lo, hi) in _INFER_TOLERANCE.items():
        if lo <= minutes <= hi:
            return TF_MINUTES[tf]
    raise ValueError(f"cannot infer source timeframe from median spacing {minutes:.1f} minutes")


def _crypto_full_count_resample(
    df: pd.DataFrame,
    target_tf: str,
    as_of: datetime | pd.Timestamp,
) -> pd.DataFrame:
    """UTC-aligned resample that keeps a bucket only when every source bar is present.

    TODO: remove this fallback once ``signal_data.resample_closed`` is published
    and imported above. Do not extend this into session-aware equity/FX logic.
    """
    if target_tf not in TIMEFRAMES:
        raise ValueError(f"target_tf must be one of {sorted(TIMEFRAMES)}")
    src = truncate_at(df, as_of)
    if src.empty:
        return src.iloc[0:0]
    src_min = _source_minutes(src)
    tgt_min = TF_MINUTES[target_tf]
    if tgt_min % src_min != 0:
        raise ValueError(f"cannot aggregate {src_min}m bars into {target_tf}")
    expected = tgt_min // src_min
    rule = TF_RULE[target_tf]
    agg = {c: fn for c, fn in (
        ("open", "first"),
        ("high", "max"),
        ("low", "min"),
        ("close", "last"),
        ("volume", "sum"),
    ) if c in src.columns}
    resampled = src.resample(rule, label="right", closed="right", origin="epoch").agg(agg)
    counts = src["close"].resample(rule, label="right", closed="right", origin="epoch").count()
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])
    cut = to_utc(as_of)
    resampled = resampled.loc[resampled.index <= cut]
    complete = counts.reindex(resampled.index).fillna(0).astype(int) == expected
    out = resampled.loc[complete].copy()
    if not out.empty:
        out["close_time"] = out.index
        out["partial_session"] = False
    return out


def resample_closed(
    df: pd.DataFrame,
    target_tf: str,
    as_of: datetime | pd.Timestamp,
    *,
    asset_class: str | None = None,
) -> pd.DataFrame:
    """Thin wrapper around ``signal_data.resample_closed``.

    Session-aware equity / FX 4h rules live only in the data package. If that
    function is not published yet, equity/FX 4h raises ``NotImplementedError``
    so a partial bucket cannot slip through. Crypto may use a temporary
    UTC full-count fallback (see TODO in ``_crypto_full_count_resample``).
    """
    fn = import_data_resample_closed()
    if fn is not None:
        return _call_data_resample_closed(
            fn, df, target_tf, as_of, asset_class=asset_class
        )
    ac = None if asset_class is None else str(asset_class)
    if ac in {"equity", "fx"} and target_tf == "4h":
        raise NotImplementedError(
            "equity/fx 4h resampling is owned by signal_data.resample_closed "
            "(session-aware: 09:30 ET equity buckets, FX weekend drop). "
            "Quant will not invent a partial bucket."
        )
    return _crypto_full_count_resample(df, target_tf, as_of)


def bars_by_timeframe_from_base(
    df: pd.DataFrame,
    as_of: datetime | pd.Timestamp,
    base_timeframe: str,
    higher: list[str] | None = None,
    *,
    asset_class: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the mapping the backtester passes into ``generate``.

    The base timeframe is truncated at as_of. Higher timeframes are resampled
    from fully closed bars only, via ``resample_closed``.
    """
    base = truncate_at(df, as_of)
    out: dict[str, pd.DataFrame] = {base_timeframe: base}
    for tf in (higher if higher is not None else higher_timeframes(base_timeframe)):
        if TF_MINUTES[tf] <= TF_MINUTES[base_timeframe]:
            continue
        out[tf] = resample_closed(base, tf, as_of, asset_class=asset_class)
    return out


def timeframe_just_closed(
    bars_by_timeframe: Mapping[str, pd.DataFrame],
    as_of: datetime | pd.Timestamp,
) -> str | None:
    """Return the shortest timeframe whose latest bar closes exactly at as_of."""
    cut = to_utc(as_of)
    hits: list[tuple[int, str]] = []
    for tf, bars in bars_by_timeframe.items():
        if bars is None or len(bars) == 0:
            continue
        idx = ensure_utc_index(bars).index
        if idx[-1] == cut and tf in TF_MINUTES:
            hits.append((TF_MINUTES[tf], tf))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def last_close(bars: pd.DataFrame) -> float:
    return float(ensure_utc_index(bars)["close"].iloc[-1])


def truncate_all(
    bars_by_timeframe: Mapping[str, pd.DataFrame],
    as_of: datetime | pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    """Drop every bar with close_time > as_of, on every timeframe.

    ``generate`` must do this itself. The backtester already truncates, but
    QA's lookahead gate passes the *full* history (and a future-scrambled
    copy) and requires the signal to be unchanged.
    """
    return {
        tf: truncate_at(df, as_of)
        for tf, df in bars_by_timeframe.items()
        if df is not None
    }

