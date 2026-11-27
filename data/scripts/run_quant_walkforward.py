#!/usr/bin/env python3
"""Walk-forward OOS backtests of Quant's baseline strategies (v2, 2026-11-26).

v2 replaces the withdrawn reports/oos_quant/ run (see WITHDRAWN.md there):

- Signals come only from the product code path: ``signal_quant.registry.generate_range``
  (Quant's official vectorized equivalent of ``Strategy.generate``). There is
  no monkeypatching and no 2-bar ``signals_at`` slicing. If ``generate_range``
  is missing the run FAILS (no fallback). Each combo is also spot-checked
  against ``signal_quant.registry.run_for_bar`` (the live per-bar path,
  ``Strategy.generate`` on load_closed lookback frames); any mismatch fails
  the combo.
- Each trade is scored by ``signal_data.barriers.resolve`` with the signal's
  own ``horizon_bars`` (engine.run_backtest). No hard-coded horizon.
- Position state: one position at a time per symbol, carried across windows.
- A signal must fill inside its test window: signals at the last bar of a
  window (fill would be at/after test_end) are not taken. A trade opened in
  the window may exit after test_end; bars after the window (same contiguous
  segment only) are supplied up to the signal's horizon so it resolves exactly
  as the live tracker would. A trade that still cannot resolve (end of data or
  a gap) is dropped and counted (``dropped_open_at_end``).
- Undefined PF / Sharpe / Sortino are null + ``metric_undefined``.

Parameters are Quant's published defaults (frozen); nothing is fit on train
or OOS data. Fees = 10 bps per side, slippage = 5 bps.
Windows: 365 days train / 180 days test, stepped by 180 days, as bar counts.

Usage:
    python scripts/run_quant_walkforward.py            # all combos, resumable
    python scripts/run_quant_walkforward.py --symbol BTC-USDT --timeframe 1d --strategy breakout_donchian
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
QA_CHECK = ROOT.parent / "qa" / "audits" / "backtest_report_check.py"
SCHEMA_PATH = ROOT.parent / "shared" / "backtest_result.schema.json"
OUT_DIR = ROOT / "reports" / "oos_quant_v2"
RUNNER_VERSION = "v2-2026-11-26"

# A priori, not tuned on OOS results.
FEE_BPS = 10.0
SLIP_BPS = 5.0
TRAIN_DAYS = 365
TEST_DAYS = 180
STEP_DAYS = 180
BARS_PER_DAY = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
PARITY_SAMPLE = 12  # as_of bars per combo re-checked against run_for_bar / generate()
# Levels (entry / stop / targets) may differ by up to ~1e-6 relative (observed) because
# run_for_bar warms indicators on a 200-bar lookback and generate_range on full
# history (Wilder ATR is an EWM). Decisions (bar, side, horizon, count) must match exactly.
PARITY_LEVEL_RTOL = 1e-4
ASSET_CLASS = "crypto"


class MissingQuantFastPath(RuntimeError):
    pass


class ParityError(RuntimeError):
    pass


def require_generate_range():
    """Return Quant's official ``generate_range``. Raise loudly if it is missing (no fallback)."""
    try:
        from signal_quant import registry
    except ImportError as exc:  # pragma: no cover - environment problem
        raise MissingQuantFastPath(f"signal_quant.registry is not importable: {exc}") from exc
    fn = getattr(registry, "generate_range", None)
    if fn is None or not callable(fn):
        raise MissingQuantFastPath(
            "signal_quant.registry.generate_range is missing. The v2 walk-forward runs only "
            "through Quant's official fast path (with its parity test vs generate()); "
            "there is no fallback and no monkeypatch."
        )
    return fn


def store_dir() -> Path:
    from signal_data.paths import get_store_dir

    return get_store_dir()


