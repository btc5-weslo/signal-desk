"""Store root is data_dir / SIGNAL_DATA_DIR. No implicit default path."""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

from signal_quant.data_loader import (
    SIGNAL_DATA_DIR_ENV,
    DataDirError,
    list_available_series,
    load_series,
    resolve_data_dir,
    series_path,
)
from signal_quant.registry import generate_range, run_for_bar
from signal_quant.synthetic import make_synthetic_ohlcv


def _write_series(root: Path, *, timeframe: str = "1h", n: int = 80, close: float | None = None):
    pytest.importorskip("pyarrow")
    src = make_synthetic_ohlcv(n, timeframe=timeframe, seed=3, process="trend")
    if close is not None:
        src = src.copy()
        src["close"] = float(close)
        src["open"] = float(close)
        src["high"] = float(close) + 0.1
        src["low"] = float(close) - 0.1
    raw = src.reset_index(drop=True)[
        ["open_time", "close_time", "open", "high", "low", "close", "volume", "source"]
    ]
    path = series_path("crypto", "BTC-USDT", timeframe, data_dir=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(path, index=False)
    return path, src


def test_resolve_data_dir_prefers_argument_then_env(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNAL_DATA_DIR_ENV, raising=False)
    assert resolve_data_dir(tmp_path, required=False) == tmp_path
    other = tmp_path / "env-store"
    other.mkdir()
    monkeypatch.setenv(SIGNAL_DATA_DIR_ENV, str(other))
    assert resolve_data_dir(required=False) == other
    # Explicit data_dir wins over the env var.
    assert resolve_data_dir(tmp_path, required=False) == tmp_path
    monkeypatch.delenv(SIGNAL_DATA_DIR_ENV, raising=False)
    with pytest.raises(DataDirError, match="SIGNAL_DATA_DIR"):
        resolve_data_dir(required=True)
    assert resolve_data_dir(required=False) is None


def test_temp_store_passed_as_data_dir_is_the_one_read(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNAL_DATA_DIR_ENV, raising=False)
    marker = 123456.789
    _write_series(tmp_path, close=marker)
    loaded = load_series("crypto", "BTC-USDT", "1h", data_dir=tmp_path)
    assert len(loaded) == 80
    assert float(loaded["close"].iloc[-1]) == pytest.approx(marker)
    found = list_available_series(data_dir=tmp_path)
    assert [(ac, sym, tf) for ac, sym, tf, _ in found] == [("crypto", "BTC-USDT", "1h")]

    as_of = loaded.index[-1].to_pydatetime()
    signals = run_for_bar(
        "BTC-USDT",
        "crypto",
        "1h",
        as_of,
        data_dir=tmp_path,
    )
    assert isinstance(signals, list)


def test_run_for_bar_requires_data_dir_or_env_when_no_loader(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNAL_DATA_DIR_ENV, raising=False)
    as_of = make_synthetic_ohlcv(10, timeframe="1h", seed=1).index[-1].to_pydatetime()
    with pytest.raises(DataDirError, match="SIGNAL_DATA_DIR"):
        run_for_bar("BTC-USDT", "crypto", "1h", as_of)


def test_run_for_bar_signature_has_keyword_only_data_dir():
    sig = inspect.signature(run_for_bar)
    params = list(sig.parameters)
    assert params == ["symbol", "asset_class", "timeframe", "as_of", "loader", "data_dir"]
    assert sig.parameters["data_dir"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["loader"].default is None
    assert sig.parameters["data_dir"].default is None


def test_no_hardcoded_data_path_in_signal_quant():
    root = Path(__file__).resolve().parents[1] / "signal_quant"
    forbidden = (
        "/workspace/signal-app/data",
        "/workspace/signal-data",
        "signal-app/data/store",
        "SIGNAL_DATA_STORE_DIR",
    )
    offenders = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix not in {".py", ".md", ".txt", ".toml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.relative_to(root)}: {needle}")
    assert not offenders, "hard-coded data path or wrong env var name:\n" + "\n".join(offenders)


def test_generate_range_requires_data_dir_or_env_when_no_loader(monkeypatch):
    monkeypatch.delenv(SIGNAL_DATA_DIR_ENV, raising=False)
    start = make_synthetic_ohlcv(10, timeframe="1h", seed=1).index[0].to_pydatetime()
    end = make_synthetic_ohlcv(10, timeframe="1h", seed=1).index[-1].to_pydatetime()
    with pytest.raises(DataDirError, match="SIGNAL_DATA_DIR"):
        generate_range("trend_ema_adx", "BTC-USDT", "crypto", "1h", start, end)


def test_generate_range_signature_has_keyword_only_data_dir():
    sig = inspect.signature(generate_range)
    params = list(sig.parameters)
    assert params[:6] == [
        "strategy_id",
        "symbol",
        "asset_class",
        "timeframe",
        "start",
        "end",
    ]
    assert sig.parameters["data_dir"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["loader"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["data_dir"].default is None
