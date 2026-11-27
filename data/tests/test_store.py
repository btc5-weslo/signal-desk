"""get_candles reads exactly one locked-layout file and does not glob."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from signal_data.store import candle_path, get_candles
from signal_data.storage import atomic_write_parquet
from tests.toy import make_bars
from datetime import datetime, timezone


def _toy(n=5):
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return make_bars(start, n, timeframe="1d")


def test_candle_path_is_exact_and_uses_canonical_symbol(tmp_path: Path):
    p = candle_path("BTC/USDT", "1d", store_dir=tmp_path)
    assert p == tmp_path / "crypto" / "BTC-USDT" / "1d.parquet"
    p = candle_path("aapl.us", "1d", store_dir=tmp_path)
    assert p == tmp_path / "equity" / "AAPL" / "1d.parquet"
    p = candle_path("EURUSD=X", "1h", store_dir=tmp_path)
    assert p == tmp_path / "fx" / "EURUSD" / "1h.parquet"


def test_get_candles_reads_exactly_one_file(tmp_path: Path, monkeypatch):
    bars = _toy()
    target = tmp_path / "crypto" / "BTC-USDT" / "1d.parquet"
    atomic_write_parquet(bars, target)

    # A second file that must not be picked up by any glob-style lookup.
    other = tmp_path / "crypto" / "ETH-USDT" / "1d.parquet"
    atomic_write_parquet(bars, other)
    decoy = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    atomic_write_parquet(bars, decoy)

    calls: list[str] = []
    real_glob = Path.glob
    real_rglob = Path.rglob

    def watch_glob(self, pattern):
        calls.append(f"glob:{self}:{pattern}")
        return real_glob(self, pattern)

    def watch_rglob(self, pattern):
        calls.append(f"rglob:{self}:{pattern}")
        return real_rglob(self, pattern)

    monkeypatch.setattr(Path, "glob", watch_glob)
    monkeypatch.setattr(Path, "rglob", watch_rglob)

    out = get_candles("BTCUSDT", "1d", store_dir=tmp_path)
    assert len(out) == len(bars)
    assert list(out["close"]) == list(bars["close"])
    assert calls == [], f"get_candles must not glob; saw {calls}"


def test_get_candles_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as exc:
        get_candles("AAPL", "1d", store_dir=tmp_path)
    assert "equity/AAPL/1d.parquet" in str(exc.value)


def test_get_candles_rejects_bad_timeframe(tmp_path: Path):
    with pytest.raises(ValueError):
        get_candles("AAPL", "1w", store_dir=tmp_path)