def load_summary_row(report_path: Path, audit_ok: bool, audit_output: str = "") -> dict:
    r = json.loads(report_path.read_text())
    cfg_path = report_path.parent / "config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    return {
        "status": "ok" if audit_ok else "audit_failed",
        "strategy_id": r.get("strategy_id"),
        "version": r.get("version"),
        "symbol": r.get("symbol"),
        "timeframe": r.get("timeframe"),
        "trade_count": r.get("trade_count"),
        "win_rate": r.get("win_rate"),
        "profit_factor": r.get("profit_factor"),
        "sharpe": r.get("sharpe"),
        "max_drawdown": r.get("max_drawdown"),
        "flags": r.get("flags"),
        "run_id": r.get("run_id"),
        "data_hash": r.get("data_hash"),
        "n_windows": len(r.get("oos_windows") or []),
        "window_trades": [w.get("trades") for w in r.get("oos_windows") or []],
        "entry_position_deciles": cfg.get("entry_position_deciles"),
        "horizon_bars_used": cfg.get("horizon_bars_used"),
        "runtime_s": cfg.get("runtime_s"),
        "path": str(report_path),
        "audit_ok": audit_ok,
        "audit_output": (audit_output or "").strip(),
        "fees_bps": r.get("fees_bps"),
        "slippage_bps": r.get("slippage_bps"),
        "schema_ok": True,
    }


def validate_report_schema(report_path: Path) -> None:
    """Raise if the report JSON does not match shared/backtest_result.schema.json."""
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text())
    instance = json.loads(report_path.read_text())
    jsonschema.validate(instance=instance, schema=schema)


