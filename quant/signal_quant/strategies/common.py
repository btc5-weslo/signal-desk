"""Shared helpers for the v0 baseline strategies."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from signal_quant.features import compute_features
from signal_quant.regime import last_regime, regime_from_features

HORIZON_DEFAULT = {"15m": 16, "1h": 16, "4h": 10, "1d": 10}


@dataclass
class LastBar:
    features: pd.Series
    regime: str
    high_vol: bool
    adx: float | None
    close: float
    atr: float | None
    index: int
    time: pd.Timestamp


def last_bar_context(bars: pd.DataFrame, feature_kwargs: dict | None = None) -> LastBar | None:
    if bars is None or len(bars) == 0:
        return None
    feats = compute_features(bars, **(feature_kwargs or {}))
    if "is_stale" in feats.columns and bool(feats["is_stale"].iloc[-1]):
        return None
    reg = regime_from_features(feats)
    i = len(bars) - 1
    row = feats.iloc[i]
    r = last_regime(reg)
    atr = None if pd.isna(row.get("atr", float("nan"))) else float(row["atr"])
    return LastBar(
        features=row,
        regime=str(r["regime"]),
        high_vol=bool(r["high_vol"]),
        adx=r.get("adx"),
        close=float(bars["close"].iloc[i]),
        atr=atr,
        index=i,
        time=bars.index[i],
    )


def uncalibrated_prior() -> tuple[float, dict]:
    """Until a calibrator is fit on exported trades, emit a 0.5 prior."""
    return 0.5, {"confidence_is_calibrated": False}


def feature_frames(bars: pd.DataFrame, feature_kwargs: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute causal features and the regime frame once for a truncated series."""
    feats = compute_features(bars, **(feature_kwargs or {}))
    return feats, regime_from_features(feats)


def context_at_index(
    bars: pd.DataFrame,
    feats: pd.DataFrame,
    reg: pd.DataFrame,
    i: int,
) -> LastBar | None:
    """Row-level LastBar from precomputed frames (same fields as last_bar_context)."""
    if bars is None or i < 0 or i >= len(bars):
        return None
    if "is_stale" in feats.columns and bool(feats["is_stale"].iloc[i]):
        return None
    row = feats.iloc[i]
    adx = reg["adx"].iloc[i] if "adx" in reg.columns else float("nan")
    atr = row["atr"] if "atr" in row.index else float("nan")
    return LastBar(
        features=row,
        regime=str(reg["regime"].iloc[i]),
        high_vol=bool(reg["high_vol"].iloc[i]),
        adx=None if pd.isna(adx) else float(adx),
        close=float(bars["close"].iloc[i]),
        atr=None if pd.isna(atr) else float(atr),
        index=i,
        time=bars.index[i],
    )

