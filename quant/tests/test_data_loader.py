"""Data-store loader and canonical symbols. No performance claims."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from signal_quant.data_loader import list_available_series, load_series, series_path
from signal_quant.symbols import to_canonical_symbol
from signal_quant.synthetic import make_synthetic_ohlcv


def test_canonical_symbols_passthrough():
    assert to_canonical_symbol("BTC-USDT") == "BTC-USDT"
    assert to_canonical_symbol("AAPL") == "AAPL"
    assert to_canonical_symbol("EURUSD") == "EURUSD"


def test_slash_symbol_rejected_until_official_normalizer_exists():
    # We do not hand-write mappings. If official helpers appear, this test
    # should be updated to expect their canonical output instead of a raise.
    try:
        from signal_data.symbols import to_canonical  # noqa: F401
        official = True
    except ImportError:
        try:
            from signal_shared import normalize_symbol  # noqa: F401
            official = True
        except ImportError:
            official = False
    if official:
        pytest.skip("official symbol normalizer is present; wrapper defers to it")
    with pytest.raises(ValueError, match="not canonical"):
        to_canonical_symbol("BTC/USDT")


def test_load_missing_series_is_empty(tmp_path: Path):
    df = load_series("crypto", "BTC-USDT", "15m", root=tmp_path)
    assert df.empty
    assert "close_time" in list(df.columns) or df.empty


def test_load_roundtrip_canonical_layout(tmp_path: Path):
    pytest.importorskip("pyarrow")
    src = make_synthetic_ohlcv(40, timeframe="15m", seed=1, process="trend")
    # Store form: columns open_time, close_time, OHLCV, source
    raw = src.reset_index(drop=True)[
        ["open_time", "close_time", "open", "high", "low", "close", "volume", "source"]
    ]
    path = series_path("crypto", "BTC-USDT", "15m", root=tmp_path)
    path.parent.mkdir(parents=True)
    raw.to_parquet(path, index=False)
    loaded = load_series("crypto", "BTC-USDT", "15m", root=tmp_path)
    assert len(loaded) == 40
    assert loaded["close_time"].dt.tz is not None
    assert list_available_series(root=tmp_path) == [
        ("crypto", "BTC-USDT", "15m", path)
    ]
