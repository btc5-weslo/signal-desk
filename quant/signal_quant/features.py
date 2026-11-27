"""Causal, vectorized technical features. No lookahead.

Every function uses only the current bar and bars before it (pandas rolling /
ewm with the window ending at the current index; never center=True, never shift
(-n), never full-sample normalization).

A unit test mutates future bars and asserts that past feature values are
unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signal_quant.bars import ensure_utc_index, infer_timeframe
from signal_quant.masks import gap_segments, is_stale


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def ema(close: pd.Series, window: int) -> pd.Series:
    return close.ewm(span=window, adjust=False, min_periods=window).mean()


def returns(close: pd.Series, window: int = 1) -> pd.Series:
    return close.pct_change(window)


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    a = high - low
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def _wilder_smooth(series: pd.Series, window: int) -> pd.Series:
    """Wilder / RMA smoothing (causal)."""
    return series.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    return _wilder_smooth(true_range(high, low, close), window)


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = _wilder_smooth(gain, window)
    avg_loss = _wilder_smooth(loss, window)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    hist = line - sig
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": hist})


def bollinger(close: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, window)
    std = close.rolling(window, min_periods=window).std(ddof=0)
    upper = mid + n_std * std
    lower = mid - n_std * std
    width = (upper - lower) / mid.replace(0.0, np.nan)
    pct_b = (close - lower) / (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame(
        {"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width, "bb_pct_b": pct_b}
    )


def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)
    atr_ = atr(high, low, close, window)
    plus_di = 100.0 * _wilder_smooth(plus_dm, window) / atr_.replace(0.0, np.nan)
    minus_di = 100.0 * _wilder_smooth(minus_dm, window) / atr_.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_ = _wilder_smooth(dx, window)
    return pd.DataFrame({"adx": adx_, "plus_di": plus_di, "minus_di": minus_di})


def realized_vol(close: pd.Series, window: int = 20, periods_per_year: int | None = None) -> pd.Series:
    log_ret = np.log(close / close.shift(1))
    vol = log_ret.rolling(window, min_periods=window).std(ddof=0)
    if periods_per_year:
        vol = vol * np.sqrt(periods_per_year)
    return vol


def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    return volume / sma(volume, window).replace(0.0, np.nan)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


def donchian(
    high: pd.Series,
    low: pd.Series,
    window: int = 20,
    *,
    exclude_current: bool = True,
) -> pd.DataFrame:
    """Donchian channel.

    ``exclude_current=True`` (default) uses the prior ``window`` bars so a
    breakout is measured against already-closed bars, not the bar that may be
    making the new high/low.
    """
    hh = high.rolling(window, min_periods=window).max()
    ll = low.rolling(window, min_periods=window).min()
    if exclude_current:
        hh = hh.shift(1)
        ll = ll.shift(1)
    mid = (hh + ll) / 2.0
    return pd.DataFrame({"donchian_high": hh, "donchian_low": ll, "donchian_mid": mid})


def swing_points(high: pd.Series, low: pd.Series, left: int = 3, right: int = 0) -> pd.DataFrame:
    """Causal swing high/low using only ``left`` bars before the current bar.

    ``right`` must be 0. A positive right window would look ahead and is rejected.
    """
    if right != 0:
        raise ValueError("swing_points is causal: right must be 0 (no future confirmation)")
    swing_high = high.rolling(left, min_periods=left).max().shift(1)
    swing_low = low.rolling(left, min_periods=left).min().shift(1)
    return pd.DataFrame({"swing_high": swing_high, "swing_low": swing_low})


def _compute_raw(
    bars: pd.DataFrame,
    *,
    ema_fast: int = 12,
    ema_slow: int = 48,
    rsi_window: int = 14,
    atr_window: int = 14,
    adx_window: int = 14,
    bb_window: int = 20,
    vol_window: int = 20,
    donchian_window: int = 20,
    volume_window: int = 20,
) -> pd.DataFrame:
    """Causal features on a contiguous, already-cleaned (no stale) segment."""
    close, high, low, volume = bars["close"], bars["high"], bars["low"], bars["volume"]
    parts = [
        pd.DataFrame(
            {
                "sma_fast": sma(close, ema_fast),
                "sma_slow": sma(close, ema_slow),
                "ema_fast": ema(close, ema_fast),
                "ema_slow": ema(close, ema_slow),
                "ret_1": returns(close, 1),
                "rsi": rsi(close, rsi_window),
                "atr": atr(high, low, close, atr_window),
                "realized_vol": realized_vol(close, vol_window),
                "volume_ratio": volume_ratio(volume, volume_window),
                "obv": obv(close, volume),
            }
        ),
        macd(close),
        bollinger(close, bb_window),
        adx(high, low, close, adx_window),
        donchian(high, low, donchian_window, exclude_current=True),
        swing_points(high, low, left=3, right=0),
    ]
    out = pd.concat(parts, axis=1)
    out["ema_fast_above_slow"] = (out["ema_fast"] > out["ema_slow"]).astype("float")
    out["trend_dir"] = np.sign(out["ema_fast"] - out["ema_slow"])
    return out


def _segment_ids(bars: pd.DataFrame, timeframe: str) -> tuple[pd.Series, pd.Series]:
    """Return (segment_id, stale_mask) aligned to ``bars``.

    Segment bounds come from official ``gap_segments``: each item is a
    contiguous run of real bars (``GapSegment.start`` / ``.end`` are
    ``open_time``). A run of more than 3 stale or missing bars starts a new
    segment — the same split whether those stale rows were dropped or not.
    Stale bars that sit *inside* a segment (short hole) keep the segment id
    so indicator state can be forward-filled through them. Bars in a long
    gap (id -1) do not carry state across the break.
    """
    stale = is_stale(bars).reindex(bars.index).fillna(False).astype(bool)
    if "open_time" in bars.columns:
        ot = pd.to_datetime(bars["open_time"], utc=True)
    elif "close_time" in bars.columns:
        ot = pd.to_datetime(bars["close_time"], utc=True)
    else:
        ot = pd.Series(pd.to_datetime(bars.index, utc=True), index=bars.index)
    ids = np.full(len(bars), -1, dtype=int)
    segs = gap_segments(bars, timeframe) or []
    for i, seg in enumerate(segs):
        start = pd.Timestamp(seg.start)
        end = pd.Timestamp(seg.end)
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        else:
            start = start.tz_convert("UTC")
        if end.tzinfo is None:
            end = end.tz_localize("UTC")
        else:
            end = end.tz_convert("UTC")
        in_seg = (ot >= start) & (ot <= end)
        ids[np.asarray(in_seg)] = i
    return pd.Series(ids, index=bars.index, name="segment"), stale


def compute_features(
    df: pd.DataFrame,
    *,
    ema_fast: int = 12,
    ema_slow: int = 48,
    rsi_window: int = 14,
    atr_window: int = 14,
    adx_window: int = 14,
    bb_window: int = 20,
    vol_window: int = 20,
    donchian_window: int = 20,
    volume_window: int = 20,
    timeframe: str | None = None,
) -> pd.DataFrame:
    """Build a causal feature frame aligned to ``df`` (same index).

    Stale / placeholder bars (via ``is_stale``) are excluded from ATR, vol,
    RSI, Bollinger, and volume (and every other feature here). Indicator
    state is forward-filled through those holes rather than treating them as
    zero-range / zero-volume observations. After a gap longer than 3 bars
    (``gap_segments``), indicators reset and must warm up again.
    """
    bars = ensure_utc_index(df)
    tf = timeframe
    if tf is None and len(bars) >= 2:
        try:
            tf = infer_timeframe(bars)
        except ValueError:
            tf = None
    kwargs = dict(
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi_window=rsi_window,
        atr_window=atr_window,
        adx_window=adx_window,
        bb_window=bb_window,
        vol_window=vol_window,
        donchian_window=donchian_window,
        volume_window=volume_window,
    )
    if tf is None:
        stale = is_stale(bars).reindex(bars.index).fillna(False).astype(bool)
        valid = bars.loc[~stale]
        if valid.empty:
            out = pd.DataFrame(index=bars.index)
        else:
            out = _compute_raw(valid, **kwargs).reindex(bars.index).ffill()
        out["is_stale"] = stale
        return out

    seg_ids, stale = _segment_ids(bars, tf)
    parts: list[pd.DataFrame] = []
    for sid, chunk in bars.groupby(seg_ids, sort=False):
        if int(sid) < 0:
            # Long-gap hole: no indicator state, no forward-fill across the break.
            parts.append(pd.DataFrame(index=chunk.index))
            continue
        mask = stale.loc[chunk.index]
        valid = chunk.loc[~mask]
        if valid.empty:
            feat = pd.DataFrame(index=chunk.index)
        else:
            feat = _compute_raw(valid, **kwargs).reindex(chunk.index).ffill()
        parts.append(feat)
    out = pd.concat(parts).reindex(bars.index)
    out["is_stale"] = stale
    return out
