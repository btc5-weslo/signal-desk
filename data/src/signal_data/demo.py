"""Placeholder SMA 20/50 pipeline demo on real 1d data.

This is not a trading recommendation. It exists to validate ingestion,
cleaning, storage, the event-driven backtester, walk-forward, and reporting
against live free APIs. Failed sources are recorded honestly; prices are
never fabricated.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import run_backtest
from signal_data.backtester.strategy import SmaCrossoverPlaceholder
from signal_data.backtester.walk_forward import walk_forward
from signal_data.ingestion.pipeline import ingest_series
from signal_data.paths import REPORTS_DIR, STORE_DIR, series_path
from signal_data.reporting import write_run
from signal_data.store import get_candles
from signal_data.timeutil import now_utc

DEMO_SYMBOLS = ("BTC-USDT", "AAPL", "EURUSD")
DEMO_TIMEFRAME = "1d"
# ~3 years ending today (box-local date is the user's America/New_York date)
DEMO_YEARS = 3
FEE_BPS = 10.0
SLIP_BPS = 5.0
PLACEHOLDER_NOTICE = (
    "PLACEHOLDER STRATEGY for pipeline validation only — not a recommendation. "
    "Not financial advice. Hypothetical backtest. Past performance does not "
    "guarantee future results."
)


def _start_end() -> tuple[datetime, datetime]:
    end = now_utc().to_pydatetime()
    start = end - timedelta(days=int(365.25 * DEMO_YEARS) + 14)  # small pad for SMA warmup
    return start, end


def run_demo(*, dest: Path | None = None) -> dict:
    """Fetch real 1d bars, run the placeholder SMA baseline + walk-forward, write reports."""
    dest = dest or REPORTS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    start, end = _start_end()
    cost = CostModel(fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)

    source_report: dict = {
        "generated_at": now_utc().isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "notice": PLACEHOLDER_NOTICE,
        "symbols": {},
    }
    frames: dict[str, pd.DataFrame] = {}

    for symbol in DEMO_SYMBOLS:
        df, quality = ingest_series(symbol, DEMO_TIMEFRAME, start, end, incremental=True)
        entry = {
            "ok": not df.empty and not quality.errors,
            "n_bars": int(len(df)),
            "source": quality.source,
            "start": quality.start.isoformat() if quality.start else None,
            "end": quality.end.isoformat() if quality.end else None,
            "fetch_attempts": [a.model_dump() for a in quality.fetch_attempts],
            "history_limitations": quality.history_limitations,
            "warnings": quality.warnings,
            "errors": quality.errors,
            "n_duplicates_removed": quality.n_duplicates_removed,
            "n_bad_ticks_dropped": quality.n_bad_ticks_dropped,
            "n_outliers_flagged": quality.n_outliers_flagged,
            "n_gaps_unexpected": quality.n_gaps_unexpected,
            "store_path": str(series_path(
                quality.asset_class if quality.asset_class != "unknown" else "crypto",
                quality.symbol,
                DEMO_TIMEFRAME,
            )) if not df.empty else None,
        }
        # If the series was written, confirm the official read path works.
        if not df.empty:
            try:
                via_store = get_candles(symbol, DEMO_TIMEFRAME)
                entry["get_candles_rows"] = int(len(via_store))
            except FileNotFoundError as exc:
                entry["get_candles_error"] = str(exc)
            frames[symbol] = df
        source_report["symbols"][symbol] = entry

    (dest / "source_report.json").write_text(json.dumps(source_report, indent=2, default=str) + "\n")

    results: dict = {"notice": PLACEHOLDER_NOTICE, "cost": {"fee_bps": FEE_BPS, "slippage_bps": SLIP_BPS}, "runs": {}}

    def _factory(**kwargs):
        return SmaCrossoverPlaceholder(**kwargs)

    def _fixed_params(symbol: str):
        def _cb(_train: pd.DataFrame):
            # Intentionally not a search over a large grid. Fixed 20/50
            # placeholder params, applied OOS, for pipeline validation.
            return {
                "symbol": symbol,
                "timeframe": DEMO_TIMEFRAME,
                "fast": 20,
                "slow": 50,
                "atr_period": 14,
                "stop_atr": 2.0,
                "tp_atr": 3.0,
                "horizon_bars": 20,
            }
        return _cb

    for symbol, df in frames.items():
        data_path = series_path(
            {"BTC-USDT": "crypto", "AAPL": "equity", "EURUSD": "fx"}[symbol],
            symbol,
            DEMO_TIMEFRAME,
        )
        strategy = SmaCrossoverPlaceholder(
            symbol=symbol,
            timeframe=DEMO_TIMEFRAME,
            fast=20,
            slow=50,
            horizon_bars=20,
        )
        full = run_backtest(
            df,
            symbol=symbol,
            timeframe=DEMO_TIMEFRAME,
            strategy=strategy,
            cost=cost,
            data_paths=[data_path],
            strategy_id="sma_crossover_placeholder",
            strategy_version="v1-placeholder",
            extra_config={"mode": "full_sample_pipeline_check", "notice": PLACEHOLDER_NOTICE},
        )
        full_dir = write_run(full, dest=dest / f"{symbol}_full", label=f"{symbol}_full_placeholder")

        # Walk-forward: ~1y train / ~6m test on daily bars (252/126 for all three
        # so windows are comparable; crypto has more calendar bars than equities).
        n = len(df)
        train_bars = 252
        test_bars = 126
        step_bars = 126
        wf_run, wf_logs = (None, [])
        if n >= train_bars + test_bars:
            wf_run, wf_logs = walk_forward(
                df,
                symbol=symbol,
                timeframe=DEMO_TIMEFRAME,
                strategy_factory=lambda **kw: SmaCrossoverPlaceholder(**kw),
                param_callback=_fixed_params(symbol),
                cost=cost,
                train_bars=train_bars,
                test_bars=test_bars,
                step_bars=step_bars,
                data_paths=[data_path],
                strategy_id="sma_crossover_placeholder",
                strategy_version="v1-placeholder",
            )
            write_run(wf_run, dest=dest / f"{symbol}_walkforward", label=f"{symbol}_walkforward_placeholder")

        def _summary(run):
            if run is None:
                return None
            r = run.report
            return {
                "run_id": r.run_id,
                "data_hash": r.data_hash,
                "period": {k: v.isoformat() for k, v in r.period.items()},
                "trade_count": r.trade_count,
                "win_rate": r.win_rate,
                "profit_factor": r.profit_factor,
                "sharpe": r.sharpe,
                "sortino": r.sortino,
                "max_drawdown": r.max_drawdown,
                "avg_R": r.avg_R,
                "exposure": r.exposure,
                "fees_bps": r.fees_bps,
                "slippage_bps": r.slippage_bps,
                "flags": r.flags,
                "qa_approved": r.qa_approved,
                "extra_metrics": run.extra_metrics,
                "oos_windows": len(r.oos_windows),
            }

        results["runs"][symbol] = {
            "n_bars": int(len(df)),
            "source": source_report["symbols"][symbol]["source"],
            "full_sample_pipeline_check": _summary(full),
            "walk_forward_oos": _summary(wf_run),
            "walk_forward_windows_log": wf_logs,
            "notice": PLACEHOLDER_NOTICE,
        }

    (dest / "demo_summary.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(json.dumps(results, indent=2, default=str))
    return results


def main(argv=None) -> int:
    run_demo()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
