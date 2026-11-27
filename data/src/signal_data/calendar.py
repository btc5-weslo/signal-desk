"""Session calendars for gap detection.

Equities use the NYSE regular session (09:30–16:00 America/New_York, early
close 13:00 on documented days). A closed market — overnight, weekend, or
full/early holiday close — is not a missing-bar gap and must not set
``data_quality_warning``.

FX uses the existing resample convention: Friday 22:00 UTC through Sunday
22:00 UTC is the weekend close. Mid-week holes still count as gaps.
Crypto is 24/7 and is unchanged (no calendar closures).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from signal_data.timeutil import ET, to_utc

# Match signal_data.resample: Fri 22:00 UTC – Sun 22:00 UTC.
FX_WEEKEND_START_DOW = 4
FX_WEEKEND_START_HOUR = 22
FX_WEEKEND_HOURS = 48

_TF_DELTA = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> date:
    """Shift Sat→Fri, Sun→Mon (NYSE observance)."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: Mon=0 … Sun=6. n is 1-based; n=-1 is the last such weekday."""
    if n > 0:
        first = date(year, month, 1)
        shift = (weekday - first.weekday()) % 7
        return first + timedelta(days=shift + 7 * (n - 1))
    # last
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    shift = (last.weekday() - weekday) % 7
    return last - timedelta(days=shift)


def nyse_holidays(year: int) -> set[date]:
    """Full NYSE market-closed days (observed) for one year."""
    hols = {
        _observed(date(year, 1, 1)),  # New Year's
        _nth_weekday(year, 1, 0, 3),  # MLK
        _nth_weekday(year, 2, 0, 3),  # Presidents
        easter_sunday(year) - timedelta(days=2),  # Good Friday
        _nth_weekday(year, 5, 0, -1),  # Memorial
        _observed(date(year, 7, 4)),  # Independence
        _nth_weekday(year, 9, 0, 1),  # Labor
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),  # Christmas
    }
    if year >= 2021:
        hols.add(_observed(date(year, 6, 19)))  # Juneteenth
    # New Year's observed from next year can land on Dec 31 of this year.
    nxt = _observed(date(year + 1, 1, 1))
    if nxt.year == year:
        hols.add(nxt)
    return hols


def is_nyse_holiday(d: date) -> bool:
    return d in nyse_holidays(d.year)


def is_nyse_session_day(d: date) -> bool:
    return d.weekday() < 5 and not is_nyse_holiday(d)


def nyse_early_close_time(d: date):
    """Return (hour, minute) ET of the session close if this is an early-close day, else None.

    Regular close is 16:00. Early close is 13:00 ET on the usual NYSE days
    (day after Thanksgiving; July 3 when July 4 is a weekday; Christmas Eve
    and New Year's Eve when they are session days).
    """
    if not is_nyse_session_day(d):
        return None
    # Day after Thanksgiving
    thanks = _nth_weekday(d.year, 11, 3, 4)
    if d == thanks + timedelta(days=1):
        return (13, 0)
    # July 3 when Independence Day is a weekday (Thu/Fri observed patterns)
    if d.month == 7 and d.day == 3 and date(d.year, 7, 4).weekday() < 5:
        return (13, 0)
    # Christmas Eve / New Year's Eve, if the market is open
    if d.month == 12 and d.day == 24:
        return (13, 0)
    if d.month == 12 and d.day == 31:
        return (13, 0)
    return None


def _et(ts) -> pd.Timestamp:
    t = to_utc(ts)
    return t.tz_convert(ET)


def _et_clock(d: date, hour: int, minute: int) -> pd.Timestamp:
    return pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=hour, minute=minute, tz=ET).tz_convert("UTC")


def next_nyse_session_day(d: date) -> date:
    cur = d + timedelta(days=1)
    for _ in range(20):
        if is_nyse_session_day(cur):
            return cur
        cur += timedelta(days=1)
    raise RuntimeError(f"no NYSE session day after {d}")


