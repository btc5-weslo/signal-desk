"""Parity: signals_series / generate_range vs generate() at each as_of.

Also runs the QA lookahead gate against the vectorized path (a generate-shaped
wrapper around signals_series). Real BTC 1h / 4h is skipped when the store
is missing or SIGNAL_DATA_DIR is unset.
"""

from __future__ import annotations

import pandas as pd
import pytest

from signal_quant.audit_lookahead import (
    MIN_EMIT_AS_OF,
    _PROCESS,
    _full_mapping,
    _as_of_for_strategy,
    count_emitting,
    run_gate_on_strategy,
)
from signal_quant.bars import ensure_utc_index, to_utc
from signal_quant.data_loader import (
    DataDirError,
    resolve_data_dir,
    series_path,
    load_bars_by_timeframe,
)
from signal_quant.registry import generate_range, get_strategy, list_strategies
from signal_quant.strategies import BASELINE
from signal_quant.synthetic import make_synthetic_ohlcv

N_AS_OF = 200
# History kept before the first compared as_of so both paths share the same warmup.
HISTORY_BARS = 500


def _fields(sig) -> tuple:
    side = sig.side.value if hasattr(sig.side, "value") else str(sig.side)
    tps = tuple(float(x) for x in (sig.take_profit or []))
    entry = None if sig.entry is None else float(sig.entry)
    stop = None if sig.stop_loss is None else float(sig.stop_loss)
    return (side, entry, stop, tps, int(sig.horizon_bars), float(sig.confidence))


def _index_by_close(signals) -> dict:
    out: dict = {}
    for s in signals:
        out.setdefault(to_utc(s.bar_close_time), []).append(s)
    return out


def assert_parity(strategy, mapping: dict, as_ofs: list, timeframe: str) -> dict:
    """Compare signals_series over [first, last] to generate() at each as_of."""
    assert len(as_ofs) >= N_AS_OF, len(as_ofs)
    start, end = as_ofs[0], as_ofs[-1]
    series = strategy.signals_series(mapping, start, end, timeframe=timeframe)
    by = _index_by_close(series)
    n_emit = 0
    for t in as_ofs:
        expected = strategy.generate(mapping, t)
        got = by.get(to_utc(t), [])
        assert [_fields(s) for s in got] == [_fields(s) for s in expected], (
            strategy.strategy_id,
            timeframe,
            to_utc(t),
            [_fields(s) for s in got],
            [_fields(s) for s in expected],
        )
        if expected:
            n_emit += 1
    return {"n_as_of": len(as_ofs), "n_emit": n_emit, "n_series": len(series)}


class _SeriesAsGenerate:
    """Adapter so the QA gate can call signals_series as generate(bars, as_of)."""

    def __init__(self, strat, timeframe: str) -> None:
        self._strat = strat
        self._tf = timeframe

    def generate(self, bars_by_timeframe, as_of):
        return self._strat.signals_series(
            bars_by_timeframe, as_of, as_of, timeframe=self._tf
        )


