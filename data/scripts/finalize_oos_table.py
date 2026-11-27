#!/usr/bin/env python3
"""Rebuild summary.json and a markdown table from every audited report on disk."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "oos_quant"
CHECK = ROOT.parent / "qa" / "audits" / "backtest_report_check.py"
PY = ROOT / ".venv" / "bin" / "python"
SCHEMA = ROOT.parent / "shared" / "backtest_result.schema.json"

STRATS = ["breakout_donchian", "mean_reversion_rsi_bb", "mtf_confirmation", "trend_ema_adx"]
SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
TFS = ["15m", "1h", "4h", "1d"]


def main() -> int:
    import jsonschema

    schema = json.loads(SCHEMA.read_text())
    rows = []
    for sid in STRATS:
        for symbol in SYMBOLS:
            for tf in TFS:
                report = OUT / sid / f"{symbol}_{tf}" / "backtest_report.json"
                if not report.exists():
                    rows.append({
                        "status": "missing",
                        "strategy_id": sid,
                        "symbol": symbol,
                        "timeframe": tf,
                        "path": str(report),
                    })
                    continue
                r = json.loads(report.read_text())
                audit = subprocess.run([str(PY), str(CHECK), str(report)], capture_output=True, text=True)
                schema_ok = True
                schema_err = ""
                try:
                    jsonschema.validate(instance=r, schema=schema)
                except Exception as exc:  # noqa: BLE001
                    schema_ok = False
                    schema_err = f"{type(exc).__name__}: {exc}"
                audit_ok = audit.returncode == 0
                (report.parent / "qa_audit.txt").write_text((audit.stdout or "") + (audit.stderr or ""))
                (report.parent / "schema_ok.txt").write_text("OK\n" if schema_ok else schema_err + "\n")
                rows.append({
                    "status": "ok" if audit_ok and schema_ok else "failed",
                    "strategy_id": r.get("strategy_id", sid),
                    "version": r.get("version"),
                    "symbol": r.get("symbol", symbol),
                    "timeframe": r.get("timeframe", tf),
                    "trade_count": r.get("trade_count"),
                    "win_rate": r.get("win_rate"),
                    "profit_factor": r.get("profit_factor"),
                    "sharpe": r.get("sharpe"),
                    "max_drawdown": r.get("max_drawdown"),
                    "flags": r.get("flags"),
                    "run_id": r.get("run_id"),
                    "data_hash": r.get("data_hash"),
                    "n_windows": len(r.get("oos_windows") or []),
                    "path": str(report),
                    "audit_ok": audit_ok,
                    "audit_output": ((audit.stdout or "") + (audit.stderr or "")).strip(),
                    "schema_ok": schema_ok,
                    "schema_error": schema_err,
                    "fees_bps": r.get("fees_bps"),
                    "slippage_bps": r.get("slippage_bps"),
                })
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2, default=str) + "\n")
    lines = [
        "# Walk-forward OOS reports",
        "",
        "Fees 10 bps (charged on entry and exit). Slippage 5 bps of price. Published default parameters; no OOS tuning.",
        "",
        "| strategy | symbol | TF | trades | win_rate | PF | sharpe | max_dd | flags | run_id | data_hash | audit | schema | path |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|",
    ]
    def fmt(x, n=6):
        if x is None:
            return ""
        if isinstance(x, float):
            return f"{x:.{n}g}"
        return str(x)
    for r in rows:
        flags = ",".join(r.get("flags") or []) if r.get("status") != "missing" else r.get("status")
        lines.append(
            "| {strategy_id} | {symbol} | {timeframe} | {trade_count} | {win_rate} | {profit_factor} | {sharpe} | {max_drawdown} | {flags} | {run_id} | {data_hash} | {audit} | {schema} | `{path}` |".format(
                strategy_id=r.get("strategy_id"),
                symbol=r.get("symbol"),
                timeframe=r.get("timeframe"),
                trade_count=r.get("trade_count") if r.get("trade_count") is not None else "",
                win_rate=fmt(r.get("win_rate")),
                profit_factor=fmt(r.get("profit_factor")),
                sharpe=fmt(r.get("sharpe")),
                max_drawdown=fmt(r.get("max_drawdown")),
                flags=flags,
                run_id=r.get("run_id") or "",
                data_hash=(r.get("data_hash") or "")[:16] + ("…" if r.get("data_hash") else ""),
                audit="OK" if r.get("audit_ok") else ("FAIL" if r.get("status") != "missing" else "—"),
                schema="OK" if r.get("schema_ok") else ("FAIL" if r.get("status") != "missing" else "—"),
                path=r.get("path", ""),
            )
        )
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    missing = [r for r in rows if r["status"] == "missing"]
    failed = [r for r in rows if r["status"] == "failed"]
    print(f"rows={len(rows)} ok={sum(1 for r in rows if r['status']=='ok')} missing={len(missing)} failed={len(failed)}")
    for r in missing:
        print("missing", r["strategy_id"], r["symbol"], r["timeframe"])
    for r in failed:
        print("failed", r["strategy_id"], r["symbol"], r["timeframe"], r.get("audit_output"), r.get("schema_error"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
