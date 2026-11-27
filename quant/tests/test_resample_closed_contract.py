"""Contract tests for ``resample_closed`` (owned by the data package).

These cases describe the locked session-aware 4h rules so the Data Engineer
can implement ``signal_data.resample_closed`` against them.

- Crypto tests also run against Quant's temporary UTC full-count fallback.
- Equity / FX session and weekend tests SKIP until ``signal_data.resample_closed``
  is published (Quant must not invent that logic).
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from signal_quant.bars import import_data_resample_closed, resample_closed

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _has_data_resample() -> bool:
    return import_data_resample_closed() is not None


def _hourly(
    opens: list[pd.Timestamp],
    *,
    start_price: float = 100.0,
    session_close: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Build 1h OHLCV bars from a list of open times.

    Close defaults to open + 1h, but is capped at ``session_close`` so an
    equity 15:30 ET bar ends at 16:00 ET (not 16:30), which is what
    ``signal_data.resample_closed`` expects for the afternoon bucket.
    """
    rows = []
    px = start_price
    cap = None
    if session_close is not None:
        cap = pd.Timestamp(session_close)
        if cap.tzinfo is None:
            cap = cap.tz_localize("UTC")
        else:
            cap = cap.tz_convert("UTC")
    for i, open_t in enumerate(opens):
        open_t = pd.Timestamp(open_t)
        if open_t.tzinfo is None:
            open_t = open_t.tz_localize("UTC")
        else:
            open_t = open_t.tz_convert("UTC")
        close_t = open_t + pd.Timedelta(hours=1)
        if cap is not None and close_t > cap:
            close_t = cap
        o, c = px, px + 0.5
        rows.append(
            {
                "open_time": open_t,
                "close_time": close_t,
                "open": o,
                "high": max(o, c) + 0.1,
                "low": min(o, c) - 0.1,
                "close": c,
                "volume": 1.0 + i,
            }
        )
        px = c
    df = pd.DataFrame(rows)
    return df


def _equity_session_hourly(session_date: str) -> list[pd.Timestamp]:
    """Regular-session 1h opens in ET: 09:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30."""
    d = pd.Timestamp(session_date).tz_localize(ET)
    minutes = [(9, 30), (10, 30), (11, 30), (12, 30), (13, 30), (14, 30), (15, 30)]
    return [
        pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=h, minute=m, tz=ET)
        for h, m in minutes
    ]


def _equity_session_close(session_date: str) -> pd.Timestamp:
    d = pd.Timestamp(session_date).tz_localize(ET)
    return pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=16, minute=0, tz=ET)


# --- Crypto (runs against the fallback or signal_data) ---


def test_crypto_4h_complete_only_with_all_four_hourly_bars():
    """UTC-aligned 4h block 00:00-04:00 is complete iff all 4 hourly bars exist."""
    opens = [pd.Timestamp("2024-01-03 00:00", tz="UTC") + pd.Timedelta(hours=i) for i in range(4)]
    as_of = pd.Timestamp("2024-01-03 04:00", tz="UTC")
    full = _hourly(opens)
    out = resample_closed(full, "4h", as_of, asset_class="crypto")
    assert len(out) == 1
    close = pd.Timestamp(out["close_time"].iloc[0] if "close_time" in out.columns else out.index[0])
    close = close.tz_convert("UTC") if close.tzinfo else close.tz_localize("UTC")
    assert close == as_of

    missing_last = _hourly(opens[:3])
    out_partial = resample_closed(missing_last, "4h", as_of, asset_class="crypto")
    assert len(out_partial) == 0


def test_crypto_4h_as_of_before_close_excludes_bucket():
    opens = [pd.Timestamp("2024-01-03 00:00", tz="UTC") + pd.Timedelta(hours=i) for i in range(4)]
    mid = pd.Timestamp("2024-01-03 03:00", tz="UTC")
    out = resample_closed(_hourly(opens), "4h", mid, asset_class="crypto")
    assert len(out) == 0


# --- Equity / FX: skip until the data package exports resample_closed ---

requires_data = pytest.mark.skipif(
    not _has_data_resample(),
    reason="signal_data.resample_closed is not published yet",
)


@requires_data
def test_equity_4h_anchors_to_0930_et_morning_and_afternoon():
    """09:30-13:30 ET (4 hourly bars) and 13:30-16:00 ET (shorter afternoon).

    Afternoon is marked ``partial_session=True`` and is complete only when all
    of its expected hourly bars (13:30, 14:30, 15:30 ET) are present.
    Morning is not a partial session.
    """
    opens = _equity_session_hourly("2024-06-03")  # EDT
    session_close = _equity_session_close("2024-06-03")
    as_of = session_close.tz_convert("UTC")
    out = resample_closed(_hourly(opens, session_close=session_close), "4h", as_of, asset_class="equity")
    assert len(out) == 2
    out = out.sort_values("close_time") if "close_time" in out.columns else out.sort_index()
    closes = [
        pd.Timestamp(t).tz_convert(ET)
        for t in (out["close_time"] if "close_time" in out.columns else out.index)
    ]
    assert closes[0] == pd.Timestamp("2024-06-03 13:30", tz=ET)
    assert closes[1] == pd.Timestamp("2024-06-03 16:00", tz=ET)
    # Data documents the shorter afternoon bucket with expected_bars (3 hourly
    # bars, not 4). A ``partial_session`` column is also accepted if present.
    if "expected_bars" in out.columns:
        exp = [int(x) for x in out["expected_bars"]]
        assert exp[0] == 4
        assert exp[1] == 3
    if "partial_session" in out.columns:
        flags = list(out["partial_session"])
        assert flags[0] in (False, 0)
        assert flags[1] in (True, 1)
    assert "expected_bars" in out.columns or "partial_session" in out.columns


