"""Strategy registry used by the backend pipeline."""

from __future__ import annotations

import pytest

from signal_quant.registry import get_strategy, list_strategies, run_for_bar
from signal_quant.strategies import BASELINE
from signal_quant.synthetic import make_synthetic_ohlcv


def test_list_and_get_strategy():
    classes = list_strategies()
    ids = [c.strategy_id for c in classes]
    assert set(ids) == set(BASELINE)
    assert ids == sorted(ids)
    for cls in classes:
        assert cls.version == cls.strategy_version
        assert hasattr(cls, "supported")
        assert ("crypto", "1h") in cls.supported or cls.strategy_id == "mtf_confirmation"
        req = cls.required_timeframes("1h")
        assert "1h" in req
        assert req["1h"] > 0
        if cls.strategy_id == "mtf_confirmation":
            assert "4h" in req
            assert ("crypto", "1d") not in cls.supported


def test_get_strategy_version_mismatch():
    cls = get_strategy("trend_ema_adx")
    assert cls.strategy_id == "trend_ema_adx"
    with pytest.raises(KeyError):
        get_strategy("trend_ema_adx", version="no-such-version")
    with pytest.raises(KeyError):
        get_strategy("not_a_strategy")


def test_run_for_bar_uses_loader_and_skips_unsupported():
    df_1h = make_synthetic_ohlcv(n=120, timeframe="1h", seed=1, process="trend")
    df_4h = make_synthetic_ohlcv(n=80, timeframe="4h", seed=1, process="trend")
    as_of = df_1h.index[-1].to_pydatetime()
    calls = []

    def loader(symbol, timeframes, as_of, lookback_bars):
        calls.append((symbol, tuple(timeframes), lookback_bars))
        out = {}
        for tf in timeframes:
            src = df_4h if tf == "4h" else df_1h
            out[tf] = src
        return out

    signals = run_for_bar(
        symbol="BTC-USDT",
        asset_class="crypto",
        timeframe="1h",
        as_of=as_of,
        loader=loader,
    )
    assert isinstance(signals, list)
    assert calls, "run_for_bar must load bars"
    # Every emitted signal is for a supported pair and the trigger symbol.
    for s in signals:
        s.model_validate(s.model_dump())
        assert s.symbol == "BTC-USDT"
        assert s.timeframe == "1h"
        assert s.confidence_calibrated is False

    # 1d is unsupported for MTF; other baselines support it. The call must
    # not raise and must not emit an MTF signal.
    df_1d = make_synthetic_ohlcv(n=80, timeframe="1d", seed=2, process="trend")

    def loader_1d(symbol, timeframes, as_of, lookback_bars):
        return {tf: df_1d for tf in timeframes}

    as_of_d = df_1d.index[-1].to_pydatetime()
    out = run_for_bar("BTC-USDT", "crypto", "1d", as_of_d, loader=loader_1d)
    assert all(s.strategy_id != "mtf_confirmation" for s in out)
