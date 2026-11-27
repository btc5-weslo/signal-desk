#!/usr/bin/env python3
"""Build and top up the demo store under SIGNAL_DATA_DIR.

The Parquet store is not committed and Render's free disk is ephemeral, so:

  build  (image build) recent history from data.binance.vision, SHA-256 checked.
  topup  (container start) newest closed bars from ccxt:binanceus, merged on
         open_time. binance_vision wins duplicates, every bar keeps its own
         source label, and source_seam marks where the source changes.

api.binance.com is never called (it blocks US IPs). Both sources are shown in
the app as not licensed.

    python deploy/bootstrap_data.py build|topup [--out DIR] [--symbols ...]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "src"))

# signal_data checks SIGNAL_DATA_DIR at import time, so resolve --out first.
if "--out" in sys.argv[1:-1]:
    os.environ["SIGNAL_DATA_DIR"] = sys.argv[sys.argv.index("--out") + 1]

import pandas as pd
from signal_data.cleaning import clean_ohlcv
from signal_data.ingestion import binance_vision as bv
from signal_data.ingestion.crypto import _exchange, _paginate
from signal_data.storage import merge_on_open_time, read_series, write_series
from signal_data.timeutil import TF_DELTA

# Monthly archives kept per timeframe (plus the daily files after them).
MONTHS = {"15m": 3, "1h": 8, "4h": 30, "1d": 72}
MIN_BARS = 200  # Quant needs at least this many closed bars per series.
TOPUP_EXCHANGE = "binanceus"
_MONTH_RE = re.compile(r"-(\d{4})-(\d{2})\.zip$")


def _ccxt_symbol(symbol: str) -> str:
    return symbol.replace("-", "/")


def build_series(symbol: str, timeframe: str, out: Path) -> str:
    monthly, daily = bv.list_archives(bv.VISION_SYMBOL[symbol], timeframe)
    keys = [k for k in monthly if _MONTH_RE.search(k)][-MONTHS[timeframe]:] + daily
    if not keys:
        raise RuntimeError("no Vision archives listed")
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(bv.download_verified_zip, keys))
    raw = pd.concat([bv.parse_kline_zip(p, timeframe=timeframe) for p in paths], ignore_index=True)
    raw = raw.sort_values("open_time").drop_duplicates(subset=["open_time"], keep="last")
    cleaned, report = clean_ohlcv(
        raw, symbol=symbol, asset_class="crypto", timeframe=timeframe, source=bv.SOURCE,
    )
    if len(cleaned) < MIN_BARS:
        raise RuntimeError(f"only {len(cleaned)} closed bars (< {MIN_BARS}) {report.errors}")
    merged = merge_on_open_time(cleaned)
    write_series(merged, "crypto", symbol, timeframe, data_dir=out)
    return f"build {symbol} {timeframe}: {len(merged)} bars, last open {merged['open_time'].iloc[-1]}"


def topup_series(ex, symbol: str, timeframe: str, out: Path) -> str:
    existing = read_series("crypto", symbol, timeframe, data_dir=out)
    if existing.empty:
        raise RuntimeError("no stored series to top up (run build first)")
    delta = TF_DELTA[timeframe]
    start = pd.Timestamp(existing["open_time"].iloc[-1]) - delta * 4
    now = datetime.now(UTC)
    incoming = _paginate(ex, _ccxt_symbol(symbol), timeframe, start.to_pydatetime(), now + delta)
    as_of = datetime.now(UTC)
    cleaned, report = clean_ohlcv(
        incoming, symbol=symbol, asset_class="crypto", timeframe=timeframe,
        source=f"ccxt:{TOPUP_EXCHANGE}", as_of=as_of,
    )
    merged = merge_on_open_time(existing, cleaned) if len(cleaned) else existing
    write_series(merged, "crypto", symbol, timeframe, as_of=as_of, data_dir=out)
    return (f"topup {symbol} {timeframe}: {len(existing)} -> {len(merged)} bars, "
            f"last open {merged['open_time'].iloc[-1]} {report.errors or ''}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["build", "topup"])
    ap.add_argument("--out", default=os.environ.get("SIGNAL_DATA_DIR"))
    ap.add_argument("--symbols", default=",".join(bv.VISION_SYMBOL))
    ap.add_argument("--timeframes", default=",".join(MONTHS))
    args = ap.parse_args(argv)
    if not args.out:
        print("set --out or SIGNAL_DATA_DIR", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ex = _exchange(TOPUP_EXCHANGE) if args.mode == "topup" else None
    failures = 0
    for symbol in [s.strip() for s in args.symbols.split(",") if s.strip()]:
        for tf in [t.strip() for t in args.timeframes.split(",") if t.strip()]:
            try:
                if args.mode == "build":
                    print(build_series(symbol, tf, out), flush=True)
                else:
                    print(topup_series(ex, symbol, tf, out), flush=True)
            except Exception as exc:  # noqa: BLE001 — logged, exit code 1
                failures += 1
                print(f"{args.mode} {symbol} {tf}: FAILED {type(exc).__name__}: {exc}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
