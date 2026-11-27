import logging

from app.core.config import Settings
from app.core.licensing import (
    filter_licensed_sources,
    is_licensed_source,
    is_never_licensed,
)


def test_never_licensed_names_and_ccxt_prefix():
    assert is_never_licensed("binance_vision") is True
    assert is_never_licensed("Binance_Vision") is True
    assert is_never_licensed("yfinance") is True
    assert is_never_licensed("ccxt:binance") is True
    assert is_never_licensed("ccxt:") is True
    assert is_never_licensed("ok-source") is False
    assert is_never_licensed("") is False
    assert is_never_licensed(None) is False


def test_filter_drops_never_licensed_with_warning(caplog):
    caplog.set_level(logging.WARNING)
    out = filter_licensed_sources(
        ["ok-source", "binance_vision", "yfinance", "ccxt:binance", "ok-source", ""],
    )
    assert out == ["ok-source"]
    assert "binance_vision" in caplog.text
    assert "yfinance" in caplog.text
    assert "ccxt:binance" in caplog.text


def test_is_licensed_source_uses_allow_list_and_never_rule():
    allowed = ["ok-source", "vendor-a"]
    assert is_licensed_source("ok-source", licensed=allowed) is True
    assert is_licensed_source("vendor-a", licensed=allowed) is True
    assert is_licensed_source("other", licensed=allowed) is False
    # Never-licensed even if a caller sneaks them into the list.
    sneaky = ["ok-source", "binance_vision", "yfinance", "ccxt:kraken"]
    assert is_licensed_source("binance_vision", licensed=sneaky) is False
    assert is_licensed_source("yfinance", licensed=sneaky) is False
    assert is_licensed_source("ccxt:kraken", licensed=sneaky) is False
    assert is_licensed_source(None, licensed=allowed) is False
    assert is_licensed_source("", licensed=allowed) is False


def test_settings_filters_never_licensed_from_env(monkeypatch):
    monkeypatch.setenv(
        "SIGNAL_LICENSED_DATA_SOURCES",
        "ok-source, binance_vision, yfinance, ccxt:binance, vendor-a",
    )
    s = Settings()
    assert s.licensed_data_sources == ["ok-source", "vendor-a"]
    assert is_licensed_source("ok-source", licensed=s.licensed_data_sources)
    assert not is_licensed_source("binance_vision", licensed=s.licensed_data_sources)
    empty = Settings(licensed_data_sources=[])
    assert empty.licensed_data_sources == []
    assert is_licensed_source("ok-source", licensed=empty.licensed_data_sources) is False
