import numpy as np, pandas as pd, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "audits"))
from lookahead import truncation_test
def _df(n=600):
    rng = np.random.default_rng(1); c = 100 + rng.standard_normal(n).cumsum()
    return pd.DataFrame({"close": c}, index=pd.date_range("2024-01-01", periods=n, freq="h"))
def clean(df):
    ma = df.close.rolling(20).mean()
    return pd.DataFrame({"side": np.where(df.close > ma, "long", "flat")}, index=df.index)
def leaky(df):
    fut = df.close.shift(-1)
    return pd.DataFrame({"side": np.where(fut > df.close, "long", "flat")}, index=df.index)
def test_clean_passes(): assert truncation_test(clean, _df()) == []
def test_leaky_caught(): assert truncation_test(leaky, _df()) != []
from lookahead_generate import lookahead_gate
def _bars():
    df = _df(); return {"1h": df.assign(close_time=df.index)}
def gen_clean(bars, as_of):
    d = bars["1h"]; d = d[d.close_time <= as_of]
    return [{"side": "long" if d.close.iloc[-1] > d.close.tail(20).mean() else "flat"}]
def gen_leaky(bars, as_of):
    d = bars["1h"]; return [{"side": "long" if d.close.iloc[-1] > d.close.mean() else "flat"}]
def test_gate_clean():
    b = _bars(); assert lookahead_gate(gen_clean, b, list(b["1h"].index[300:600:30]), validator=None) == []
def test_gate_leaky():
    b = _bars(); assert lookahead_gate(gen_leaky, b, list(b["1h"].index[300:600:30]), validator=None) != []
def gen_conf_leak(bars, as_of):
    d = bars["1h"]; past = d[d.close_time <= as_of]
    return [{"side": "flat", "confidence": float(d.close.iloc[-1] / 1000), "features_snapshot": {"c": float(past.close.iloc[-1])}}]
def test_gate_catches_confidence_leak():
    b = _bars(); assert lookahead_gate(gen_conf_leak, b, list(b["1h"].index[300:599:30]), validator=None) != []
def gen_bad_time(bars, as_of):
    return [{"side": "flat", "bar_close_time": as_of + pd.Timedelta(hours=1), "generated_at": as_of}]
def test_gate_catches_future_bar_close_time():
    b = _bars(); f = lookahead_gate(gen_bad_time, b, list(b["1h"].index[300:599:60]), validator=None)
    assert any("bar_close_time > as_of" in r for _, r in f)
def test_gate_flags_contract_violation_when_shared_available():
    import pytest
    pytest.importorskip("signal_shared")
    b = _bars(); f = lookahead_gate(gen_clean, b, list(b["1h"].index[300:600:100]))
    assert any(r.startswith("contract:") for _, r in f)