@requires_data
def test_equity_afternoon_dropped_if_an_expected_hourly_bar_is_missing():
    opens = _equity_session_hourly("2024-06-03")
    # Drop the 14:30 ET hour (an expected afternoon bar).
    opens = [t for t in opens if not (t.hour == 14 and t.minute == 30)]
    session_close = _equity_session_close("2024-06-03")
    as_of = session_close.tz_convert("UTC")
    out = resample_closed(_hourly(opens, session_close=session_close), "4h", as_of, asset_class="equity")
    closes = [
        pd.Timestamp(t).tz_convert(ET)
        for t in (out["close_time"] if "close_time" in out.columns else out.index)
    ]
    assert pd.Timestamp("2024-06-03 13:30", tz=ET) in closes
    assert pd.Timestamp("2024-06-03 16:00", tz=ET) not in closes


@requires_data
def test_equity_4h_bar_never_spans_two_calendar_days():
    """No 4h bucket may open on one ET session date and close on the next."""
    opens = _equity_session_hourly("2024-06-03")
    session_close = _equity_session_close("2024-06-03")
    as_of = session_close.tz_convert("UTC")
    out = resample_closed(_hourly(opens, session_close=session_close), "4h", as_of, asset_class="equity")
    for _, row in out.iterrows():
        close = pd.Timestamp(row["close_time"] if "close_time" in out.columns else out.loc[_.name].name)
        close = close.tz_convert(ET) if close.tzinfo else close.tz_localize("UTC").tz_convert(ET)
        if "open_time" in out.columns:
            open_t = pd.Timestamp(row["open_time"])
            open_t = open_t.tz_convert(ET) if open_t.tzinfo else open_t.tz_localize("UTC").tz_convert(ET)
            assert open_t.date() == close.date()
        assert close.date() == pd.Timestamp("2024-06-03", tz=ET).date()


@requires_data
def test_fx_drops_bucket_that_crosses_weekend_close():
    """A 4h UTC bucket that crosses Friday 17:00 America/New_York is dropped.

    In June (EDT) Friday 17:00 ET = 21:00 UTC, so the 20:00-00:00 UTC bucket
    crosses the weekend close and must not appear, even if four hourly bars
    are present.
    """
    # Friday 2024-06-07 20:00, 21:00, 22:00, 23:00 UTC opens.
    friday = pd.Timestamp("2024-06-07 20:00", tz="UTC")
    opens = [friday + pd.Timedelta(hours=i) for i in range(4)]
    as_of = pd.Timestamp("2024-06-08 00:00", tz="UTC")
    out = resample_closed(_hourly(opens), "4h", as_of, asset_class="fx")
    assert len(out) == 0


@requires_data
def test_fx_keeps_complete_midweek_utc_4h_and_drops_missing_hours():
    """Mid-week UTC 4h (08:00-12:00 Wednesday) is kept iff all 4 hourly bars exist."""
    start = pd.Timestamp("2024-06-05 08:00", tz="UTC")  # Wednesday
    opens = [start + pd.Timedelta(hours=i) for i in range(4)]
    as_of = pd.Timestamp("2024-06-05 12:00", tz="UTC")
    full = resample_closed(_hourly(opens), "4h", as_of, asset_class="fx")
    assert len(full) == 1
    partial = resample_closed(_hourly(opens[:3]), "4h", as_of, asset_class="fx")
    assert len(partial) == 0


def test_equity_fx_4h_raises_until_data_package_owns_it():
    """Quant must not silently emit a UTC 4h equity/FX bucket while waiting on Data."""
    if _has_data_resample():
        pytest.skip("signal_data.resample_closed is published; session tests cover it")
    opens = _equity_session_hourly("2024-06-03")
    session_close = _equity_session_close("2024-06-03")
    as_of = session_close.tz_convert("UTC")
    with pytest.raises(NotImplementedError, match="signal_data.resample_closed"):
        resample_closed(_hourly(opens, session_close=session_close), "4h", as_of, asset_class="equity")
    friday = pd.Timestamp("2024-06-07 20:00", tz="UTC")
    fx_opens = [friday + pd.Timedelta(hours=i) for i in range(4)]
    with pytest.raises(NotImplementedError, match="signal_data.resample_closed"):
        resample_closed(_hourly(fx_opens), "4h", pd.Timestamp("2024-06-08 00:00", tz="UTC"), asset_class="fx")
