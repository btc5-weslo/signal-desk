"""Package-level smoke on synthetic data (no market data, no performance claims)."""

from __future__ import annotations

from signal_quant.smoke import main


def test_smoke_main_exits_zero():
    assert main() == 0


def test_smoke_gate_exits_nonzero_on_fail(monkeypatch):
    """``smoke --gate`` must exit non-zero when any strategy/timeframe FAILs.

    This does not run the full real-store smoke (see test_smoke_main_exits_zero
    and ``-k not smoke_main``). The gate path is exercised with stubs.
    """
    from signal_quant import smoke

    monkeypatch.setattr(smoke, "_synthetic", lambda: None)

    monkeypatch.setattr(
        smoke,
        "_real_store_execute_only",
        lambda *, run_gate=False, data_dir=None: 1 if run_gate else 0,
    )
    assert smoke.main(["--gate"]) != 0
    assert smoke.main([]) == 0


def test_smoke_gate_exits_zero_when_all_pass(monkeypatch):
    from signal_quant import smoke

    monkeypatch.setattr(smoke, "_synthetic", lambda: None)
    monkeypatch.setattr(
        smoke,
        "_real_store_execute_only",
        lambda *, run_gate=False, data_dir=None: 0,
    )
    assert smoke.main(["--gate"]) == 0


def test_real_btc_gate_counts_failures_and_main_propagates(monkeypatch):
    """A FAIL from run_gate_on_strategy increments the count and exits 1."""
    from signal_quant import smoke
    from signal_quant.synthetic import make_synthetic_ohlcv

    monkeypatch.setattr(smoke, "_synthetic", lambda: None)

    df_1h = make_synthetic_ohlcv(120, timeframe="1h", seed=1, process="trend")
    df_4h = make_synthetic_ohlcv(80, timeframe="4h", seed=1, process="trend")
    df_1d = make_synthetic_ohlcv(80, timeframe="1d", seed=1, process="trend")

    def fake_load(ac, symbol, *, timeframes=None, as_of=None, data_dir=None, **kw):
        frames = {"1h": df_1h, "4h": df_4h, "1d": df_1d}
        return {tf: frames[tf] for tf in (timeframes or []) if tf in frames}

    monkeypatch.setattr(smoke, "load_bars_by_timeframe", fake_load)

    import signal_quant.audit_lookahead as al

    def short_as_of(strategy, mapping, **kwargs):
        trig = mapping.get("1h", mapping.get("4h"))
        return list(trig.index[-5:])

    def always_fail(strategy, bars_by_timeframe, as_of_list, *, seed=0):
        as_ofs = list(as_of_list)
        return [(as_ofs[-1] if as_ofs else None, "forced_fail")]

    monkeypatch.setattr(al, "_as_of_for_strategy", short_as_of)
    monkeypatch.setattr(al, "run_gate_on_strategy", always_fail)

    def fake_real(*, run_gate=False, data_dir=None):
        return smoke._real_btc_gate(data_dir=data_dir) if run_gate else 0

    monkeypatch.setattr(smoke, "_real_store_execute_only", fake_real)
    assert smoke.main(["--gate", "--data-dir", "unused"]) != 0