def load_frame(symbol: str, timeframe: str):
    from signal_data.store import candle_path, get_candles

    path = candle_path(symbol, timeframe)
    df = get_candles(symbol, timeframe, drop_stale=True)
    df = df.sort_values("open_time").reset_index(drop=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df, path


def _utc(x) -> pd.Timestamp:
    ts = pd.Timestamp(x)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _sig_key(s) -> tuple:
    side = s.side.value if hasattr(s.side, "value") else str(s.side)
    levels = (float(s.entry), float(s.stop_loss), *[float(x) for x in (s.take_profit or [])])
    return (_utc(s.bar_close_time), side, int(s.horizon_bars), len(s.take_profit or []), levels)


def _same(a: tuple, b: tuple) -> tuple[bool, float]:
    """Exact on (time, side, horizon, n_targets); levels within PARITY_LEVEL_RTOL."""
    if a[:4] != b[:4] or len(a[4]) != len(b[4]):
        return False, float("inf")
    rel = max((abs(x - y) / max(abs(x), abs(y), 1e-12) for x, y in zip(a[4], b[4])), default=0.0)
    return rel <= PARITY_LEVEL_RTOL, rel


def parity_check(strategy_id: str, symbol: str, timeframe: str, sigs: list, test_closes: list, data_dir) -> dict:
    """Spot-check generate_range output against the per-bar product path.

    Samples PARITY_SAMPLE bars where generate_range emitted a signal and the
    same number where it did not (evenly spaced, deterministic), and compares
    with ``run_for_bar`` (Strategy.generate on load_closed lookback frames).
    """
    from signal_quant.registry import run_for_bar

    by_close: dict = {}
    for s in sigs:
        k = _sig_key(s)
        by_close.setdefault(k[0], []).append(k)
    emitted = sorted(by_close)
    quiet = [t for t in test_closes if t not in by_close]

    def pick(xs, n):
        if len(xs) <= n:
            return list(xs)
        step = len(xs) / n
        return [xs[int(i * step)] for i in range(n)]

    sample = pick(emitted, PARITY_SAMPLE) + pick(quiet, PARITY_SAMPLE)
    mismatches = []
    max_rel = 0.0
    for ts in sample:
        live = [s for s in run_for_bar(symbol, ASSET_CLASS, timeframe, ts.to_pydatetime(), data_dir=data_dir)
                if s.strategy_id == strategy_id]
        got = sorted(_sig_key(s) for s in live)
        want = sorted(by_close.get(ts, []))
        ok = len(got) == len(want)
        if ok:
            for g, w in zip(got, want):
                same, rel = _same(g, w)
                max_rel = max(max_rel, rel)
                ok = ok and same
        if not ok:
            mismatches.append({"as_of": ts.isoformat(), "generate": [str(g) for g in got], "generate_range": [str(w) for w in want]})
    res = {"checked": len(sample), "with_signal": min(len(emitted), PARITY_SAMPLE), "mismatches": len(mismatches),
           "max_level_rel_diff": max_rel}
    if mismatches:
        raise ParityError(
            f"generate_range != generate() for {strategy_id} {symbol} {timeframe} at "
            f"{len(mismatches)}/{len(sample)} sampled bars; first: {json.dumps(mismatches[0])}"
        )
    return res


def entry_position_deciles(trades, windows) -> list[int]:
    """Histogram (10 bins) of where in its test window each trade opens."""
    bins = [0] * 10
    for t in trades:
        et = pd.Timestamp(t.entry_time)
        for w in windows:
            a, b = pd.Timestamp(w.test_start), pd.Timestamp(w.test_end)
            if a <= et < b:
                frac = (et - a) / (b - a)
                bins[min(9, int(frac * 10))] += 1
                break
    return bins


def run_one(cls, symbol: str, timeframe: str, generate_range) -> dict:
    from signal_data.backtester.costs import CostModel
    from signal_data.backtester.engine import _build_equity_and_flags, run_backtest
    from signal_data.backtester.flags import compute_flags
    from signal_data.backtester.metrics import UNDEFINABLE, summarize, undefined_metrics
    from signal_data.backtester.walk_forward import rolling_windows
    from signal_data.hashing import data_hash, run_id
    from signal_data.stale import has_large_gaps, large_gap_breaks
    from signal_data.timeutil import to_utc_datetime
    from signal_shared import BacktestReport, OOSWindow

    t0 = time.monotonic()
    supported = getattr(cls, "supported", None)
    if supported is not None and (ASSET_CLASS, timeframe) not in supported:
        return {
            "status": "skipped_unsupported",
            "strategy_id": cls.strategy_id,
            "version": cls.strategy_version,
            "symbol": symbol,
            "timeframe": timeframe,
            "reason": f"{cls.strategy_id} does not support ({ASSET_CLASS}, {timeframe})",
        }

    primary, path = load_frame(symbol, timeframe)
    paths = [path]
    for tf in cls.required_timeframes(timeframe):
        if tf != timeframe:
            from signal_data.store import candle_path

            paths.append(candle_path(symbol, tf))
    data_dir = store_dir()

    train_bars = TRAIN_DAYS * BARS_PER_DAY[timeframe]
    test_bars = TEST_DAYS * BARS_PER_DAY[timeframe]
    step_bars = STEP_DAYS * BARS_PER_DAY[timeframe]
    windows = rolling_windows(primary, train_bars=train_bars, test_bars=test_bars, step_bars=step_bars, timeframe=timeframe)
    breaks = sorted(large_gap_breaks(primary, timeframe))
    closes = pd.DatetimeIndex(primary["close_time"])

    cost = CostModel(fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    oos_audits = []
    oos_windows = []
    horizons: set[int] = set()
    counters = {"signals_total": 0, "signals_skipped_in_position": 0, "signals_at_window_last_bar": 0,
                "dropped_open_at_end": 0}
    parity = {"checked": 0, "with_signal": 0, "mismatches": 0, "max_level_rel_diff": 0.0}
    carry_exit = None  # exit_time of the last trade; positions carry across windows

    for w in windows:
        tr_end, te_end = pd.Timestamp(w.train_end), pd.Timestamp(w.test_end)
        in_win = (closes > tr_end) & (closes <= te_end)
        test_closes = list(closes[in_win])
        if not test_closes:
            oos_windows.append(OOSWindow(train_start=to_utc_datetime(w.train_start), train_end=to_utc_datetime(w.train_end),
                                         test_start=to_utc_datetime(w.test_start), test_end=to_utc_datetime(w.test_end),
                                         trades=0, metrics={}))
            continue
        sigs = list(generate_range(cls.strategy_id, symbol, ASSET_CLASS, timeframe,
                                   test_closes[0].to_pydatetime(), test_closes[-1].to_pydatetime(), data_dir=data_dir))
        for s in sigs:
            bc = pd.Timestamp(s.bar_close_time)
            if not (tr_end < bc <= te_end):
                raise RuntimeError(f"generate_range returned a signal at {bc} outside [{test_closes[0]}, {te_end}]")
        sigs = [s for s in sigs if (s.side.value if hasattr(s.side, "value") else str(s.side)) != "flat"]
        counters["signals_total"] += len(sigs)
        p = parity_check(cls.strategy_id, symbol, timeframe, sigs, test_closes, data_dir)
        for k in ("checked", "with_signal", "mismatches"):
            parity[k] += p[k]
        parity["max_level_rel_diff"] = max(parity["max_level_rel_diff"], p["max_level_rel_diff"])

        # Fill must be inside the window: drop signals on the window's last bar.
        last_close = test_closes[-1]
        at_last = [s for s in sigs if pd.Timestamp(s.bar_close_time) == last_close]
        counters["signals_at_window_last_bar"] += len(at_last)
        sigs = [s for s in sigs if pd.Timestamp(s.bar_close_time) < last_close]
        # Position carried from the previous window.
        if carry_exit is not None:
            held = [s for s in sigs if pd.Timestamp(s.bar_close_time) < carry_exit]
            counters["signals_skipped_in_position"] += len(held)
            sigs = [s for s in sigs if pd.Timestamp(s.bar_close_time) >= carry_exit]

        # Bars: first test bar .. last test bar + max horizon, within the same segment.
        first_i = int(closes.get_loc(test_closes[0]))
        last_i = int(closes.get_loc(last_close))
        max_h = max([int(s.horizon_bars) for s in sigs], default=0)
        seg_end = next((b - 1 for b in breaks if b > last_i), len(primary) - 1)
        end_i = min(seg_end, last_i + max_h)
        bar_slice = primary.iloc[first_i : end_i + 1].reset_index(drop=True)

        run = run_backtest(
            bar_slice,
            symbol=symbol,
            timeframe=timeframe,
            signals=sigs,
            cost=cost,
            strategy_id=cls.strategy_id,
            strategy_version=cls.strategy_version,
            data_paths=paths,
            period_start=to_utc_datetime(w.test_start),
            period_end=to_utc_datetime(w.test_end),
        )
        counters["signals_skipped_in_position"] += int(run.config["signals_skipped_in_position"])
        counters["dropped_open_at_end"] += int(run.config["dropped_open_at_end"])
        horizons.update(int(h) for h in run.config["horizon_bars_used"])
        win_audits = list(run.audits)
        if win_audits:
            carry_exit = pd.Timestamp(win_audits[-1].exit_time)
        oos_audits.extend(win_audits)

        # Window metrics on the window's own bars only.
        win_bars = primary[(primary["open_time"] >= w.test_start) & (primary["close_time"] <= w.test_end)]
        weq, wflags = _build_equity_and_flags(win_bars.reset_index(drop=True), win_audits, initial_equity=100_000.0)
        wm = summarize(win_audits, weq, wflags, timeframe=timeframe, asset_class=ASSET_CLASS)
        m = {k: wm[k] for k in ("win_rate", "profit_factor", "sharpe", "sortino", "max_drawdown", "avg_R", "exposure")}
        oos_windows.append(
            OOSWindow(
                train_start=to_utc_datetime(w.train_start),
                train_end=to_utc_datetime(w.train_end),
                test_start=to_utc_datetime(w.test_start),
                test_end=to_utc_datetime(w.test_end),
                trades=len(win_audits),
                metrics=m,
            )
        )

    initial_equity = 100_000.0
    oos_bars = [primary[(primary["open_time"] >= w.test_start) & (primary["close_time"] <= w.test_end)] for w in windows]
    oos_data = pd.concat(oos_bars, ignore_index=True) if oos_bars else primary.iloc[0:0]
    if not oos_data.empty:
        equity, pos_flags = _build_equity_and_flags(oos_data, oos_audits, initial_equity=initial_equity)
    else:
        equity, pos_flags = pd.Series(dtype=float), pd.Series(dtype=float)

    trades = [a.to_trade() for a in oos_audits]
    oos_bar_count = int(sum(int(((closes > pd.Timestamp(w.train_end)) & (closes <= pd.Timestamp(w.test_end))).sum()) for w in windows))
    metrics = summarize(oos_audits, equity, pos_flags, timeframe=timeframe, asset_class=ASSET_CLASS)
    undefined = undefined_metrics({k: metrics[k] for k in UNDEFINABLE})
    win_undefined = sum(1 for w in oos_windows if undefined_metrics(w.metrics))
    flags = compute_flags(
        trades=trades,
        win_rate_reported=metrics["win_rate"],
        profit_factor_reported=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        oos_bar_count=oos_bar_count,
        has_oos_windows=bool(oos_windows),
        data_quality_warning=has_large_gaps(primary, timeframe),
        metric_undefined=bool(undefined) or win_undefined > 0,
    )
    dhash = data_hash(paths)
    cfg = {
        "runner_version": RUNNER_VERSION,
        "signal_source": "signal_quant.registry.generate_range",
        "outcome_source": "signal_data.barriers.resolve (per signal, own horizon_bars)",
        "fees_bps": FEE_BPS,
        "slippage_bps": SLIP_BPS,
        "train_days": TRAIN_DAYS,
        "test_days": TEST_DAYS,
        "step_days": STEP_DAYS,
        "train_bars": train_bars,
        "test_bars": test_bars,
        "params": "published_defaults_frozen",
        "symbol": symbol,
        "timeframe": timeframe,
        "open_at_end_policy": "drop (trade that cannot fully resolve before end of data / a gap)",
        "window_last_bar_policy": "signals on a window's last bar are not taken (fill would be outside the window)",
    }
    rid = run_id(cls.strategy_id, cfg, dhash)
    if windows:
        period = {"start": to_utc_datetime(windows[0].test_start), "end": to_utc_datetime(windows[-1].test_end)}
    else:
        period = {"start": datetime(1970, 1, 1, tzinfo=timezone.utc), "end": datetime(1970, 1, 1, tzinfo=timezone.utc)}

    report = BacktestReport(
        strategy_id=cls.strategy_id,
        version=cls.strategy_version,
        period=period,
        oos_windows=oos_windows,
        trades=trades,
        trade_count=len(trades),
        win_rate=metrics["win_rate"],
        profit_factor=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        sortino=metrics["sortino"],
        max_drawdown=metrics["max_drawdown"],
        avg_R=metrics["avg_R"],
        exposure=metrics["exposure"],
        fees_bps=FEE_BPS,
        slippage_bps=SLIP_BPS,
        run_id=rid,
        data_hash=dhash,
        symbol=symbol,
        timeframe=timeframe,
        flags=flags,
    )
    dest = OUT_DIR / cls.strategy_id / f"{symbol}_{timeframe}"
    dest.mkdir(parents=True, exist_ok=True)
    report_path = dest / "backtest_report.json"
    report_path.write_text(report.model_dump_json(indent=2) + "\n")
    deciles = entry_position_deciles(oos_audits, windows)
    runtime = round(time.monotonic() - t0, 1)
    extra = {
        **cfg,
        "run_id": rid,
        "n_windows": len(windows),
        "oos_bar_count": oos_bar_count,
        "horizon_bars_used": sorted(horizons),
        **counters,
        "window_trades": [w.trades for w in oos_windows],
        "entry_position_deciles": deciles,
        "undefined_report_metrics": undefined,
        "windows_with_undefined_metrics": win_undefined,
        "parity_vs_generate": parity,
        "runtime_s": runtime,
    }
    (dest / "config.json").write_text(json.dumps(extra, indent=2, default=str) + "\n")
    audit = subprocess.run([sys.executable, str(QA_CHECK), str(report_path)], capture_output=True, text=True)
    audit_ok = audit.returncode == 0
    audit_text = (audit.stdout or "") + (audit.stderr or "")
    (dest / "qa_audit.txt").write_text(audit_text)
    schema_ok, schema_err = False, ""
    try:
        validate_report_schema(report_path)
        schema_ok = True
        (dest / "schema_ok.txt").write_text("OK\n")
    except Exception as exc:  # noqa: BLE001
        schema_err = f"{type(exc).__name__}: {exc}"
        (dest / "schema_ok.txt").write_text(schema_err + "\n")
    row = load_summary_row(report_path, audit_ok and schema_ok, audit_text)
    row["schema_ok"] = schema_ok
    row["schema_error"] = schema_err
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", action="append")
    p.add_argument("--timeframe", action="append")
    p.add_argument("--strategy", action="append")
    p.add_argument("--summary", default="summary.json", help="per-process summary file name (parallel runs)")
    args = p.parse_args(argv)

    generate_range = require_generate_range()  # fails loudly; no fallback
    from signal_quant.registry import list_strategies
    from signal_data.universe import CRYPTO

    classes = list_strategies()
    if args.strategy:
        classes = [c for c in classes if c.strategy_id in args.strategy]
    symbols = args.symbol or [i.symbol for i in CRYPTO]
    timeframes = args.timeframe or ["1d", "4h", "1h", "15m"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUT_DIR / args.summary
    results = []
    for cls in classes:
        for symbol in symbols:
            for tf in timeframes:
                print(f"==> {cls.strategy_id} {symbol} {tf}", flush=True)
                dest = OUT_DIR / cls.strategy_id / f"{symbol}_{tf}"
                existing, audit_txt, schema_txt = dest / "backtest_report.json", dest / "qa_audit.txt", dest / "schema_ok.txt"
                if (existing.exists() and audit_txt.exists() and audit_txt.read_text().strip().endswith("OK")
                        and schema_txt.exists() and schema_txt.read_text().strip() == "OK"):
                    print(f"    resume skip (checkpoint, audited OK): {existing}", flush=True)
                    row = load_summary_row(existing, True, audit_txt.read_text())
                    row["resumed"] = True
                else:
                    try:
                        row = run_one(cls, symbol, tf, generate_range)
                    except (MissingQuantFastPath, ParityError):
                        raise
                    except Exception as exc:  # noqa: BLE001
                        row = {"status": "error", "strategy_id": cls.strategy_id, "version": cls.strategy_version,
                               "symbol": symbol, "timeframe": tf, "error": f"{type(exc).__name__}: {exc}"}
                        print(f"    ERROR {row['error']}", flush=True)
                if row.get("status") == "skipped_unsupported":
                    print(f"    skipped: {row.get('reason')}", flush=True)
                elif row.get("status") != "error":
                    print(f"    trades={row.get('trade_count')} windows={row.get('window_trades')} "
                          f"pf={row.get('profit_factor')} flags={row.get('flags')} audit={row.get('audit_ok')} "
                          f"t={row.get('runtime_s')}s", flush=True)
                results.append(row)
                summary_path.write_text(json.dumps(results, indent=2, default=str) + "\n")
    return 0 if all(r.get("status") in {"ok", "skipped_unsupported"} for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
