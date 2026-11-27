"""Clean OHLCV series: UTC, sort, dedupe, drop bad ticks, flag outliers and gaps.

Never fabricates replacement prices. Impossible ticks (non-positive prices,
high < low, high < max(open, close), low > min(open, close)) are dropped and
listed in the quality report. Statistical outliers are kept and flagged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from signal_data.schema import DataQualityReport, GapRecord
from signal_data.alignment import drop_off_grid
from signal_data.stale import STALE_RUN_GAP_BARS, missing_bars_between, stale_mask, stale_run_lengths
from signal_data.timeutil import now_utc, to_utc, TF_DELTA

OUTLIER_ABS_RET = {
    "15m": 0.25,
    "1h": 0.35,
    "4h": 0.45,
    "1d": 0.60,
}
OUTLIER_SIGMA = 8.0


def _as_utc_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True)


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    colmap = {c.lower(): c for c in out.columns}
    # accept aliases
    aliases = {
        "open_time": ["open_time", "time", "timestamp", "datetime", "date"],
        "close_time": ["close_time"],
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "c"],
        "volume": ["volume", "vol", "v"],
        "source": ["source"],
    }
    rename = {}
    lower = {c.lower(): c for c in out.columns}
    for canon, names in aliases.items():
        if canon in out.columns:
            continue
        for n in names:
            if n in lower:
                rename[lower[n]] = canon
                break
    if rename:
        out = out.rename(columns=rename)
    if "open_time" not in out.columns:
        raise ValueError("OHLCV frame needs an open_time (or time/timestamp) column")
    out["open_time"] = _as_utc_series(out["open_time"])
    if "close_time" in out.columns:
        out["close_time"] = _as_utc_series(out["close_time"])
    for c in ("open", "high", "low", "close", "volume"):
        if c not in out.columns:
            if c == "volume":
                out[c] = 0.0
            else:
                raise ValueError(f"missing column {c}")
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "source" not in out.columns:
        out["source"] = ""
    out["source"] = out["source"].astype(str)
    return out


def _impossible_tick(row: pd.Series) -> bool:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if not np.isfinite([o, h, l, c]).all():
        return True
    if min(o, h, l, c) <= 0:
        return True
    if h < l:
        return True
    if h < max(o, c) or l > min(o, c):
        return True
    return False


def _expected_delta(timeframe: str) -> timedelta:
    return TF_DELTA[timeframe]


def _is_calendar_gap(asset_class: str, timeframe: str, prev_close: pd.Timestamp, next_open: pd.Timestamp) -> bool:
    """Weekends (and Fri close -> Mon open) are expected for equities; FX weekends too.

    Crypto trades 24/7 so any gap longer than 1.5x the bar is unexpected.
    """
    if asset_class == "crypto":
        return False
    gap = next_open - prev_close
    # session close Friday to Monday open is a calendar gap
    if prev_close.dayofweek >= 4 and next_open.dayofweek <= 1 and gap <= timedelta(days=4, hours=12):
        return True
    # daily equity/FX: 3-day holiday weekends still calendar-ish if < 5 days
    if timeframe == "1d" and timedelta(days=1) < gap <= timedelta(days=5):
        return True
    return False


def clean_ohlcv(
    df: pd.DataFrame,
    *,
    symbol: str,
    asset_class: str,
    timeframe: str,
    source: str | None = None,
    as_of: datetime | pd.Timestamp | None = None,
    history_limitations: list[str] | None = None,
    fetch_attempts=None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> tuple[pd.DataFrame, DataQualityReport]:
    warnings = list(warnings or [])
    errors = list(errors or [])
    attempts = list(fetch_attempts or [])
    limitations = list(history_limitations or [])

    if df is None or df.empty:
        report = DataQualityReport(
            symbol=symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            source=source,
            history_limitations=limitations,
            fetch_attempts=attempts,
            warnings=warnings,
            errors=errors or ["no bars returned"],
            cleaned_at=now_utc().to_pydatetime(),
        )
        empty = pd.DataFrame(
            columns=["open_time", "close_time", "open", "high", "low", "close", "volume", "source", "is_stale"]
        )
        return empty, report

    out = normalize_ohlcv(df)
    if "close_time" not in out.columns or out["close_time"].isna().any():
        from signal_data.timeutil import close_time_from_open, equity_session_times

        closes = []
        for ot in out["open_time"]:
            if asset_class == "equity" and timeframe == "1d":
                _, ct = equity_session_times(ot, "1d")
                closes.append(ct)
            else:
                closes.append(close_time_from_open(ot, timeframe))
        out["close_time"] = closes
        out["close_time"] = _as_utc_series(out["close_time"])

    # Drop forming bars
    cut = to_utc(as_of) if as_of is not None else now_utc()
    forming = out["close_time"] > cut
    n_forming = int(forming.sum())
    out = out.loc[~forming].copy()

    n_dup = int(out["open_time"].duplicated().sum())
    out = out.sort_values("open_time")
    out = out.drop_duplicates(subset=["open_time"], keep="last")

    bad_mask = out.apply(_impossible_tick, axis=1)
    bad_times = [t.to_pydatetime() for t in out.loc[bad_mask, "open_time"]]
    out = out.loc[~bad_mask].copy()

    # volume NaN -> 0
    out["volume"] = out["volume"].fillna(0.0)

    # Off-grid open_times (e.g. Feb 2018 Binance outage restarts at 09:28:14)
    # are dropped, never snapped. They count as missing for gap detection.
    out, off_grid_times = drop_off_grid(out, timeframe, asset_class)
    n_off_grid = len(off_grid_times)

    # Stale bars (volume == 0 and o == h == l == c) are not real quotes.
    # They stay in the raw store with is_stale=True; readers drop them by default.
    stale = stale_mask(out) if not out.empty else pd.Series(dtype=bool)
    n_stale = int(stale.sum()) if len(stale) else 0
    stale_times = [t.to_pydatetime() for t in out.loc[stale, "open_time"]] if n_stale else []
    stale_runs = stale_run_lengths(out, timeframe) if not out.empty else []
    n_stale_runs_gt_3 = int(sum(1 for n in stale_runs if n > STALE_RUN_GAP_BARS))
    # Raw store keeps stale bars, flagged. get_candles / load_closed drop them
    # by default; gap_segments still treats them as missing so holes are visible.
    if len(out):
        out = out.copy()
        out["is_stale"] = stale.astype(bool).values

    n_zero_vol = (
        int(((out["volume"] <= 0) & ~out["is_stale"].astype(bool)).sum())
        if (not out.empty and "is_stale" in out.columns)
        else (int((out["volume"] <= 0).sum()) if not out.empty else 0)
    )

    # outliers: extreme close-to-close returns (keep, flag)
    outlier_times: list[datetime] = []
    if len(out) >= 3:
        ret = out["close"].pct_change()
        abs_cap = OUTLIER_ABS_RET.get(timeframe, 0.60)
        hard = ret.abs() >= abs_cap
        # robust z-score on returns, ignore the first NaN
        med = ret.median()
        mad = (ret - med).abs().median()
        if mad and mad > 0:
            z = (ret - med).abs() / (1.4826 * mad)
            sig = z >= OUTLIER_SIGMA
        else:
            sig = pd.Series(False, index=out.index)
        flag = (hard | sig) & ret.notna()
        outlier_times = [t.to_pydatetime() for t in out.loc[flag, "open_time"]]

    # gap detection — treat stale bars as missing so they cannot hide a hole
    gaps: list[GapRecord] = []
    n_cal = 0
    n_unexp = 0
    n_gt_3x = 0
    real = out.loc[~out["is_stale"].astype(bool)].copy() if (len(out) and "is_stale" in out.columns) else out
    if len(real) >= 2:
        delta = _expected_delta(timeframe)
        opens = list(real["open_time"])
        closes = list(real["close_time"])
        for i in range(1, len(opens)):
            prev_open = opens[i - 1]
            prev_close = closes[i - 1]
            cur_open = opens[i]
            missing = missing_bars_between(prev_open, cur_open, timeframe)
            if missing <= 0:
                continue
            spacing = cur_open - prev_open
            if missing > STALE_RUN_GAP_BARS:
                kind = "gt_3x_interval"
                n_gt_3x += 1
            elif _is_calendar_gap(asset_class, timeframe, prev_close, cur_open):
                kind = "weekend_or_holiday"
                n_cal += 1
            else:
                kind = "unexpected"
                n_unexp += 1
            gaps.append(
                GapRecord(
                    start=prev_close.to_pydatetime(),
                    end=cur_open.to_pydatetime(),
                    missing_bars_estimate=missing,
                    kind=kind,
                )
            )

    n = len(out)
    span_missing = 0.0
    if n >= 2:
        span = out["open_time"].iloc[-1] - out["open_time"].iloc[0]
        expected = max(int(span / _expected_delta(timeframe)) + 1, n)
        # equities daily: weekdays only rough estimate
        if asset_class != "crypto" and timeframe == "1d":
            expected = int(np.busday_count(out["open_time"].iloc[0].date(), (out["open_time"].iloc[-1] + timedelta(days=1)).date()))
        if expected > 0:
            span_missing = max(0.0, 1.0 - n / expected)

    if n_forming:
        warnings.append(f"dropped {n_forming} still-forming bar(s) (close_time > as_of)")
    if n_dup:
        warnings.append(f"removed {n_dup} duplicate open_time row(s)")
    if bad_times:
        warnings.append(f"dropped {len(bad_times)} impossible tick(s)")
    if outlier_times:
        warnings.append(f"flagged {len(outlier_times)} statistical outlier bar(s); prices kept as published")
    if n_stale:
        warnings.append(
            f"kept {n_stale} stale bar(s) in the raw store with is_stale=True "
            "(volume==0 and open==high==low==close); get_candles/load_closed drop them by default"
        )
    if n_stale_runs_gt_3:
        warnings.append(
            f"detected {n_stale_runs_gt_3} stale/missing run(s) longer than {STALE_RUN_GAP_BARS} bars "
            "(sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)"
        )
    if n_off_grid:
        warnings.append(
            f"dropped {n_off_grid} off-grid bar(s) whose open_time was not on the {timeframe} boundary "
            "(not snapped; counted as missing; sets data_quality_warning when the hole is longer than 3 bars)"
        )
    if n_unexp:
        warnings.append(f"detected {n_unexp} unexpected gap(s)")
    if n_gt_3x:
        warnings.append(
            f"detected {n_gt_3x} gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)"
        )

    start = out["open_time"].iloc[0].to_pydatetime() if n else None
    end = out["close_time"].iloc[-1].to_pydatetime() if n else None
    used_source = source or (str(out["source"].mode().iloc[0]) if n and len(out["source"].mode()) else None)

    # cap long timestamp lists in the report
    def _cap(ts, limit=50):
        return ts[:limit]

    report = DataQualityReport(
        symbol=symbol,
        asset_class=asset_class,
        timeframe=timeframe,
        source=used_source,
        start=start,
        end=end,
        n_bars=n,
        n_duplicates_removed=n_dup,
        n_bad_ticks_dropped=len(bad_times),
        n_outliers_flagged=len(outlier_times),
        n_zero_volume=n_zero_vol,
        n_stale_bars=n_stale,
        n_stale_runs_gt_3=n_stale_runs_gt_3,
        n_off_grid_dropped=n_off_grid,
        off_grid_times=_cap(off_grid_times),
        n_gaps_unexpected=n_unexp,
        n_gaps_calendar=n_cal,
        n_gaps_gt_3x=n_gt_3x,
        missing_pct_estimate=float(span_missing),
        history_limitations=limitations,
        bad_tick_times=_cap(bad_times),
        outlier_times=_cap(outlier_times),
        stale_times=_cap(stale_times),
        gaps=gaps[:100],
        fetch_attempts=attempts,
        warnings=warnings,
        errors=errors,
        dropped_forming_bars=n_forming,
        cleaned_at=now_utc().to_pydatetime(),
    )

    cols = ["open_time", "close_time", "open", "high", "low", "close", "volume", "source", "is_stale"]
    if "is_stale" not in out.columns:
        out["is_stale"] = False
    if used_source:
        out.loc[out["source"].isin(["", "nan", "None"]), "source"] = used_source
    out = out[cols].sort_values("open_time").reset_index(drop=True)
    return out, report
