"""Backend import path: from signal_data.candles import get_candles."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from signal_data.candles import candle_path, get_candles
from signal_data.storage import atomic_write_parquet
from signal_data.store import get_candles as store_get_candles
from tests.toy import make_bars


def test_candles_reexports_store_get_candles():
    assert get_candles is store_get_candles


def test_get_candles_from_candles_module_reads_exact_file(tmp_path: Path):
    bars = make_bars(datetime(2024, 1, 2, tzinfo=timezone.utc), 5, timeframe="1d")
    path = tmp_path / "crypto" / "BTC-USDT" / "1d.parquet"
    atomic_write_parquet(bars, path)
    # decoys that a glob would pick up
    atomic_write_parquet(bars, tmp_path / "crypto" / "ETH-USDT" / "1d.parquet")
    atomic_write_parquet(bars, tmp_path / "crypto" / "BTC-USDT" / "1h.parquet")

    assert candle_path("BTC/USDT", "1d", store_dir=tmp_path) == path
    out = get_candles("BTCUSDT", "1d", store_dir=tmp_path)
    assert len(out) == 5
    assert list(out["close"]) == list(bars["close"])


def test_candles_import_has_no_side_effects():
    # Imported at module top; this just documents the contract.
    import signal_data.candles as m

    assert "get_candles" in m.__all__
    assert not hasattr(m, "ingest_series")
