"""4h resample_closed completeness: equity session, FX weekend, missing hourly bar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from signal_data.resample import overlaps_fx_weekend, resample_closed, resample_closed_result

UTC = timezone.utc
ET = ZoneInfo("America/New_York")


def _hourly(opens: list[pd.Timestamp], price0: float = 100.0) -> pd.DataFrame:
    rows = []
    for i, ot in enumerate(opens):
        ot = pd.Timestamp(ot)
        if ot.tzinfo is None:
            ot = ot.tz_localize("UTC")
        else:
            ot = ot.tz_convert("UTC")
        px = price0 + i
        rows.append(
            {
                "open_time": ot,
                "close_time": ot + pd.Timedelta(hours=1),
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px + 0.5,
                "volume": 10.0,
                "source": "toy",
            }
        )
    return pd.DataFrame(rows)


def test_equity_session_two_buckets_short_close_session():
    # A regular Tuesday session: 09:30–16:00 ET, 7 hourly bars.
    # 2024-06-11 is a Tuesday in DST (EDT, UTC-4): 09:30 ET = 13:30 UTC.
    day = datetime(2024, 6, 11, tzinfo=ET)
    opens = [
        pd.Timestamp(year=2024, month=6, day=11, hour=h, minute=30, tz=ET)
        for h in (9, 10, 11, 12, 13, 14, 15)
    ]
    df = _hourly(opens)
    out = resample_closed(df, "4h", asset_class="equity", source_timeframe="1h")
    assert len(out) == 2

    first = out.iloc[0]
    second = out.iloc[1]
    assert first["open_time"] == pd.Timestamp(year=2024, month=6, day=11, hour=9, minute=30, tz=ET).tz_convert("UTC")
    assert first["close_time"] == pd.Timestamp(year=2024, month=6, day=11, hour=13, minute=30, tz=ET).tz_convert("UTC")
    assert int(first["expected_bars"]) == 4  # 09:30, 10:30, 11:30, 12:30

    # Shorter close-session bucket: 13:30–16:00 ET, 2.5 hours, 3 hourly bars.
    assert second["open_time"] == pd.Timestamp(year=2024, month=6, day=11, hour=13, minute=30, tz=ET).tz_convert("UTC")
    assert second["close_time"] == pd.Timestamp(year=2024, month=6, day=11, hour=16, minute=0, tz=ET).tz_convert("UTC")
    assert int(second["expected_bars"]) == 3  # 13:30, 14:30, 15:30 — honest, not 4

    # OHLC of first bucket uses 4 bars; close is the 12:30 bar's close.
    assert first["open"] == pytest.approx(100.0)
    assert first["close"] == pytest.approx(100.0 + 3 + 0.5)

    # Never merge across days: adding the next morning must not create an overnight bucket.
    next_morn = _hourly(
        [pd.Timestamp(year=2024, month=6, day=12, hour=9, minute=30, tz=ET)]
    )
    both = pd.concat([df, next_morn], ignore_index=True)
    out2 = resample_closed(both, "4h", asset_class="equity", source_timeframe="1h")
    # Complete buckets: only the two from Tuesday; Wednesday has a single bar so it is dropped.
    assert len(out2) == 2
    assert out2["open_time"].min() >= pd.Timestamp(year=2024, month=6, day=11, hour=9, minute=30, tz=ET).tz_convert("UTC")
    assert out2["close_time"].max() <= pd.Timestamp(year=2024, month=6, day=11, hour=16, minute=0, tz=ET).tz_convert("UTC")
    overnight = [
        o for o in out2["open_time"]
        if o.tz_convert(ET).date() == datetime(2024, 6, 11).date() and o.tz_convert(ET).hour >= 16
    ]
    assert overnight == []


def test_fx_weekend_buckets_are_dropped():
    # Friday 2024-06-14: UTC hours 16, 17, 18, 19, 20, 21, 22, 23 and Saturday 00...
    # Friday 16:00–20:00 is fully in-session and should be kept if complete.
    # Friday 20:00–00:00 crosses Fri 22:00 close — dropped.
    # Saturday / Sunday buckets dropped.
    # Sunday 20:00–00:00 crosses Sun 22:00 reopen — dropped.
    # Monday 00:00–04:00 kept if complete.
    opens = []
    start = pd.Timestamp("2024-06-14 16:00:00", tz="UTC")  # Friday
    for i in range(16 + 24 + 24 + 8):  # through Monday 08:00
        opens.append(start + pd.Timedelta(hours=i))
    df = _hourly(opens)
    result = resample_closed_result(df, "4h", asset_class="fx", source_timeframe="1h")
    out = result.bars
    kept = list(out["open_time"])
    # Friday 16:00 should be present
    assert pd.Timestamp("2024-06-14 16:00:00", tz="UTC") in kept
    # Crossing and weekend buckets must not appear
    forbidden = [
        "2024-06-14 20:00:00",  # Fri 20:00 crosses 22:00 close
        "2024-06-15 00:00:00",
        "2024-06-15 04:00:00",
        "2024-06-15 08:00:00",
        "2024-06-15 12:00:00",
        "2024-06-15 16:00:00",
        "2024-06-15 20:00:00",
        "2024-06-16 00:00:00",
        "2024-06-16 04:00:00",
        "2024-06-16 08:00:00",
        "2024-06-16 12:00:00",
        "2024-06-16 16:00:00",
        "2024-06-16 20:00:00",  # Sun 20:00 crosses 22:00 reopen
    ]
    for s in forbidden:
        ts = pd.Timestamp(s, tz="UTC")
        assert ts not in kept, f"{s} should be dropped as weekend/cross"
        assert overlaps_fx_weekend(ts, ts + pd.Timedelta(hours=4))
    # Monday 00:00 is after Sun 22:00 reopen
    assert pd.Timestamp("2024-06-17 00:00:00", tz="UTC") in kept
    reasons = {d.open_time: d.reason for d in result.dropped}
    assert reasons[pd.Timestamp("2024-06-14 20:00:00", tz="UTC")] == "fx_weekend_overlap"


def test_missing_hourly_bar_drops_crypto_bucket():
    # UTC 4h bucket 00/04/... : four hours at 00, 01, 02, 03. Drop 02:00.
    base = pd.Timestamp("2024-03-01 00:00:00", tz="UTC")
    opens = [base + pd.Timedelta(hours=h) for h in (0, 1, 3, 4, 5, 6, 7)]  # missing 02:00
    df = _hourly(opens)
    result = resample_closed_result(df, "4h", asset_class="crypto", source_timeframe="1h")
    kept = list(result.bars["open_time"])
    assert pd.Timestamp("2024-03-01 00:00:00", tz="UTC") not in kept
    assert pd.Timestamp("2024-03-01 04:00:00", tz="UTC") in kept
    assert int(result.bars.iloc[0]["expected_bars"]) == 4
    missing = [d for d in result.dropped if d.open_time == base]
    assert len(missing) == 1
    assert missing[0].reason == "missing_source_bars"
    assert missing[0].expected_bars == 4
    assert missing[0].actual_bars == 3


def test_crypto_alignment_is_utc_00_04_08():
    opens = [pd.Timestamp("2024-03-01 00:00:00", tz="UTC") + pd.Timedelta(hours=h) for h in range(12)]
    out = resample_closed(_hourly(opens), "4h", asset_class="crypto", source_timeframe="1h")
    assert list(out["open_time"]) == [
        pd.Timestamp("2024-03-01 00:00:00", tz="UTC"),
        pd.Timestamp("2024-03-01 04:00:00", tz="UTC"),
        pd.Timestamp("2024-03-01 08:00:00", tz="UTC"),
    ]
