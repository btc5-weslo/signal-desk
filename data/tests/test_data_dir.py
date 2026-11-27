"""SIGNAL_DATA_DIR is the store root; no silent hard-coded fallback in staging/prod."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from signal_data.paths import (
    DEFAULT_STORE_DIR,
    MissingDataDir,
    get_staging_dir,
    get_store_dir,
    series_path,
)
from signal_data.store import candle_path, get_candles
from signal_data.storage import atomic_write_parquet
from tests.toy import make_bars


def _toy(n=3, timeframe="1d"):
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return make_bars(start, n, timeframe=timeframe)


def test_dev_default_is_repo_store_root(monkeypatch):
    monkeypatch.delenv("SIGNAL_DATA_DIR", raising=False)
    monkeypatch.delenv("SIGNAL_ENV", raising=False)
    root = get_store_dir()
    assert root == DEFAULT_STORE_DIR
    assert root == Path(__file__).resolve().parents[1] / "store"  # <repo>/data/store
    assert series_path("crypto", "BTC-USDT", "1h") == root / "crypto" / "BTC-USDT" / "1h.parquet"


def test_dev_env_allows_default(monkeypatch):
    monkeypatch.delenv("SIGNAL_DATA_DIR", raising=False)
    monkeypatch.setenv("SIGNAL_ENV", "dev")
    assert get_store_dir() == DEFAULT_STORE_DIR
    monkeypatch.setenv("SIGNAL_ENV", "test")
    assert get_store_dir() == DEFAULT_STORE_DIR


def test_explicit_data_dir_wins_over_env(tmp_path, monkeypatch):
    env_root = tmp_path / "envstore"
    explicit = tmp_path / "explicit"
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(env_root))
    monkeypatch.setenv("SIGNAL_ENV", "prod")
    assert get_store_dir(explicit) == explicit
    assert candle_path("BTC-USDT", "1h", data_dir=explicit) == explicit / "crypto" / "BTC-USDT" / "1h.parquet"
    # store_dir is an accepted alias for the same store root
    assert candle_path("BTC-USDT", "1h", store_dir=explicit) == explicit / "crypto" / "BTC-USDT" / "1h.parquet"


def test_signal_data_dir_env_used_when_no_argument(tmp_path, monkeypatch):
    root = tmp_path / "store"
    target = root / "crypto" / "BTC-USDT" / "1d.parquet"
    atomic_write_parquet(_toy(), target)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(root))
    monkeypatch.setenv("SIGNAL_ENV", "prod")
    out = get_candles("BTC-USDT", "1d")
    assert len(out) == 3
    # A missing file is reported under the env root, not the repo default.
    with pytest.raises(FileNotFoundError) as exc:
        get_candles("ETH-USDT", "1d")
    assert str(root / "crypto" / "ETH-USDT" / "1d.parquet") in str(exc.value)
    assert "signal-app/data/store" not in str(exc.value)


def test_prod_and_staging_without_env_raise_no_silent_default(monkeypatch):
    monkeypatch.delenv("SIGNAL_DATA_DIR", raising=False)
    for env in ("prod", "staging"):
        monkeypatch.setenv("SIGNAL_ENV", env)
        with pytest.raises(MissingDataDir) as exc:
            get_store_dir()
        assert "SIGNAL_DATA_DIR" in str(exc.value)
        assert "SIGNAL_DATA_STORE_DIR" not in str(exc.value)
        with pytest.raises(MissingDataDir):
            get_candles("BTC-USDT", "1d")


def test_import_raises_in_prod_without_signal_data_dir():
    env = os.environ.copy()
    env["SIGNAL_ENV"] = "prod"
    env.pop("SIGNAL_DATA_DIR", None)
    env.pop("SIGNAL_DATA_STORE_DIR", None)
    code = "from signal_data.paths import get_store_dir"
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode != 0, r.stdout
    assert "SIGNAL_DATA_DIR" in (r.stderr + r.stdout)


def test_staging_dir_is_optional_and_separate(tmp_path, monkeypatch):
    monkeypatch.delenv("SIGNAL_DATA_STAGING_DIR", raising=False)
    default = get_staging_dir()
    assert default.name == "staging"
    staged = tmp_path / "my-staging"
    monkeypatch.setenv("SIGNAL_DATA_STAGING_DIR", str(staged))
    assert get_staging_dir() == staged
    assert get_store_dir(tmp_path / "store") != staged