def _synthetic_mapping(sid: str, timeframe: str = "15m", n: int = 800):
    df = make_synthetic_ohlcv(
        n, timeframe=timeframe, seed=11, process=_PROCESS[sid]
    )
    if timeframe == "15m":
        return _full_mapping(df)
    # Provide a matching HTF for MTF on 1h / 4h synthetic runs.
    mapping = {timeframe: df}
    if timeframe == "1h":
        mapping["4h"] = make_synthetic_ohlcv(
            max(n // 4, 200), timeframe="4h", seed=11, process=_PROCESS[sid]
        )
    elif timeframe == "4h":
        mapping["1d"] = make_synthetic_ohlcv(
            max(n // 6, 200), timeframe="1d", seed=11, process=_PROCESS[sid]
        )
    return mapping


def test_signals_series_parity_on_synthetic():
    # Enough bars for warmup + 200 consecutive closes.
    n_bars = HISTORY_BARS + N_AS_OF + 50
    summary = {}
    for sid, cls in BASELINE.items():
        for tf in ("15m", "1h"):
            if tf == "1d" and sid == "mtf_confirmation":
                continue
            mapping = _synthetic_mapping(sid, tf, n=n_bars)
            trig = ensure_utc_index(mapping[tf])
            as_ofs = list(trig.index[-(N_AS_OF):])
            strat = cls(symbol="BTC-USDT", asset_class="crypto", is_mock=True)
            summary[(sid, tf)] = assert_parity(strat, mapping, as_ofs, tf)
    # Recorded for the run report; no performance claim.
    assert all(v["n_as_of"] >= N_AS_OF for v in summary.values())


def test_generate_range_parity_on_synthetic():
    n_bars = HISTORY_BARS + N_AS_OF + 50
    sid = "trend_ema_adx"
    tf = "15m"
    mapping = _synthetic_mapping(sid, tf, n=n_bars)
    trig = ensure_utc_index(mapping[tf])
    as_ofs = list(trig.index[-N_AS_OF:])
    start, end = as_ofs[0], as_ofs[-1]

    def loader(symbol, timeframes, as_of, lookback_bars, **kwargs):
        return {k: mapping[k] for k in timeframes if k in mapping}

    ranged = generate_range(
        sid,
        "BTC-USDT",
        "crypto",
        tf,
        start,
        end,
        loader=loader,
    )
    strat = get_strategy(sid)(symbol="BTC-USDT", asset_class="crypto", is_mock=True)
    by = _index_by_close(ranged)
    for t in as_ofs:
        expected = strat.generate(mapping, t)
        got = by.get(to_utc(t), [])
        assert [_fields(s) for s in got] == [_fields(s) for s in expected]


def test_signals_series_lookahead_gate_on_synthetic():
    results = {}
    for sid, cls in BASELINE.items():
        mapping = _synthetic_mapping(sid, "15m", n=800)
        strat = cls(symbol="BTC-USDT", asset_class="crypto", is_mock=True)
        as_ofs = _as_of_for_strategy(strat, mapping, warmup=80, n=80)
        adapter = _SeriesAsGenerate(strat, "15m")
        fails = run_gate_on_strategy(adapter, mapping, as_ofs, seed=11)
        n_emits = count_emitting(adapter, mapping, as_ofs)
        results[sid] = {"pass": not fails, "failures": fails, "n_emitting": n_emits}
        lookahead_failed = [
            (a, k)
            for a, k in fails
            if "insufficient_signals_for_lookahead" not in str(k)
        ]
        assert not lookahead_failed, (sid, lookahead_failed)
        if n_emits < MIN_EMIT_AS_OF:
            assert any(
                "insufficient_signals_for_lookahead" in str(k) for _, k in fails
            ), (sid, fails)
        else:
            assert not fails, (sid, fails)
    assert sum(r["n_emitting"] for r in results.values()) > 0


def _real_btc_or_skip(timeframe: str) -> tuple:
    try:
        data_dir = resolve_data_dir(required=True)
    except DataDirError:
        pytest.skip("SIGNAL_DATA_DIR unset; skipping real BTC parity")
    need = [timeframe]
    if timeframe == "1h":
        need.append("4h")
    elif timeframe == "4h":
        need.append("1d")
    for tf in need:
        path = series_path("crypto", "BTC-USDT", tf, data_dir=data_dir)
        if not path.exists():
            pytest.skip(f"store missing {path.name}")
    bars = load_bars_by_timeframe(
        "crypto", "BTC-USDT", timeframes=need, data_dir=data_dir
    )
    trig = ensure_utc_index(bars[timeframe])
    if len(trig) < HISTORY_BARS + N_AS_OF:
        pytest.skip(f"not enough BTC-USDT {timeframe} bars for parity")
    end_i = len(trig) - 1
    first_as_of_i = end_i - (N_AS_OF - 1)
    hist_i = max(0, first_as_of_i - HISTORY_BARS)
    cut_start, cut_end = trig.index[hist_i], trig.index[end_i]
    mapping = {}
    for tf, df in bars.items():
        df = ensure_utc_index(df)
        mapping[tf] = df.loc[(df.index >= cut_start) & (df.index <= cut_end)]
    as_ofs = list(trig.index[first_as_of_i : end_i + 1])
    return mapping, as_ofs, data_dir


@pytest.mark.parametrize("timeframe", ["1h", "4h"])
def test_signals_series_and_generate_range_parity_on_real_btc(timeframe):
    mapping, as_ofs, _data_dir = _real_btc_or_skip(timeframe)
    start, end = as_ofs[0], as_ofs[-1]

    def loader(symbol, timeframes, as_of, lookback_bars, **kwargs):
        return {k: mapping[k] for k in timeframes if k in mapping}

    summary = {}
    for sid, cls in BASELINE.items():
        strat = cls(symbol="BTC-USDT", asset_class="crypto")
        series = strat.signals_series(mapping, start, end, timeframe=timeframe)
        ranged = generate_range(
            sid, "BTC-USDT", "crypto", timeframe, start, end, loader=loader
        )
        by_s = _index_by_close(series)
        by_r = _index_by_close(ranged)
        n_emit = 0
        for t in as_ofs:
            expected = strat.generate(mapping, t)
            exp_f = [_fields(s) for s in expected]
            assert [_fields(s) for s in by_s.get(to_utc(t), [])] == exp_f, (sid, "series", to_utc(t))
            assert [_fields(s) for s in by_r.get(to_utc(t), [])] == exp_f, (sid, "range", to_utc(t))
            if expected:
                n_emit += 1
        summary[sid] = {"n_as_of": len(as_ofs), "n_emit": n_emit}
    assert all(v["n_as_of"] >= N_AS_OF for v in summary.values())


def test_list_strategies_still_discoverable():
    ids = {cls.strategy_id for cls in list_strategies()}
    assert ids == set(BASELINE)
