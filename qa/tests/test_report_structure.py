import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("brc", Path(__file__).parents[1] / "audits" / "backtest_report_check.py")
brc = importlib.util.module_from_spec(spec); spec.loader.exec_module(brc)
T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _report(offsets_per_window, n_windows=6):
    wins, trades = [], []
    for w in range(n_windows):
        a = T0 + timedelta(days=180 * w)
        offs = offsets_per_window[w % len(offsets_per_window)]
        wins.append({"train_start": iso(a - timedelta(days=365)), "train_end": iso(a), "test_start": iso(a),
                     "test_end": iso(a + timedelta(days=180)), "trades": len(offs), "metrics": {"profit_factor": 1.1}})
        for i, d in enumerate(offs):
            e = a + timedelta(days=d)
            trades.append({"symbol": "BTC-USDT", "entry_time": iso(e), "exit_time": iso(e + timedelta(days=1)),
                           "net_return": 0.01 if i % 2 else -0.01})
    return {"oos_windows": wins, "trade_count": len(trades)}, trades


def test_spread_trades_pass():
    r, tr = _report([[5, 40, 80, 120, 170], [10, 60, 100, 150]])
    assert brc.structure_errors(r, tr) == []


def test_bunched_and_capped_trades_fail():
    r, tr = _report([[1, 3]])
    errs = " ".join(brc.structure_errors(r, tr))
    assert "bunched at window starts" in errs and "exactly 2 trades" in errs


def test_sentinel_metric_fails():
    r, tr = _report([[5, 40, 80, 120, 170], [10, 60, 100, 150]])
    r["oos_windows"][0]["metrics"]["profit_factor"] = 1000000.0
    assert any("sentinel" in e for e in brc.structure_errors(r, tr))


def test_overlapping_trades_fail():
    r, tr = _report([[5, 5.5, 80, 120, 170], [10, 60, 100, 150]])
    assert any("overlapping" in e for e in brc.structure_errors(r, tr))
