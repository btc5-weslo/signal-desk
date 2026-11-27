"""Write backtest artifacts under reports/{run_id}/."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from signal_data.backtester.engine import BacktestRun
from signal_data.hashing import canonical_json
from signal_data.paths import REPORTS_DIR


def write_run(run: BacktestRun, *, dest: Path | None = None, label: str | None = None) -> Path:
    """Persist the team-contract report plus equity curve, audit log, and extra metrics."""
    report = run.report
    folder = dest or (REPORTS_DIR / report.run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "backtest_report.json").write_text(report.model_dump_json(indent=2) + "\n")
    extra = {
        "label": label,
        "config": run.config,
        "data_paths": run.data_paths,
        "extra_metrics": run.extra_metrics,
        "disclaimer": (
            "Hypothetical backtest. Not financial advice. Past performance "
            "(including backtests) does not guarantee future results. "
            "Placeholder strategies are for pipeline validation only, not recommendations."
        ),
    }
    (folder / "extra_metrics.json").write_text(json.dumps(extra, indent=2, default=str) + "\n")
    if run.audits:
        pd.DataFrame([a.model_dump(mode="json") for a in run.audits]).to_parquet(folder / "trade_audit.parquet", index=False)
        pd.DataFrame([a.model_dump(mode="json") for a in run.audits]).to_csv(folder / "trade_audit.csv", index=False)
    if run.equity is not None and len(run.equity):
        eq = run.equity.rename("equity").to_frame()
        eq.to_csv(folder / "equity_curve.csv")
    if label:
        # also drop a pointer at reports/{label}.json for the demo
        pointer = REPORTS_DIR / f"{label}.json"
        pointer.write_text(report.model_dump_json(indent=2) + "\n")
    return folder