def is_fx_weekend_instant(ts) -> bool:
    """True if ``ts`` falls in [Fri 22:00 UTC, Sun 22:00 UTC)."""
    t = to_utc(ts)
    # Friday 22:00 of this week or previous
    dow = int(t.dayofweek)  # Mon=0
    # minutes since Monday 00:00
    minutes = dow * 24 * 60 + t.hour * 60 + t.minute + t.second / 60.0
    # Fri 22:00 = 4*24*60 + 22*60 = 6840; Sun 22:00 = 6*24*60 + 22*60 = 9720
    start = FX_WEEKEND_START_DOW * 24 * 60 + FX_WEEKEND_START_HOUR * 60
    end = start + FX_WEEKEND_HOURS * 60
    return start <= minutes < end


def _equity_1h_grid_minutes(sample_minute: int) -> list[int]:
    """Session minute-of-day for 1h opens.

    09:30-aligned grid (common yfinance): 09:30, 10:30, … 15:30.
    Clock-hour grid after the open: 09:30, 10:00, 11:00, … 15:00.
    """
    if sample_minute == 0:
        return [9 * 60 + 30, 10 * 60, 11 * 60, 12 * 60, 13 * 60, 14 * 60, 15 * 60]
    return [9 * 60 + 30 + 60 * i for i in range(7)]  # 09:30..15:30


def _session_close_minutes(d: date) -> int:
    early = nyse_early_close_time(d)
    if early:
        return early[0] * 60 + early[1]
    return 16 * 60


def next_expected_open(ts, timeframe: str, asset_class: str, *, hour_grid_minute: int | None = None) -> pd.Timestamp:
    """The next official session open strictly after ``ts``."""
    t = to_utc(ts)
    if asset_class == "crypto":
        return t + _TF_DELTA[timeframe]
    if asset_class == "equity":
        return _next_equity_open(t, timeframe, hour_grid_minute=hour_grid_minute)
    if asset_class == "fx":
        return _next_fx_open(t, timeframe)
    raise ValueError(f"unknown asset_class {asset_class}")


