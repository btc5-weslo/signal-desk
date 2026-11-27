"""Contract: quant labels match signal_data.barriers.resolve when it exists.

Covers same-bar stop+target (must be a stop) and timeout.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from signal_quant.labeling import (
    _fallback_label_triple_barrier,
    _try_import_resolve,
    label_signal,
    label_triple_barrier,
)
from signal_quant.models import AssetClass, Side, Signal, SignalStatus


def _bars_from_ohlc(rows):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="1h", tz="UTC")
    df = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])
    df["volume"] = 1.0
    df["close_time"] = df.index
    df["open_time"] = df.index - pd.Timedelta(hours=1)
    return df


def _signal(df, *, signal_index, side, stop, tps, horizon, entry=None):
    as_of = df.index[signal_index].to_pydatetime()
    return Signal(
        id="test-signal",
        strategy_id="trend_ema_adx",
        strategy_version="0.1.0",
        symbol="BTC-USDT",
        asset_class=AssetClass.crypto,
        timeframe="1h",
        side=Side(side),
        generated_at=as_of,
        bar_close_time=as_of,
        entry=entry,
        stop_loss=stop,
        take_profit=list(tps),
        horizon_bars=horizon,
        confidence=0.5,
        features_snapshot={},
        rationale="contract",
        status=SignalStatus.active,
        is_mock=True,
        confidence_calibrated=False,
        calibration_run_id=None,
    )


def test_same_bar_stop_and_timeout_on_fallback():
    # Signal at bar 0; fill at bar 1 open=100. Same fill bar trades 90-110,
    # touching a stop at 95 and a target at 105. Must resolve to hit_sl.
    collision = _bars_from_ohlc(
        [
            dict(open=100, high=101, low=99, close=100),
            dict(open=100, high=110, low=90, close=100),
            dict(open=100, high=101, low=99, close=100),
        ]
    )
    lab = _fallback_label_triple_barrier(
        collision,
        signal_index=0,
        side="long",
        stop_loss=95.0,
        take_profit=[105.0],
        horizon_bars=3,
        entry_price=100.0,
    )
    assert lab["outcome"] == "hit_sl"
    assert lab["bars_held"] == 1
    assert lab["r_multiple"] == -1.0

    # Timeout: path never touches 95 or 105; expires at horizon.
    timeout = _bars_from_ohlc(
        [
            dict(open=100, high=101, low=99, close=100),
            dict(open=100, high=102, low=99, close=101),
            dict(open=101, high=103, low=100, close=102),
            dict(open=102, high=104, low=101, close=103),
        ]
    )
    lab_t = _fallback_label_triple_barrier(
        timeout,
        signal_index=0,
        side="long",
        stop_loss=95.0,
        take_profit=[110.0],
        horizon_bars=2,
        entry_price=100.0,
    )
    assert lab_t["outcome"] == "expired"
    assert lab_t["bars_held"] == 2


def test_public_label_api_matches_fallback_when_resolve_absent():
    if _try_import_resolve() is not None:
        pytest.skip("resolve is present; compared in test_labels_match_resolve")
    df = _bars_from_ohlc(
        [
            dict(open=100, high=101, low=99, close=100),
            dict(open=100, high=110, low=90, close=100),
            dict(open=100, high=101, low=99, close=100),
        ]
    )
    pub = label_triple_barrier(
        df,
        signal_index=0,
        side="long",
        stop_loss=95.0,
        take_profit=[105.0],
        horizon_bars=3,
        entry_price=100.0,
    )
    assert pub["outcome"] == "hit_sl"
    sig = _signal(df, signal_index=0, side="long", stop=95.0, tps=[105.0], horizon=3, entry=100.0)
    via_signal = label_signal(sig, df)
    assert via_signal["outcome"] == "hit_sl"


def test_labels_match_resolve_when_available():
    resolve = _try_import_resolve()
    if resolve is None:
        pytest.skip("signal_data.barriers.resolve is not published yet")

    collision = _bars_from_ohlc(
        [
            dict(open=100, high=101, low=99, close=100),
            dict(open=100, high=110, low=90, close=100),
            dict(open=100, high=101, low=99, close=100),
        ]
    )
    timeout = _bars_from_ohlc(
        [
            dict(open=100, high=101, low=99, close=100),
            dict(open=100, high=102, low=99, close=101),
            dict(open=101, high=103, low=100, close=102),
            dict(open=102, high=104, low=101, close=103),
        ]
    )
    cases = [
        (collision, 0, "long", 95.0, [105.0], 3, 100.0, "hit_sl"),
        (timeout, 0, "long", 95.0, [110.0], 2, 100.0, "expired"),
    ]
    for df, idx, side, stop, tps, horizon, entry, expected in cases:
        sig = _signal(df, signal_index=idx, side=side, stop=stop, tps=tps, horizon=horizon, entry=entry)
        via_resolve = label_signal(sig, df)
        via_fallback = _fallback_label_triple_barrier(
            df,
            signal_index=idx,
            side=side,
            stop_loss=stop,
            take_profit=tps,
            horizon_bars=horizon,
            entry_price=entry,
        )
        assert via_resolve["outcome"] == expected
        assert via_fallback["outcome"] == expected
        assert via_resolve["outcome"] == via_fallback["outcome"]
        assert via_resolve["bars_held"] == via_fallback["bars_held"]
        if expected == "hit_sl":
            assert via_resolve["r_multiple"] == pytest.approx(via_fallback["r_multiple"])
