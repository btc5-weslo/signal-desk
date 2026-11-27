from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from signal_shared import (
    BacktestFlag,
    BacktestReport,
    Signal,
    Trade,
    infer_asset_class,
    normalize_symbol,
)


def _trade(**kw):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    base = {
        "symbol": "BTC-USDT", "side": "long", "entry_time": t,
        "exit_time": t + timedelta(hours=1), "entry_price": 100.0, "exit_price": 101.0,
        "exit_reason": "tp", "r_multiple": 0.5, "bars_held": 1, "net_return": 0.01,
    }
    base.update(kw)
    return Trade(**base)


def _report(**kw):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    trades = kw.pop("trades", [_trade()])
    base = {
        "strategy_id": "s", "version": "1",
        "period": {"start": t, "end": t + timedelta(days=1)},
        "oos_windows": [{"train_start": t, "train_end": t, "test_start": t, "test_end": t}],
        "trades": trades, "trade_count": len(trades),
        "win_rate": 0.0, "profit_factor": 0.0, "sharpe": 0.0, "sortino": 0.0,
        "max_drawdown": 0.0, "avg_R": 0.0, "exposure": 0.0, "fees_bps": 1.0,
        "slippage_bps": 1.0, "run_id": "r", "data_hash": "h", "flags": [],
    }
    base.update(kw)
    return BacktestReport(**base)


def _signal(**kw):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    base = {
        "id": "x", "strategy_id": "s", "strategy_version": "1", "symbol": "BTC-USDT",
        "asset_class": "crypto", "timeframe": "1h", "side": "flat", "generated_at": t,
        "bar_close_time": t, "horizon_bars": 1, "confidence": 0.5, "rationale": "r",
    }
    base.update(kw)
    return Signal(**base)


def test_backtest_report_always_includes_flags_and_trade_list():
    d = _report(flags=["low_oos_trades"]).model_dump()
    assert d["flags"] == [BacktestFlag.low_oos_trades]
    assert d["trade_count"] == 1
    assert isinstance(d["trades"], list)
    assert d["trades"][0]["net_return"] == 0.01
    assert d["trades"][0]["exit_reason"] == "tp"
    assert "flags" in _report().model_dump()
    assert "qa_approved" not in d


def test_trade_count_must_match_trades():
    with pytest.raises(ValidationError):
        _report(trade_count=99)


def test_trade_rejects_flat_side():
    with pytest.raises(ValidationError):
        _trade(side="flat")


def test_normalize_symbol_accepts_canonical_forms():
    assert normalize_symbol("BTC-USDT") == "BTC-USDT"
    assert normalize_symbol("BTC-USDT", "crypto") == "BTC-USDT"
    assert normalize_symbol("AAPL") == "AAPL"
    assert normalize_symbol("AAPL", "equity") == "AAPL"
    assert normalize_symbol("BRK.B", "equity") == "BRK.B"
    assert normalize_symbol("EURUSD") == "EURUSD"
    assert normalize_symbol("EURUSD", "fx") == "EURUSD"
    assert infer_asset_class("BTC-USDT") == "crypto"
    assert infer_asset_class("AAPL") == "equity"
    assert infer_asset_class("EURUSD") == "fx"


@pytest.mark.parametrize("raw,asset_class", [
    ("BTCUSDT", "crypto"),
    ("BTC/USDT", "crypto"),
    ("btc-usdt", None),
    ("EURUSD=X", "fx"),
    ("EUR/USD", "fx"),
    ("aapl", "equity"),
    ("AAPL.US", "equity"),
    ("", None),
    ("BTC-USDT", "fx"),
])
def test_normalize_symbol_rejects_aliases_and_mismatches(raw, asset_class):
    with pytest.raises(ValueError):
        normalize_symbol(raw, asset_class)


def test_signal_rejects_non_canonical_symbol():
    with pytest.raises(ValidationError):
        _signal(symbol="BTCUSDT")


def test_confidence_calibrated_requires_run_id():
    with pytest.raises(ValidationError):
        _signal(confidence_calibrated=True)
    s = _signal(confidence_calibrated=True, calibration_run_id="cal-1")
    assert s.confidence_calibrated is True and s.calibration_run_id == "cal-1"
    d = _signal().model_dump()
    assert d["confidence_calibrated"] is False and d["calibration_run_id"] is None



def test_backtest_report_rejects_unknown_flag():
    with pytest.raises(ValidationError):
        _report(flags=["under 100 OOS trades"])


def test_backtest_report_symbol_and_timeframe():
    summary = _report()
    assert summary.symbol is None and summary.timeframe is None
    per = _report(symbol="BTC-USDT", timeframe="1h")
    assert per.symbol == "BTC-USDT" and per.timeframe == "1h"
    with pytest.raises(ValidationError):
        _report(symbol="BTC-USDT")
    with pytest.raises(ValidationError):
        _report(timeframe="1h")
    with pytest.raises(ValidationError):
        _report(symbol="BTCUSDT", timeframe="1h")