def _next_equity_open(t: pd.Timestamp, timeframe: str, *, hour_grid_minute: int | None) -> pd.Timestamp:
    et = _et(t)
    d = et.date()
    if timeframe == "1d":
        nxt = next_nyse_session_day(d) if (not is_nyse_session_day(d) or (et.hour, et.minute) >= (9, 30)) else d
        # if t is before 09:30 on a session day, 09:30 today
        if is_nyse_session_day(d) and (et.hour, et.minute) < (9, 30):
            nxt = d
        elif is_nyse_session_day(d) and (et.hour, et.minute) >= (9, 30):
            nxt = next_nyse_session_day(d)
        else:
            nxt = next_nyse_session_day(d) if not is_nyse_session_day(d) else next_nyse_session_day(d)
        return _et_clock(nxt, 9, 30)

    # Intraday
    gm = 30 if hour_grid_minute is None else hour_grid_minute
    # Start search from the clock just after t
    cur_day = d
    # If weekend/holiday, jump to next session 09:30
    if not is_nyse_session_day(cur_day) or (et.hour, et.minute) >= (_session_close_minutes(cur_day) // 60, _session_close_minutes(cur_day) % 60):
        cur_day = next_nyse_session_day(cur_day)
        return _first_intraday_open(cur_day, timeframe, gm)

    close_m = _session_close_minutes(cur_day)
    now_m = et.hour * 60 + et.minute + (1 if (et.second or et.microsecond) else 0)
    # "strictly after t": if t is exactly a bar open, we want the next one
    # Use a second-less minute compare; if t is exactly on a bar, advance.
    candidates = _intraday_opens_minutes(cur_day, timeframe, gm, close_m)
    t_min = et.hour * 60 + et.minute
    t_exact = et.second == 0 and et.microsecond == 0
    for m in candidates:
        if m > t_min or (m == t_min and not t_exact):
            # m == t_min and t not exact means t is before that bar? actually t is inside the minute
            # strictly after: if t is exactly the bar, skip it (t_exact and m==t_min should not fire)
            if m > t_min:
                return _et_clock(cur_day, m // 60, m % 60)
        if m > t_min:
            return _et_clock(cur_day, m // 60, m % 60)
    # none left today
    nxt = next_nyse_session_day(cur_day)
    return _first_intraday_open(nxt, timeframe, gm)


def _first_intraday_open(d: date, timeframe: str, hour_grid_minute: int) -> pd.Timestamp:
    return _et_clock(d, 9, 30)


def _intraday_opens_minutes(d: date, timeframe: str, hour_grid_minute: int, close_m: int) -> list[int]:
    if timeframe == "15m":
        opens = list(range(9 * 60 + 30, close_m, 15))
        return opens
    if timeframe == "1h":
        mins = _equity_1h_grid_minutes(hour_grid_minute)
        return [m for m in mins if m < close_m]
    if timeframe == "4h":
        # 09:30 and 13:30; 13:30 only if the close session exists (close > 13:30)
        out = [9 * 60 + 30]
        if close_m > 13 * 60 + 30:
            out.append(13 * 60 + 30)
        return out
    return []


def _next_fx_open(t: pd.Timestamp, timeframe: str) -> pd.Timestamp:
    step = _TF_DELTA[timeframe]
    if timeframe == "1d":
        # UTC midnight weekdays
        nxt = (t.normalize() + pd.Timedelta(days=1))
        while int(nxt.dayofweek) >= 5 or is_fx_weekend_instant(nxt):
            nxt = nxt + pd.Timedelta(days=1)
        return nxt
    # step along the UTC grid, skipping weekend instants / overlapping 4h buckets
    cand = t + step
    # snap 4h to 00/04/08/12/16/20 if needed
    if timeframe == "4h":
        hour = (t.hour // 4) * 4
        base = t.floor("h").replace(hour=hour, minute=0, second=0, microsecond=0)
        if base <= t:
            cand = base + pd.Timedelta(hours=4)
        else:
            cand = base
    for _ in range(200):
        if timeframe == "4h":
            from signal_data.resample import overlaps_fx_weekend
            if not overlaps_fx_weekend(cand, cand + step) and not is_fx_weekend_instant(cand):
                return cand
        else:
            if not is_fx_weekend_instant(cand):
                return cand
        cand = cand + step
    return cand


def session_missing_bars(
    t0,
    t1,
    timeframe: str,
    asset_class: str,
    *,
    hour_grid_minute: int | None = None,
) -> int:
    """Count expected *session* opens strictly between t0 and t1.

    Weekend, overnight, and holiday closures contribute 0.
    """
    a = to_utc(t0)
    b = to_utc(t1)
    if b <= a:
        return 0
    if asset_class in (None, "crypto"):
        step = _TF_DELTA[timeframe]
        if b - a <= step:
            return 0
        slots = int(round((b - a) / step))
        return max(slots - 1, 0)

    # Infer 1h equity grid from t0 if not given
    gm = hour_grid_minute
    if asset_class == "equity" and timeframe == "1h" and gm is None:
        gm = int(_et(a).minute)

    n = 0
    cur = next_expected_open(a, timeframe, asset_class, hour_grid_minute=gm)
    # safety: don't walk forever
    for _ in range(1_000_000):
        if cur >= b:
            break
        n += 1
        cur = next_expected_open(cur, timeframe, asset_class, hour_grid_minute=gm)
    return n


def infer_asset_class(df: pd.DataFrame, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if df is not None and getattr(df, "attrs", None):
        ac = df.attrs.get("asset_class")
        if ac:
            return str(ac)
    return "crypto"
