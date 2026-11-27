"""Run QA's mandatory generate() lookahead gate on the v0 baseline strategies.

Uses SYNTHETIC bars only (unless called with a provided mapping). Reports
pass/fail; does not compute performance.

A strategy+timeframe that emits on fewer than ``MIN_EMIT_AS_OF`` (10) of the
sampled as_of points FAILs with ``insufficient_signals_for_lookahead (n=…)``.
A 0-emit run is never a PASS. Sampling may use up to ``MAX_SAMPLED_AS_OF``
closes; strategy parameters are not changed to manufacture signals.

Usage:  python -m signal_quant.audit_lookahead
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from signal_quant.bars import bars_by_timeframe_from_base, infer_timeframe
from signal_quant.strategies import BASELINE
from signal_quant.synthetic import make_synthetic_ohlcv

QA_AUDITS = Path(__file__).resolve().parents[2] / "qa" / "audits"
MIN_EMIT_AS_OF = 10
MAX_SAMPLED_AS_OF = 2000
DEFAULT_WARMUP = 80
# Processes chosen so each baseline has a chance to emit on the synthetic path.
_PROCESS = {
    "trend_ema_adx": "trend",
    "mean_reversion_rsi_bb": "range",
    "breakout_donchian": "breakout",
    "mtf_confirmation": "trend",
}


def _import_gate():
    if str(QA_AUDITS.parent) not in sys.path:
        sys.path.insert(0, str(QA_AUDITS.parent))
    from audits.lookahead_generate import KEYS, lookahead_gate  # type: ignore

    return lookahead_gate, KEYS


def _full_mapping(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    as_of = df["close_time"].iloc[-1] if "close_time" in df.columns else df.index[-1]
    return bars_by_timeframe_from_base(df, as_of, infer_timeframe(df), asset_class="crypto")


def _trigger_times(mapping: dict[str, pd.DataFrame], *, warmup: int = DEFAULT_WARMUP) -> list:
    base_tf = min(mapping, key=lambda tf: {"15m": 0, "1h": 1, "4h": 2, "1d": 3}.get(tf, 9))
    df = mapping[base_tf]
    times = df["close_time"] if "close_time" in df.columns else df.index
    times = list(times.iloc[warmup:]) if hasattr(times, "iloc") else list(times[warmup:])
    return times


def _as_of_samples(
    mapping: dict[str, pd.DataFrame],
    *,
    warmup: int = DEFAULT_WARMUP,
    n: int = MAX_SAMPLED_AS_OF,
) -> list:
    """Evenly sample up to ``n`` trigger-TF closes after warmup (all, if fewer)."""
    times = _trigger_times(mapping, warmup=warmup)
    if not times:
        return []
    if len(times) <= n:
        return list(times)
    idx = np.linspace(0, len(times) - 1, num=n, dtype=int)
    # unique, order-preserving
    seen: set[int] = set()
    out = []
    for i in idx:
        ii = int(i)
        if ii not in seen:
            seen.add(ii)
            out.append(times[ii])
    return out


def _as_of_for_strategy(
    strategy,
    mapping: dict[str, pd.DataFrame],
    *,
    warmup: int = DEFAULT_WARMUP,
    n: int = MAX_SAMPLED_AS_OF,
) -> list:
    """Wide sample of closes (up to ``n``) so the min-signal rule can be met honestly."""
    return _as_of_samples(mapping, warmup=warmup, n=n)


def _is_live(sigs) -> bool:
    for s in sigs or []:
        side = s.side.value if hasattr(s.side, "value") else s.side
        if side and side != "flat":
            return True
    return False


def count_emitting(strategy, mapping: dict[str, pd.DataFrame], as_of_list: Iterable) -> int:
    n = 0
    for t in as_of_list:
        as_of = t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
        if _is_live(strategy.generate(mapping, as_of)):
            n += 1
    return n


def run_gate_on_strategy(
    strategy,
    bars_by_timeframe: dict[str, pd.DataFrame],
    as_of_list: Iterable,
    *,
    seed: int = 0,
) -> list:
    """Run QA's generate() gate, then apply the minimum-signal rule.

    Fewer than ``MIN_EMIT_AS_OF`` emitting as_of points is a FAIL with
    ``insufficient_signals_for_lookahead (n=…)``. A 0-emit run is never PASS.
    """
    as_ofs = list(as_of_list)
    lookahead_gate, _ = _import_gate()
    fails = list(lookahead_gate(strategy.generate, bars_by_timeframe, as_ofs, seed=seed))
    n_emits = count_emitting(strategy, bars_by_timeframe, as_ofs)
    if n_emits < MIN_EMIT_AS_OF:
        marker = as_ofs[-1] if as_ofs else None
        fails.append((marker, f"insufficient_signals_for_lookahead (n={n_emits})"))
    return fails


def run_all_baseline_synthetic(
    *,
    n_bars: int = 800,
    seed: int = 11,
    warmup: int = DEFAULT_WARMUP,
    n_as_of: int = 80,
) -> dict[str, dict]:
    results = {}
    for sid, cls in BASELINE.items():
        df = make_synthetic_ohlcv(n_bars, timeframe="15m", seed=seed, process=_PROCESS[sid])
        mapping = _full_mapping(df)
        strat = cls(symbol="BTC-USDT", asset_class="crypto", is_mock=True)
        as_ofs = _as_of_for_strategy(strat, mapping, warmup=warmup, n=n_as_of)
        fails = run_gate_on_strategy(strat, mapping, as_ofs, seed=seed)
        n_emits = count_emitting(strat, mapping, as_ofs)
        results[sid] = {
            "pass": not fails,
            "failures": fails,
            "n_as_of": len(as_ofs),
            "n_emitting": n_emits,
            "synthetic": True,
        }
    return results


def inspect_gate_keys() -> tuple[tuple[str, ...], list[str]]:
    """Return (compared keys, Signal fields the gate does not compare)."""
    _, keys = _import_gate()
    from signal_quant.models import Signal

    all_fields = tuple(Signal.model_fields.keys())
    missed = [f for f in all_fields if f not in keys]
    return tuple(keys), missed


def main() -> int:
    keys, missed = inspect_gate_keys()
    print("=== QA lookahead_generate gate (SYNTHETIC data) ===")
    print(f"Compared keys: {', '.join(keys)}")
    print(f"Not compared: {', '.join(missed)}")
    print(f"Min emitting as_of: {MIN_EMIT_AS_OF} (0-emit is FAIL)")
    results = run_all_baseline_synthetic()
    rc = 0
    for sid, r in results.items():
        status = "PASS" if r["pass"] else "FAIL"
        if not r["pass"]:
            rc = 1
        print(
            f"  {sid}: {status}  "
            f"({r['n_emitting']}/{r['n_as_of']} sampled as_of emitted a signal; SYNTHETIC)"
        )
        for as_of, kind in r["failures"]:
            print(f"      failure at {as_of} ({kind})")
    print("=== end gate ===")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
