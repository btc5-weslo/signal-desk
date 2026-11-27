"""Smoke-run the baseline strategies on SYNTHETIC data only (plus an optional
execute-only pass on real store files if any exist).

This is not a backtest and reports no accuracy or returns.
Usage:  python -m signal_quant.smoke
        python -m signal_quant.smoke --gate --data-dir DIR
"""

from __future__ import annotations

import sys

from signal_quant.adapters import as_frame
from signal_quant.bars import bars_by_timeframe_from_base, infer_timeframe
from signal_quant.data_loader import (
    list_available_series,
    load_bars_by_timeframe,
    load_series,
    resolve_data_dir,
)
from signal_quant.labeling import label_triple_barrier
from signal_quant.masks import is_stale
from signal_quant.models import Signal
from signal_quant.strategies import BASELINE
from signal_quant.synthetic import make_synthetic_ohlcv
from signal_quant.audit_lookahead import DEFAULT_WARMUP, MAX_SAMPLED_AS_OF
from signal_quant.strategy import LOOKBACK_BARS
from signal_quant.walkforward import expanding_walk_forward

# Recent window: warmup + up to MAX_SAMPLED_AS_OF closes (not the full history).

_REAL_WINDOW = DEFAULT_WARMUP + MAX_SAMPLED_AS_OF

# Current crypto Parquet files were pulled from Binance.US and are PROVISIONAL.
# Data is re-pulling from Binance global / OKX / Bybit. Counts below are
# execute-only checks that the code runs; they are not a data-quality sign-off.
_PROVISIONAL_WARNING = (
    "Store files are read-only and may be mid-backfill. Each line reports the "
    "actual distinct source values on that series, plus 'provisional' if any "
    "source is in the never-licensed set. A changed date range is not a failure. "
    "Execute-only; no performance metrics."
)


def _synthetic() -> None:
    print("=== signal-quant smoke test: SYNTHETIC DATA ONLY ===")
    print("No market data is used in this block. Do not treat output as accuracy or returns.")
    processes = {
        "trend_ema_adx": "trend",
        "mean_reversion_rsi_bb": "range",
        "breakout_donchian": "breakout",
        "mtf_confirmation": "trend",
    }
    df = None
    for sid, cls in BASELINE.items():
        df = make_synthetic_ohlcv(320, timeframe="15m", seed=11, process=processes[sid])
        strat = cls(symbol="BTC-USDT", asset_class="crypto", is_mock=True)
        as_of = df.index[-1].to_pydatetime()
        mapping = bars_by_timeframe_from_base(df, as_of, infer_timeframe(df), asset_class="crypto")
        signals = strat.generate(mapping, as_of)
        for s in signals:
            assert isinstance(s, Signal)
            assert s.is_mock is True
            assert s.symbol == "BTC-USDT"
            assert s.confidence_calibrated is False
        frame = as_frame(strat, df, warmup=60)
        n_active = int((frame["side"] != "flat").sum())
        print(
            f"  {sid}: generate() at last bar emitted {len(signals)} Signal(s); "
            f"as_frame replayed {len(frame)} synthetic bars, "
            f"{n_active} non-flat (SYNTHETIC, is_mock=True)."
        )
    assert df is not None
    windows = expanding_walk_forward(
        df.index, n_windows=3, train_min_bars=120, test_bars=40, horizon_bars=16
    )
    print(f"  walk-forward: {len(windows)} expanding windows on the synthetic index.")
    mid = 200
    lab = label_triple_barrier(
        df,
        signal_index=mid,
        side="long",
        stop_loss=float(df["close"].iloc[mid] * 0.98),
        take_profit=[float(df["close"].iloc[mid] * 1.02)],
        horizon_bars=8,
    )
    print(f"  triple-barrier on one synthetic example: outcome={lab['outcome']} (SYNTHETIC).")


