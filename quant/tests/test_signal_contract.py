"""Emitted signals validate against the canonical v1 contract."""

from __future__ import annotations

from signal_quant.bars import bars_by_timeframe_from_base, infer_timeframe
from signal_quant.ml_policy import insufficient_oos_history, ml_fit_allowed
from signal_quant.strategy import snapshot_policy
from signal_quant.models import Signal, TIMEFRAMES
from signal_quant.strategies import BASELINE
from signal_quant.synthetic import make_synthetic_ohlcv


def test_ml_policy_locked_decisions():
    for tf in TIMEFRAMES:
        assert ml_fit_allowed("crypto", tf)
        assert not insufficient_oos_history("crypto", tf)
    for ac in ("equity", "fx"):
        assert ml_fit_allowed(ac, "1d")
        assert not ml_fit_allowed(ac, "4h")
        assert not ml_fit_allowed(ac, "1h")
        assert not ml_fit_allowed(ac, "15m")
        for tf in ("15m", "1h", "4h"):
            assert insufficient_oos_history(ac, tf)
            flags_short = snapshot_policy(ac, tf)
            assert flags_short["insufficient_oos_history"] is True
            assert flags_short["ml_fit_allowed"] is False
            assert flags_short["rule_only"] is True
        assert not insufficient_oos_history(ac, "1d")


def test_synthetic_signals_match_contract():
    df = make_synthetic_ohlcv(280, timeframe="15m", seed=4, process="trend")
    as_of = df.index[-1].to_pydatetime()
    mapping = bars_by_timeframe_from_base(df, as_of, infer_timeframe(df), asset_class="crypto")
    seen = 0
    # Walk a few closes so at least one strategy has a chance to emit.
    for i in range(120, len(df), 7):
        as_of = df.index[i].to_pydatetime()
        mapping = bars_by_timeframe_from_base(df.iloc[: i + 1], as_of, infer_timeframe(df), asset_class="crypto")
        for cls in BASELINE.values():
            s = cls(symbol="BTC-USDT", asset_class="crypto", is_mock=True)
            for sig in s.generate(mapping, as_of):
                assert isinstance(sig, Signal)
                # Re-validate through the model (shared or fallback).
                Signal.model_validate(sig.model_dump())
                assert sig.is_mock is True
                assert sig.confidence_calibrated is False
                assert sig.calibration_run_id is None
                assert sig.generated_at >= sig.bar_close_time
                assert sig.timeframe in TIMEFRAMES
                if sig.side.value != "flat":
                    assert sig.entry is not None and sig.stop_loss is not None and sig.take_profit
                seen += 1
    # It is OK if a particular seed emits few signals; we only require the
    # ones that *are* emitted to be valid. If none appeared, fail so the
    # skeleton cannot silently go mute.
    assert seen > 0


def test_equity_fx_intraday_and_4h_flagged_insufficient_oos():
    for ac in ("equity", "fx"):
        for tf in ("15m", "1h", "4h"):
            flags = snapshot_policy(ac, tf)
            assert flags["insufficient_oos_history"] is True
            assert flags["ml_fit_allowed"] is False
            assert flags["rule_only"] is True
        flags_ok = snapshot_policy(ac, "1d")
        assert flags_ok["insufficient_oos_history"] is False
        assert flags_ok["ml_fit_allowed"] is True
        assert flags_ok["rule_only"] is False


def test_quant_does_not_invent_report_flags():
    """Quant may set insufficient_oos_history metadata; it must not invent report flags."""
    from signal_quant.models import BacktestFlag

    expected = {
        "low_oos_trades",
        "sharpe_gt_3",
        "win_rate_gt_75",
        "insufficient_oos_history",
        "data_quality_warning",
        "metric_recompute_mismatch",
        "metric_undefined",
    }
    assert {f.value for f in BacktestFlag} == expected
    flags_eq = snapshot_policy("equity", "4h")
    assert flags_eq["insufficient_oos_history"] is True
    # Snapshot metadata only — no invented report-flag list.
    assert "flags" not in flags_eq
    assert "data_quality_warning" not in flags_eq
    assert "low_oos_trades" not in flags_eq
    flags_1d = snapshot_policy("equity", "1d")
    assert flags_1d["insufficient_oos_history"] is False
