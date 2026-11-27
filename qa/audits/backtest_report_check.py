#!/usr/bin/env python3
"""Sanity-check a backtest report JSON against the team contract and recompute metrics from trades.
Usage: python qa/audits/backtest_report_check.py report.json"""
import json, sys, math
from datetime import datetime
FLAGS = {"low_oos_trades","sharpe_gt_3","win_rate_gt_75","insufficient_oos_history","data_quality_warning","metric_recompute_mismatch"}
REQ = ["strategy_id","version","period","oos_windows","trades","win_rate","profit_factor","sharpe","sortino",
       "max_drawdown","avg_R","exposure","fees_bps","slippage_bps","run_id","data_hash"]
def _t(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))

def _binom_sf(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k, n + 1))

SENTINEL = 1e5  # any |metric| above this is a stand-in for infinity, not a number
BUNCH_FRAC, BUNCH_P = 0.2, 1e-3

def structure_errors(r, tr):
    """Checks that catch engine bugs the metric recompute cannot (added after the 2026-11-26 in_trade bug)."""
    errs, wins = [], r["oos_windows"]
    # 1. no sentinel / non-finite metrics, at report or window level (use null + a flag instead)
    for scope, m in [("report", r)] + [(f"window {i}", w.get("metrics") or {}) for i, w in enumerate(wins)]:
        for k in ("win_rate", "profit_factor", "sharpe", "sortino", "max_drawdown", "avg_R", "exposure"):
            v = m.get(k)
            if isinstance(v, (int, float)) and (not math.isfinite(v) or abs(v) > SENTINEL):
                errs.append(f"{scope}: {k}={v} is a sentinel/non-finite value; report null with a flag")
    # 2. window trade counts add up to the trade list
    if "trade_count" in r and r["trade_count"] != len(tr):
        errs.append(f"trade_count {r['trade_count']} != len(trades) {len(tr)}")
    wsum = sum(int(w.get("trades") or 0) for w in wins)
    if wsum != len(tr):
        errs.append(f"sum of window trades {wsum} != len(trades) {len(tr)}")
    # 3. every trade opens inside an OOS test window; measure position within its window
    spans = [(_t(w["test_start"]), _t(w["test_end"])) for w in wins]
    early = 0
    for t in tr:
        et = _t(t["entry_time"])
        hit = [(a, b) for a, b in spans if a <= et < b]
        if not hit:
            errs.append(f"trade at {t['entry_time']} is outside every OOS test window"); continue
        a, b = hit[0]
        if (et - a) / (b - a) < BUNCH_FRAC: early += 1
    # 4. trades bunched at window starts (expect ~20% in the first 20% of a window)
    n = len(tr)
    if n >= 10:
        pv = _binom_sf(early, n, BUNCH_FRAC)
        if pv < BUNCH_P:
            errs.append(f"trades bunched at window starts: {early}/{n} open in the first {int(BUNCH_FRAC*100)}% "
                        f"of their window (p={pv:.1e}); check the engine's position/pending logic")
    # 5. identical trade counts in every window
    counts = [int(w.get("trades") or 0) for w in wins]
    if len(counts) >= 5 and len(set(counts)) == 1 and counts[0] > 0:
        errs.append(f"every one of {len(counts)} windows has exactly {counts[0]} trades; looks capped by construction")
    elif len(counts) >= 5 and max(counts) - min(counts) <= 1 and max(counts) <= 3:
        print(f"warning: near-identical window trade counts {counts}")
    # 6. trades must not overlap (one position at a time per symbol)
    by_sym = {}
    for t in sorted(tr, key=lambda t: _t(t["entry_time"])):
        prev = by_sym.get(t.get("symbol"))
        if prev and _t(t["entry_time"]) < _t(prev["exit_time"]):
            errs.append(f"overlapping trades: {prev['entry_time']}-{prev['exit_time']} and {t['entry_time']}")
        by_sym[t.get("symbol")] = t
    return errs

def check(r):
    errs = [f"missing field: {k}" for k in REQ if k not in r]
    if errs: return errs
    if not r["oos_windows"]: errs.append("no out-of-sample windows")
    if r["fees_bps"] <= 0: errs.append("fees_bps must be > 0")
    if r["slippage_bps"] <= 0: errs.append("slippage_bps must be > 0")
    tr = r["trades"] if isinstance(r["trades"], list) else None
    if tr is None: errs.append("trades must be the trade list so QA can recompute metrics"); return errs
    expected = set()
    if len(tr) < 100: expected.add("low_oos_trades")
    pnl = [t.get("net_return", t.get("pnl")) for t in tr]
    if any(p is None for p in pnl): errs.append("trade missing net_return/pnl"); return errs
    wins = [p for p in pnl if p > 0]; losses = [p for p in pnl if p <= 0]
    wr = len(wins)/len(pnl) if pnl else 0
    pf = sum(wins)/abs(sum(losses)) if losses and sum(losses) != 0 else math.inf
    if abs(wr - r["win_rate"]) > 1e-3 or (math.isfinite(pf) and abs(pf - r["profit_factor"]) > 1e-2):
        expected.add("metric_recompute_mismatch")
        errs.append(f"metric mismatch: win_rate {r['win_rate']} vs {wr:.4f}, profit_factor {r['profit_factor']} vs {pf:.3f}")
    if (r["sharpe"] or 0) > 3: expected.add("sharpe_gt_3")
    if (r["win_rate"] or 0) > 0.75: expected.add("win_rate_gt_75")
    errs += structure_errors(r, tr)
    got = set(r.get("flags") or [])
    unknown = got - FLAGS
    if unknown: errs.append(f"unknown flags: {sorted(unknown)}")
    missing = expected - got
    if missing: errs.append(f"report is missing required flags: {sorted(missing)}")
    if expected or got: print(f"flags (expected by QA): {sorted(expected)}; in report: {sorted(got)}")
    return errs
if __name__ == "__main__":
    e = check(json.load(open(sys.argv[1])))
    print("\n".join(e) or "OK"); sys.exit(1 if e else 0)
