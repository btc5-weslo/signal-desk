"""Off-grid open_times are dropped, never snapped, and fail alignment checks."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from signal_data.alignment import (
    OffGridError,
    assert_aligned,
    drop_off_grid,
    is_open_aligned,
    off_grid_mask,
)
from signal_data.cleaning import clean_ohlcv
from signal_data.quality_batch import reports_from_store, write_batch_reports
from signal_data.storage import atomic_write_parquet, mark_source_seams
from tests.toy import make_bars


def test_crypto_grid_boundaries():
    utc = timezone.utc
    assert is_open_aligned(datetime(2018, 2, 8, 0, 0, tzinfo=utc), "1h", "crypto")
    assert not is_open_aligned(datetime(2018, 2, 9, 9, 28, 14, 789000, tzinfo=utc), "1h", "crypto")
    assert is_open_aligned(datetime(2018, 2, 9, 9, 45, tzinfo=utc), "15m", "crypto")
    assert not is_open_aligned(datetime(2018, 2, 9, 9, 58, 14, tzinfo=utc), "15m", "crypto")
    assert is_open_aligned(datetime(2018, 2, 9, 8, 0, tzinfo=utc), "4h", "crypto")
    assert not is_open_aligned(datetime(2018, 2, 9, 9, 0, tzinfo=utc), "4h", "crypto")
    assert is_open_aligned(datetime(2018, 2, 9, 0, 0, tzinfo=utc), "1d", "crypto")
    assert not is_open_aligned(datetime(2018, 2, 9, 1, 0, tzinfo=utc), "1d", "crypto")


def test_drop_off_grid_does_not_snap():
    start = datetime(2018, 2, 9, 8, 0, tzinfo=timezone.utc)
    df = make_bars(start, 4, timeframe="1h")
    # Inject an unaligned outage restart; must be dropped, not snapped to 09:00.
    off = df.iloc[[0]].copy()
    off["open_time"] = pd.Timestamp("2018-02-09 09:28:14.789", tz="UTC")
    off["close_time"] = pd.Timestamp("2018-02-09 10:28:14.789", tz="UTC")
    mixed = pd.concat([df, off], ignore_index=True).sort_values("open_time")
    out, dropped = drop_off_grid(mixed, "1h", "crypto")
    assert len(dropped) == 1
    assert dropped[0] == pd.Timestamp("2018-02-09 09:28:14.789", tz="UTC")
    assert not off_grid_mask(out, "1h", "crypto").any()
    # The 09:00 bar from the original grid is still there; we did not snap 09:28 -> 09:00
    # or invent a replacement.
    opens = list(pd.to_datetime(out["open_time"], utc=True))
    assert pd.Timestamp("2018-02-09 09:00:00", tz="UTC") in opens
    assert pd.Timestamp("2018-02-09 09:28:14.789", tz="UTC") not in opens
    assert len(out) == 4


def test_clean_ohlcv_drops_off_grid_and_records_gap():
    start = datetime(2018, 2, 9, 0, 0, tzinfo=timezone.utc)
    df = make_bars(start, 12, timeframe="1h")
    # Replace bars 2..8 (7 hours) with off-grid times so the hole is > 3 bars.
    off = df.iloc[2:9].copy()
    off["open_time"] = off["open_time"] + pd.Timedelta(minutes=28, milliseconds=14789)
    mixed = pd.concat([df.iloc[:2], off, df.iloc[9:]], ignore_index=True)
    cleaned, report = clean_ohlcv(
        mixed, symbol="BTC-USDT", asset_class="crypto", timeframe="1h", source="binance_vision"
    )
    assert report.n_off_grid_dropped == 7
    assert len(cleaned) == 5
    assert not off_grid_mask(cleaned, "1h", "crypto").any()
    assert any("off-grid" in w.lower() for w in report.warnings)
    # 7 missing hours is longer than 3 bars → gap / quality warning material.
    assert report.n_gaps_gt_3x >= 1 or report.n_gaps_unexpected >= 1 or report.n_stale_runs_gt_3 >= 1


def test_atomic_write_fails_if_off_grid_remain(tmp_path):
    start = datetime(2018, 2, 9, 8, 0, tzinfo=timezone.utc)
    df = make_bars(start, 3, timeframe="1h")
    df.loc[df.index[1], "open_time"] = pd.Timestamp("2018-02-09 09:28:14.789", tz="UTC")
    dest = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    with pytest.raises(OffGridError):
        atomic_write_parquet(df, dest)
    assert not dest.exists()


def test_quality_report_from_store_fails_on_remaining_off_grid(tmp_path):
    start = datetime(2018, 2, 9, 8, 0, tzinfo=timezone.utc)
    aligned = make_bars(start, 4, timeframe="1h")
    dest = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    atomic_write_parquet(aligned, dest)

    # Bypass the write-time check to plant a dirty file, as a stale store would look.
    dirty = aligned.copy()
    dirty.loc[dirty.index[1], "open_time"] = pd.Timestamp("2018-02-09 09:28:14.789", tz="UTC")
    dirty = mark_source_seams(dirty)
    # Write with pyarrow directly so we don't trip assert_aligned.
    dirty.to_parquet(dest, index=False)

    reports = reports_from_store(data_dir=tmp_path)
    assert len(reports) == 1
    assert any(e.startswith("FAIL:") and "off-boundary" in e for e in reports[0].errors)
    json_path, _ = write_batch_reports("crypto", reports, dest=tmp_path / "reports")
    payload = __import__("json").loads(json_path.read_text())
    assert payload["n_series_failed"] == 1
    assert payload["series"][0]["ok"] is False
