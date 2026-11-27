"""Checksum verification for data.binance.vision archives (no network)."""

from __future__ import annotations

import hashlib
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from signal_data.ingestion.binance_vision import (
    SOURCE,
    ChecksumError,
    parse_checksum_file,
    parse_kline_zip,
    sha256_bytes,
    verify_checksum,
)
from signal_data.storage import merge_on_open_time


def test_parse_and_verify_checksum():
    data = b"hello-vision"
    digest = hashlib.sha256(data).hexdigest()
    text = f"{digest}  BTCUSDT-1d-2024-01.zip\n"
    assert parse_checksum_file(text) == digest
    assert verify_checksum(data, text, filename="BTCUSDT-1d-2024-01.zip") == digest
    with pytest.raises(ChecksumError):
        verify_checksum(b"tampered", text, filename="BTCUSDT-1d-2024-01.zip")
    with pytest.raises(ChecksumError):
        parse_checksum_file("not-a-checksum")
    assert sha256_bytes(data) == digest


def test_parse_kline_zip_no_header(tmp_path: Path):
    # One 1d bar, Vision layout, no CSV header.
    open_ms = 1704067200000  # 2024-01-01 00:00 UTC
    close_ms = 1704153599999
    csv = (
        f"{open_ms},100.0,110.0,90.0,105.0,12.5,{close_ms},"
        "1000.0,10,6.0,500.0,0\n"
    ).encode()
    zpath = tmp_path / "BTCUSDT-1d-2024-01.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("BTCUSDT-1d-2024-01.csv", csv)
    df = parse_kline_zip(zpath, timeframe="1d")
    assert len(df) == 1
    assert float(df.iloc[0]["open"]) == 100.0
    assert float(df.iloc[0]["close"]) == 105.0
    assert float(df.iloc[0]["volume"]) == 12.5
    assert df.iloc[0]["source"] == SOURCE
    assert pd.Timestamp(df.iloc[0]["open_time"]) == pd.Timestamp("2024-01-01", tz="UTC")
    assert pd.Timestamp(df.iloc[0]["close_time"]) == pd.Timestamp("2024-01-02", tz="UTC")


def test_merge_keeps_both_sources_and_prefers_vision_on_duplicate():
    a = pd.DataFrame(
        {
            "open_time": [pd.Timestamp("2024-01-01", tz="UTC")],
            "close_time": [pd.Timestamp("2024-01-02", tz="UTC")],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
            "source": ["ccxt:binanceus"],
            "is_stale": [False],
        }
    )
    b = a.copy()
    b["source"] = SOURCE
    b["close"] = 2.0
    merged = merge_on_open_time(a, b)
    assert len(merged) == 1
    assert merged.iloc[0]["source"] == SOURCE
    assert float(merged.iloc[0]["close"]) == 2.0
    assert not bool(merged.iloc[0]["source_seam"])


def test_parse_kline_zip_microsecond_timestamps(tmp_path: Path):
    """Vision switched from ms to microseconds in 2025-01; both must parse as UTC."""
    # 2025-01-01 00:00:00 UTC in microseconds
    open_us = 1735689600000000
    close_us = 1735775999999999
    csv = (
        f"{open_us},93576.0,95151.0,92888.0,94591.0,100.0,{close_us},"
        "1.0,1,1.0,1.0,0\n"
    ).encode()
    zpath = tmp_path / "BTCUSDT-1d-2025-01.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("BTCUSDT-1d-2025-01.csv", csv)
    df = parse_kline_zip(zpath, timeframe="1d")
    assert len(df) == 1
    assert pd.Timestamp(df.iloc[0]["open_time"]) == pd.Timestamp("2025-01-01", tz="UTC")
    assert pd.Timestamp(df.iloc[0]["close_time"]) == pd.Timestamp("2025-01-02", tz="UTC")
