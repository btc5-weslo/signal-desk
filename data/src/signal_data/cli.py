"""Explicit CLI for ingestion and the placeholder demo. Importing this module is a no-op.

Ingestion, network calls, and store writes happen only when a subcommand runs.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="signal-data",
        description=(
            "Market data and backtesting for the Signal app. "
            "No network or store writes occur unless you run a subcommand."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="Fetch real bars and write the Parquet store")
    ing.add_argument("--symbol", action="append", required=True, help="Canonical or raw symbol; repeatable")
    ing.add_argument("--timeframe", action="append", required=True, help="15m|1h|4h|1d; repeatable")
    ing.add_argument("--start", required=True, help="UTC start (YYYY-MM-DD or ISO)")
    ing.add_argument("--end", default=None, help="UTC end (default: now)")
    ing.add_argument("--no-incremental", action="store_true")

    sub.add_parser("demo", help="Run the placeholder SMA pipeline demo on real 1d data")
    sub.add_parser("catalog", help="Rebuild the DuckDB catalog over existing Parquet files")
    sub.add_parser("refresh", help="Catch up stored series with newly closed bars through now")
    return p


def _parse_when(s: str | None) -> datetime | None:
    if s is None:
        return None
    raw = s.strip()
    if len(raw) == 10:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "ingest":
        from signal_data.ingestion.pipeline import ingest_series

        start = _parse_when(args.start)
        end = _parse_when(args.end)
        for symbol in args.symbol:
            for tf in args.timeframe:
                df, report = ingest_series(
                    symbol,
                    tf,
                    start,
                    end,
                    incremental=not args.no_incremental,
                )
                print(
                    json.dumps(
                        {
                            "symbol": report.symbol,
                            "timeframe": report.timeframe,
                            "source": report.source,
                            "n_bars": report.n_bars,
                            "errors": report.errors,
                            "warnings": report.warnings,
                            "history_limitations": report.history_limitations,
                            "fetch_attempts": [a.model_dump() for a in report.fetch_attempts],
                        },
                        indent=2,
                        default=str,
                    )
                )
        return 0
    if args.cmd == "demo":
        from signal_data.demo import run_demo

        run_demo()
        return 0
    if args.cmd == "catalog":
        from signal_data.catalog import refresh_catalog

        refresh_catalog()
        print("catalog refreshed")
        return 0
    if args.cmd == "refresh":
        from signal_data.ingestion.pipeline import refresh_closed

        rows = refresh_closed()
        n_ok = sum(1 for r in rows if r.get("status") == "ok")
        print(f"refresh done: {n_ok}/{len(rows)} series updated or already current")
        return 0 if all(r.get("status") in {"ok", "skipped_missing"} for r in rows) else 1
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