def _fmt_utc(ts) -> str:
    if ts is None or (hasattr(ts, "__bool__") is False and ts != ts):
        return "n/a"
    try:
        import pandas as pd
        if pd.isna(ts):
            return "n/a"
        t = pd.Timestamp(ts)
    except Exception:
        return str(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.strftime("%Y-%m-%d %H:%M:%S UTC")


def _is_never_licensed(source: str) -> bool:
    """True if this source value is in the never-licensed set."""
    s = str(source)
    if s in {"binance_vision", "yfinance"}:
        return True
    if s.startswith("ccxt:"):
        return True
    return False


def _source_label(df) -> str:
    if df is None or df.empty or "source" not in df.columns:
        return "source=(missing column)"
    vals = df["source"].dropna().astype(str)
    if vals.empty:
        return "source=(null)"
    counts = vals.value_counts()
    if len(counts) == 1:
        body = str(counts.index[0])
    else:
        body = ", ".join(f"{name}({int(n)})" for name, n in counts.items())
    if any(_is_never_licensed(s) for s in counts.index):
        return f"source={body}; provisional"
    return f"source={body}"


def _sources_from_mapping(mapping: dict) -> str:
    """Distinct source values actually present in the frames used for a gate run."""
    found: list[str] = []
    seen: set[str] = set()
    licensed_hit = False
    for df in (mapping or {}).values():
        if df is None or len(df) == 0 or "source" not in df.columns:
            continue
        for val in df["source"].dropna().astype(str).unique():
            if val not in seen:
                seen.add(val)
                found.append(val)
            if _is_never_licensed(val):
                licensed_hit = True
    if not found:
        body = "source=(missing column)"
    else:
        body = "source=" + ", ".join(sorted(found))
    if licensed_hit:
        return f"{body}; provisional"
    return body


def _real_store_execute_only(*, run_gate: bool = False, data_dir=None) -> int:
    """If Data has written any Parquet, just confirm generate() runs. No metrics."""
    if data_dir is None:
        print("  real store: skipped (no --data-dir and SIGNAL_DATA_DIR is unset).")
        return 0
    available = list_available_series(data_dir=data_dir)
    if not available:
        print("  real store: no Parquet files under the given data_dir (skipped).")
        return 0
    print(_PROVISIONAL_WARNING)
    print(
        f"  real store: {len(available)} series present; execute-only generate() "
        "(no performance metrics)."
    )
    # Per-file bar counts and stale / placeholder masks.
    for ac, symbol, tf, path in available:
        df = load_series(ac, symbol, tf, data_dir=data_dir)
        n = 0 if df is None else len(df)
        n_stale = 0
        src = "source=(empty)"
        first_open = first_close = last_open = last_close = "n/a"
        if df is not None and n:
            n_stale = int(is_stale(df).sum())
            src = _source_label(df)
            if "open_time" in df.columns:
                first_open = _fmt_utc(df["open_time"].min())
                last_open = _fmt_utc(df["open_time"].max())
            if "close_time" in df.columns:
                first_close = _fmt_utc(df["close_time"].min())
                last_close = _fmt_utc(df["close_time"].max())
            else:
                first_close = _fmt_utc(df.index.min())
                last_close = _fmt_utc(df.index.max())
        print(
            f"    {ac}/{symbol}/{tf}: {n} bars, {n_stale} stale/placeholder masked, "
            f"{src}, first open {first_open} / close {first_close}, "
            f"last open {last_open} / close {last_close} ({path.name})"
        )

    # Group by (asset_class, symbol) and run generate() at the last close.
    pairs = sorted({(a, s) for a, s, _, _ in available})
    for ac, symbol in pairs:
        tfs = sorted({tf for a, s, tf, _ in available if a == ac and s == symbol})
        mapping = load_bars_by_timeframe(ac, symbol, timeframes=tfs, data_dir=data_dir)
        nonempty = {tf: df for tf, df in mapping.items() if df is not None and len(df)}
        if not nonempty:
            print(f"    {ac}/{symbol}: series on disk were empty (skipped).")
            continue
        last = max(df["close_time"].max() for df in nonempty.values())
        as_of = last.to_pydatetime() if hasattr(last, "to_pydatetime") else last
        window = {tf: df.tail(_REAL_WINDOW) for tf, df in nonempty.items()}
        for sid, cls in BASELINE.items():
            strat = cls(symbol=symbol, asset_class=ac, is_mock=False)
            sigs = strat.generate(window, as_of)
            for s in sigs:
                Signal.model_validate(s.model_dump())
                assert s.symbol == symbol
                assert s.is_mock is False
                assert s.confidence_calibrated is False
            print(
                f"    {sid} on {ac}/{symbol} at last close: "
                f"generate() returned {len(sigs)} Signal(s). No metrics computed."
            )

    if run_gate:
        return _real_btc_gate(data_dir=data_dir)
    return 0


def _diagnose_mean_reversion(strat, mapping, as_ofs) -> str:
    """Count how often H2's RSI + Bollinger rule held vs why it still did not emit.

    Does not change strategy parameters. No performance metrics.
    """
    from signal_quant.bars import truncate_all
    from signal_quant.strategy import context_from_bars
    from signal_quant.strategies.common import last_bar_context

    n = 0
    n_rsi_bb = 0
    n_blocked_regime = 0
    n_blocked_high_vol = 0
    n_emitted = 0
    rsi_low = getattr(strat, "rsi_low", 30.0)
    rsi_high = getattr(strat, "rsi_high", 70.0)
    for t in as_ofs:
        as_of = t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
        try:
            window = truncate_all(mapping, as_of)
            _tf, bars = context_from_bars(window, as_of)
        except ValueError:
            continue
        ctx = last_bar_context(bars)
        if ctx is None:
            continue
        n += 1
        rsi = ctx.features.get("rsi")
        pct_b = ctx.features.get("bb_pct_b")
        import pandas as pd

        if rsi is None or pct_b is None or pd.isna(rsi) or pd.isna(pct_b):
            continue
        cond = (float(rsi) <= rsi_low and float(pct_b) <= 0.0) or (
            float(rsi) >= rsi_high and float(pct_b) >= 1.0
        )
        if not cond:
            continue
        n_rsi_bb += 1
        if ctx.high_vol:
            n_blocked_high_vol += 1
        if ctx.regime not in ("range", "unknown"):
            n_blocked_regime += 1
        sigs = strat.generate(mapping, as_of)
        if any((s.side.value if hasattr(s.side, "value") else s.side) != "flat" for s in (sigs or [])):
            n_emitted += 1
    return (
        f"H2 diagnosis on {n} scored as_of: RSI+Bollinger both held on {n_rsi_bb}; "
        f"of those, blocked by non-range regime={n_blocked_regime}, "
        f"blocked by high_vol={n_blocked_high_vol}, emitted={n_emitted}. "
        "Strategy parameters were not changed."
    )


def _real_btc_gate(*, data_dir) -> int:
    """QA generate() lookahead gate on provisional BTC-USDT 1h and 4h. No metrics."""
    from signal_quant.audit_lookahead import _as_of_for_strategy, count_emitting, run_gate_on_strategy

    n_fail = 0
    print("  QA lookahead_generate gate on BTC-USDT 1h and 4h (read-only; no metrics):")
    for trigger in ("1h", "4h"):
        need = [trigger]
        if trigger == "1h":
            need += ["4h", "1d"]
        else:
            need += ["1d"]
        mapping = load_bars_by_timeframe("crypto", "BTC-USDT", timeframes=need, data_dir=data_dir)
        mapping = {tf: df for tf, df in mapping.items() if df is not None and len(df)}
        if trigger not in mapping:
            print(f"    BTC-USDT {trigger}: missing in store (skipped).")
            continue
        # Gate on a recent window (full history is tens of thousands of bars).
        trig = mapping[trigger].tail(_REAL_WINDOW)
        cut = trig.index[0]
        mapping[trigger] = trig
        for tf, df in list(mapping.items()):
            if tf == trigger:
                continue
            mapping[tf] = df[df.index >= cut].copy() if len(df) else df
            if mapping[tf] is not None and len(mapping[tf]) < LOOKBACK_BARS:
                mapping[tf] = df.tail(LOOKBACK_BARS)
        for sid, cls in BASELINE.items():
            # MTF on 4h needs 1d; on 1h needs 4h. If HTF is missing, generate emits nothing
            # and the gate can still pass (no invented signals from future bars).
            strat = cls(symbol="BTC-USDT", asset_class="crypto", is_mock=False)
            as_ofs = _as_of_for_strategy(strat, {trigger: mapping[trigger], **mapping})
            fails = run_gate_on_strategy(strat, mapping, as_ofs, seed=0)
            n_emits = 0
            for t in as_ofs:
                as_of = t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
                sigs = strat.generate(mapping, as_of)
                if any((s.side.value if hasattr(s.side, "value") else s.side) != "flat" for s in sigs):
                    n_emits += 1
                    for s in sigs:
                        Signal.model_validate(s.model_dump())
            status = "PASS" if not fails else "FAIL"
            if fails:
                n_fail += 1
            src = _sources_from_mapping(mapping)
            print(
                f"    {sid} BTC-USDT {trigger}: {status}  "
                f"({n_emits}/{len(as_ofs)} sampled as_of emitted; {src}). "
                "No metrics computed."
            )
            if fails:
                for as_of, kind in fails:
                    print(f"      failure at {as_of} ({kind})")
            if sid == "mean_reversion_rsi_bb" and n_emits < 10:
                print("      " + _diagnose_mean_reversion(strat, mapping, as_ofs))
    return n_fail


def main(argv: list[str] | None = None) -> int:
    # Default is no CLI flags so pytest can call main() safely (synthetic only).
    argv = [] if argv is None else list(argv)
    run_gate = "--gate" in argv
    data_dir = None
    if "--data-dir" in argv:
        i = argv.index("--data-dir")
        if i + 1 >= len(argv):
            raise SystemExit("smoke: --data-dir requires a path argument")
        data_dir = argv[i + 1]
    data_dir = resolve_data_dir(data_dir, required=False)
    _synthetic()
    n_fail = _real_store_execute_only(run_gate=run_gate, data_dir=data_dir)
    print("=== smoke test finished ===")
    if run_gate and n_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
