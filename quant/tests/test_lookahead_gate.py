"""Mandatory QA generate() lookahead gate, run on SYNTHETIC data."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from signal_quant.audit_lookahead import (
    MIN_EMIT_AS_OF,
    _full_mapping,
    inspect_gate_keys,
    run_all_baseline_synthetic,
    run_gate_on_strategy,
)
from signal_quant.models import Signal
from signal_quant.strategy import Strategy
from signal_quant.synthetic import make_synthetic_ohlcv


def test_gate_compares_more_than_side():
    keys, missed = inspect_gate_keys()
    # Current KEYS in qa/audits/lookahead_generate.py
    for required in (
        "symbol",
        "timeframe",
        "bar_close_time",
        "horizon_bars",
        "side",
        "entry",
        "stop_loss",
        "take_profit",
        "confidence",
        "features_snapshot",
    ):
        assert required in keys, required
    # Fields the gate does not compare.
    for f in (
        "id",
        "strategy_id",
        "strategy_version",
        "asset_class",
        "generated_at",
        "rationale",
        "status",
        "is_mock",
        "confidence_calibrated",
        "calibration_run_id",
    ):
        assert f in missed, f
    assert "bar_close_time" not in missed
    assert "horizon_bars" not in missed
    assert set(keys).isdisjoint({"id"})  # new UUIDs must not fail the gate
    assert set(keys) <= set(Signal.model_fields)


class _NeverEmits(Strategy):
    strategy_id = "never_emits"
    strategy_version = "0.0.0"
    name = "Never emits"
    hypothesis_id = "H0"
    supported = (("crypto", "15m"),)

    def __init__(self) -> None:
        self.asset_class = "crypto"

    def signals_at(self, bars_by_timeframe: Mapping[str, pd.DataFrame], as_of: datetime) -> list:
        return []


def test_zero_emit_strategy_fails_lookahead_gate():
    df = make_synthetic_ohlcv(n=200, timeframe="15m", seed=1, process="trend")
    mapping = _full_mapping(df)
    as_ofs = list(mapping["15m"]["close_time"].iloc[80:120])
    fails = run_gate_on_strategy(_NeverEmits(), mapping, as_ofs, seed=0)
    reasons = [str(kind) for _as_of, kind in fails]
    assert any("insufficient_signals_for_lookahead" in r for r in reasons), reasons
    assert any("n=0" in r for r in reasons), reasons


def test_baselines_follow_min_signal_rule_on_synthetic():
    results = run_all_baseline_synthetic()
    # Lookahead (future perturb / truncation) must not fail.
    lookahead_failed = {
        sid: r
        for sid, r in results.items()
        if any("insufficient_signals_for_lookahead" not in str(k) for _, k in r["failures"])
    }
    assert not lookahead_failed, lookahead_failed
    for sid, r in results.items():
        if r["n_emitting"] < MIN_EMIT_AS_OF:
            assert r["pass"] is False, sid
            assert any(
                "insufficient_signals_for_lookahead" in str(k) for _, k in r["failures"]
            ), (sid, r)
        else:
            assert r["pass"] is True, (sid, r)
    # At least one baseline should still emit on the synthetic path.
    assert sum(r["n_emitting"] for r in results.values()) > 0
