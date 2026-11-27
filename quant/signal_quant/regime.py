"""Rule-based market regime labels (v0).

v0 uses ADX (trend vs range) and realized-vol vs its own trailing median
(high-vol vs normal). HMM / clustering are reserved for a later revision and
are not fit here — no regime-accuracy claims are made.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signal_quant.features import adx, realized_vol


def regime_frame(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    adx_window: int = 14,
    adx_trend_min: float = 20.0,
    vol_window: int = 20,
    vol_lookback: int = 100,
    vol_high_mult: float = 1.5,
) -> pd.DataFrame:
    adx_df = adx(high, low, close, adx_window)
    vol = realized_vol(close, vol_window)
    vol_median = vol.rolling(vol_lookback, min_periods=max(20, vol_window)).median()
    high_vol = vol > (vol_median * vol_high_mult)
    trending = adx_df["adx"] >= adx_trend_min
    # Mutual exclusion: high-vol can coexist with trend or range; expose both.
    label = np.where(trending, "trend", "range")
    # If ADX is unavailable (warmup), label is unknown.
    label = np.where(adx_df["adx"].isna(), "unknown", label)
    return pd.DataFrame(
        {
            "regime": label,
            "high_vol": high_vol.fillna(False).astype(bool),
            "adx": adx_df["adx"],
            "plus_di": adx_df["plus_di"],
            "minus_di": adx_df["minus_di"],
            "realized_vol": vol,
        },
        index=close.index,
    )


def last_regime(reg: pd.DataFrame) -> dict:
    if reg.empty:
        return {"regime": "unknown", "high_vol": False}
    # Column-wise .iat avoids a per-call object-row Series (slow with Arrow string labels).
    adx = reg["adx"].iat[-1]
    return {
        "regime": str(reg["regime"].iat[-1]),
        "high_vol": bool(reg["high_vol"].iat[-1]),
        "adx": None if pd.isna(adx) else float(adx),
    }



def regime_from_features(
    feats: pd.DataFrame,
    *,
    adx_trend_min: float = 20.0,
    vol_window: int = 20,
    vol_lookback: int = 100,
    vol_high_mult: float = 1.5,
) -> pd.DataFrame:
    """Build a regime frame from already-masked ``compute_features`` output.

    Uses the feature module's ATR/ADX/vol (stale bars already excluded /
    forward-filled; indicators already reset on long gaps).
    """
    if feats is None or feats.empty:
        return pd.DataFrame(columns=["regime", "high_vol", "adx", "plus_di", "minus_di", "realized_vol"])
    vol = feats["realized_vol"]
    if "is_stale" in feats.columns:
        vol = vol.where(~feats["is_stale"].astype(bool))
    vol_median = vol.rolling(vol_lookback, min_periods=max(20, vol_window)).median()
    high_vol = (vol > (vol_median * vol_high_mult)).fillna(False).astype(bool)
    adx_s = feats["adx"]
    trending = adx_s >= adx_trend_min
    label = np.where(trending, "trend", "range")
    label = np.where(adx_s.isna(), "unknown", label)
    plus = feats["plus_di"] if "plus_di" in feats.columns else pd.Series(np.nan, index=feats.index)
    minus = feats["minus_di"] if "minus_di" in feats.columns else pd.Series(np.nan, index=feats.index)
    return pd.DataFrame(
        {
            "regime": label,
            "high_vol": high_vol,
            "adx": adx_s,
            "plus_di": plus,
            "minus_di": minus,
            "realized_vol": feats["realized_vol"],
        },
        index=feats.index,
    )
