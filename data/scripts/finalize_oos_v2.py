#!/usr/bin/env python3
"""Audit every report in reports/oos_quant_v2/ and write summary.json + summary.md.

Two QA audits are recorded per report:

- ``qa_raw``: qa/audits/backtest_report_check.py run unchanged (subprocess).
- ``qa_adj``: the same checker module, loaded in memory with two documented
  adjustments that do NOT change what it checks: (1) ``metric_undefined`` added
  to its known-flag set (new shared flag, 2026-11-26), and (2) ``_binom_sf``
  computed in log space, because the original overflows (OverflowError) for
  n > ~1000 trades. The checker file itself is not modified.
"""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "oos_quant_v2"
QA = ROOT.parent / "qa" / "audits" / "backtest_report_check.py"
SCHEMA = ROOT.parent / "shared" / "backtest_result.schema.json"


def _adjusted_checker():
    spec = importlib.util.spec_from_file_location("brc_adj", QA)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.FLAGS = set(m.FLAGS) | {"metric_undefined"}

    def binom_sf(k, n, p):
        if k <= 0:
            return 1.0
        lp, lq = math.log(p), math.log1p(-p)
        terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
                 for i in range(k, n + 1)]
        mx = max(terms)
        return min(1.0, math.exp(mx) * sum(math.exp(t - mx) for t in terms))

    m._binom_sf = binom_sf
    return m


def main() -> int:
    import contextlib
    import io

    import jsonschema

    schema = json.loads(SCHEMA.read_text())
    adj = _adjusted_checker()
    rows = []
    for rp in sorted(OUT.glob("*/*/backtest_report.json")):
        r = json.loads(rp.read_text())
        cfg = json.loads((rp.parent / "config.json").read_text())
        raw = subprocess.run([sys.executable, str(QA), str(rp)], capture_output=True, text=True)
        raw_out = (raw.stdout + raw.stderr).strip()
        if raw.returncode != 0 and "Traceback" in raw_out:
            raw_out = raw_out.strip().splitlines()[-1]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            adj_errs = adj.check(r)
        try:
            jsonschema.validate(r, schema)
            schema_ok = True
        except jsonschema.ValidationError as e:
            schema_ok = False
        rows.append({
            "strategy_id": r["strategy_id"], "version": r["version"], "symbol": r["symbol"], "timeframe": r["timeframe"],
            "trade_count": r["trade_count"], "win_rate": r["win_rate"], "profit_factor": r["profit_factor"],
            "sharpe": r["sharpe"], "max_drawdown": r["max_drawdown"], "flags": r["flags"], "run_id": r["run_id"],
            "data_hash": r["data_hash"], "n_windows": len(r["oos_windows"]),
            "window_trades": [w["trades"] for w in r["oos_windows"]],
            "entry_position_deciles": cfg["entry_position_deciles"],
            "horizon_bars_used": cfg["horizon_bars_used"],
            "signals_total": cfg["signals_total"], "signals_skipped_in_position": cfg["signals_skipped_in_position"],
            "signals_at_window_last_bar": cfg["signals_at_window_last_bar"], "dropped_open_at_end": cfg["dropped_open_at_end"],
            "parity_vs_generate": cfg["parity_vs_generate"], "runtime_s": cfg["runtime_s"],
            "schema_ok": schema_ok, "qa_raw_ok": raw.returncode == 0, "qa_raw_output": raw_out,
            "qa_adj_ok": not adj_errs, "qa_adj_errors": adj_errs, "path": str(rp.relative_to(ROOT)),
        })
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")

    def f(x, nd=3):
        return "null" if x is None else f"{x:.{nd}f}"

    wt = [t for r in rows for t in r["window_trades"]]
    dec = [sum(r["entry_position_deciles"][i] for r in rows) for i in range(10)]
    n = len(rows)
    lines = [
        "# Walk-forward OOS v2 — crypto (replaces withdrawn reports/oos_quant/)",
        "",
        "Signals: `signal_quant.registry.generate_range` (Quant's official fast path; parity-tested vs `generate()`,",
        "and spot-checked per combo against `run_for_bar`). Outcomes: `signal_data.barriers.resolve` per signal",
        "with its own `horizon_bars`. Frozen published parameters. Costs: 10 bps fee per side, 5 bps slippage.",
        "Windows: 365 d train / 180 d test, step 180 d. One position at a time per symbol.",
        "",
        "## Multiple-testing note",
        "",
        f"**{n} strategy/symbol/timeframe combos were tested** (4 strategies x 5 symbols x 4 timeframes,",
        "mtf_confirmation has no 1d). With that many combos, the best-looking results are expected to look good",
        "partly by chance. Any top pick from this table is a **lead for a pre-registered follow-up test, not",
        "evidence of an edge**. No parameter was tuned on these windows, and none should be.",
        "Results with fewer than 100 OOS trades (`low_oos_trades`) are an insufficient sample.",
        "",
        "## Trades per window",
        "",
        f"{len(wt)} windows: min {min(wt)}, median {statistics.median(wt)}, mean {statistics.mean(wt):.1f}, max {max(wt)};"
        f" windows with exactly 2 trades: {sum(1 for t in wt if t == 2)}; with 0: {sum(1 for t in wt if t == 0)}.",
        "",
        "Trade opens by position inside the test window (deciles, all reports): " + ", ".join(str(d) for d in dec),
        "",
        "## Per combo",
        "",
        "| strategy | symbol | tf | trades | wr | pf | sharpe | maxdd | flags | run_id | QA raw | QA adj | schema |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['strategy_id']} | {r['symbol']} | {r['timeframe']} | {r['trade_count']} | {f(r['win_rate'])} | "
            f"{f(r['profit_factor'])} | {f(r['sharpe'])} | {f(r['max_drawdown'])} | {', '.join(r['flags']) or '-'} | "
            f"{r['run_id']} | {'OK' if r['qa_raw_ok'] else 'FAIL'} | {'OK' if r['qa_adj_ok'] else 'FAIL'} | "
            f"{'OK' if r['schema_ok'] else 'FAIL'} |"
        )
    lines += ["", "QA raw = checker run unchanged; QA adj = same checker with `metric_undefined` known and a",
              "log-space `_binom_sf` (the original overflows above ~1000 trades). See scripts/finalize_oos_v2.py.", ""]
    (OUT / "summary.md").write_text("\n".join(lines))
    print(f"{n} reports; schema ok {sum(r['schema_ok'] for r in rows)}; qa raw ok {sum(r['qa_raw_ok'] for r in rows)}; "
          f"qa adj ok {sum(r['qa_adj_ok'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
