"""Undefined metrics are null + the metric_undefined flag, never a sentinel (QA 2026-11-26)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from signal_shared import BacktestFlag, ExitReason, Side

from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import run_backtest
from signal_data.backtester.flags import compute_flags
from signal_data.backtester.metrics import profit_factor, sharpe, sortino, summarize, undefined_metrics
from signal_data.schema import TradeAudit
from tests.toy import make_bars

SCHEMA = Path(__file__).resolve().parents[2] / "shared" / "backtest_result.schema.json"
TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _t(n):
    return TradeAudit(
        symbol="AAPL", side=Side.long, reference_entry=100.0, entry_time=TS, exit_time=TS,
        entry_price=100.0, exit_price=100.0, stop_loss=95.0,
        exit_reason=ExitReason.tp if n > 0 else ExitReason.sl,
        r_multiple=1.0 if n > 0 else -1.0, bars_held=1, net_return=n,
    )


def test_profit_factor_undefined_is_none():
    assert profit_factor([]) is None
    assert profit_factor([_t(0.02), _t(0.01)]) is None  # no losses: infinite
    assert profit_factor([_t(0.02), _t(-0.01)]) == 2.0


def test_sharpe_sortino_undefined_is_none():
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    flat = pd.Series([100.0] * 5, index=idx)
    up = pd.Series([100.0, 101, 102, 103, 104], index=idx)
    assert sharpe(flat, 365) is None
    assert sortino(flat, 365) is None
    assert sortino(up, 365) is None  # no downside
    assert sharpe(up, 365) is not None and math.isfinite(sharpe(up, 365))


def test_flag_added_when_any_metric_undefined():
    m = summarize([], pd.Series([1.0, 1.0]), pd.Series([0, 0]), timeframe="1d")
    assert set(undefined_metrics(m)) == {"profit_factor", "sharpe", "sortino"}
    flags = compute_flags(trades=[], win_rate_reported=0.0, profit_factor_reported=None, sharpe=None,
                          metric_undefined=True)
    assert BacktestFlag.metric_undefined in flags
    assert BacktestFlag.metric_recompute_mismatch not in flags
    assert BacktestFlag.sharpe_gt_3 not in flags


def test_report_serializes_null_and_validates_schema():
    import jsonschema

    bars = make_bars(TS, 10)
    run = run_backtest(bars, symbol="AAPL", timeframe="1d", signals=[], cost=CostModel(10, 5))
    d = json.loads(run.report.model_dump_json())
    assert d["profit_factor"] is None and d["sharpe"] is None and d["sortino"] is None
    assert "metric_undefined" in d["flags"]
    jsonschema.validate(d, json.loads(SCHEMA.read_text()))
    # window metrics may also be null
    d["oos_windows"] = [{"train_start": d["period"]["start"], "train_end": d["period"]["start"],
                         "test_start": d["period"]["start"], "test_end": d["period"]["end"],
                         "trades": 0, "metrics": {"profit_factor": None, "win_rate": 0.0}}]
    jsonschema.validate(d, json.loads(SCHEMA.read_text()))
