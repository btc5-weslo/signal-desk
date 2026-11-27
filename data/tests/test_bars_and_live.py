"""Public load_closed and live.update."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pandas as pd

from signal_data.bars import load_closed
from signal_data.live import REDIS_CHANNEL, BarClosed, update
from signal_data.storage import atomic_write_parquet
from tests.toy import make_bars


def _write_series(tmp_path, symbol, timeframe, n, start, source="toy"):
    df = make_bars(start, n, timeframe=timeframe)
    df["source"] = source
    path = tmp_path / "crypto" / symbol / f"{timeframe}.parquet"
    atomic_write_parquet(df, path)
    return df


def test_load_closed_truncates_lookback_and_keeps_source(tmp_path):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _write_series(tmp_path, "BTC-USDT", "1h", 20, start, source="binance_vision")
    _write_series(tmp_path, "BTC-USDT", "1d", 10, start, source="ccxt:binanceus")
    as_of = datetime(2024, 1, 1, 10, tzinfo=timezone.utc)  # includes the 09:00 bar (close 10:00)
    frames = load_closed("BTC-USDT", ["1h", "1d"], as_of, lookback_bars=5, store_dir=tmp_path)
    assert set(frames) == {"1h", "1d"}
    hourly = frames["1h"]
    assert len(hourly) == 5
    assert (hourly["close_time"] <= pd.Timestamp(as_of)).all()
    assert "source" in hourly.columns
    assert set(hourly["source"].unique()) == {"binance_vision"}
    daily = frames["1d"]
    # 1d bars with close 2024-01-02, 01-03, ... — only the first has close 2024-01-02
    # as_of 2024-01-01 10:00 is before any daily close, so daily may be empty.
    assert "source" in daily.columns


def test_load_closed_drops_stale_by_default(tmp_path):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = make_bars(start, 6, timeframe="1h")
    df["source"] = "toy"
    # Make bar 3 stale
    df.loc[3, ["open", "high", "low", "close", "volume"]] = [10.0, 10.0, 10.0, 10.0, 0.0]
    path = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    atomic_write_parquet(df, path)
    as_of = df["close_time"].iloc[-1]
    frames = load_closed("BTC-USDT", "1h", as_of, lookback_bars=20, store_dir=tmp_path)
    assert len(frames["1h"]) == 5
    kept = load_closed("BTC-USDT", ["1h"], as_of, 20, store_dir=tmp_path, drop_stale=False)["1h"]
    assert len(kept) == 6


def test_live_update_no_redis_without_url(tmp_path, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _write_series(tmp_path, "BTC-USDT", "1h", 4, start, source="toy")
    published = []

    def boom(*_a, **_k):
        raise AssertionError("Redis must not be contacted when REDIS_URL is unset")

    monkeypatch.setattr("signal_data.live._publish_redis", boom)
    as_of = datetime(2024, 1, 1, 4, tzinfo=timezone.utc)
    closed = update(["BTC-USDT"], ["1h"], store_dir=tmp_path, as_of=as_of)
    assert len(closed) == 1
    bar = closed[0]
    assert isinstance(bar, BarClosed)
    assert bar.symbol == "BTC-USDT"
    assert bar.timeframe == "1h"
    assert bar.source == "toy"
    assert bar.close_time == datetime(2024, 1, 1, 4, tzinfo=timezone.utc)
    assert published == []


def test_live_update_publishes_only_when_url_set(tmp_path, monkeypatch):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _write_series(tmp_path, "BTC-USDT", "1h", 3, start, source="toy")
    seen = []

    def fake_publish(url, bars):
        seen.append((url, list(bars)))

    monkeypatch.setattr("signal_data.live._publish_redis", fake_publish)
    monkeypatch.delenv("REDIS_URL", raising=False)
    as_of = datetime(2024, 1, 1, 3, tzinfo=timezone.utc)
    update(["BTC-USDT"], ["1h"], store_dir=tmp_path, as_of=as_of)
    assert seen == []
    update(["BTC-USDT"], ["1h"], store_dir=tmp_path, as_of=as_of, redis_url="redis://example:6379/0")
    assert len(seen) == 1
    assert seen[0][0] == "redis://example:6379/0"
    assert seen[0][1][0].symbol == "BTC-USDT"
    assert REDIS_CHANNEL == "bars:closed"



def test_live_update_raises_if_redis_url_set_but_redis_missing(tmp_path, monkeypatch):
    """A set REDIS_URL must not be silently ignored when redis is missing."""
    import builtins

    from signal_data.live import update
    from signal_data.storage import atomic_write_parquet
    from tests.toy import make_bars

    start = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
    bars = make_bars(start, 5, timeframe="1h")
    atomic_write_parquet(bars, tmp_path / "crypto" / "BTC-USDT" / "1h.parquet")

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("No module named 'redis'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    with pytest.raises(ImportError, match="REDIS_URL is set but the redis package is not installed"):
        update(["BTC-USDT"], ["1h"], store_dir=tmp_path, as_of=start + timedelta(hours=6))
