#!/usr/bin/env python3
"""Restore ccxt:binanceus into store/ so every crypto file runs through today.

This is a store restore, not a Vision backfill. Vision archives belong in staging/.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from signal_data.cleaning import clean_ohlcv
from signal_data.ingestion.base import failed, ok_attempt
from signal_data.ingestion.crypto import _exchange, _has_symbol, _paginate
from signal_data.schema import DataQualityReport
from signal_data.storage import write_series
from signal_data.universe import CRYPTO, get_instrument

START = datetime(2017, 1, 1, tzinfo=timezone.utc)
TFS = ("1d", "4h", "1h", "15m")
VENUE = "binanceus"


def restore_one(symbol: str, timeframe: str) -> DataQualityReport:
    inst = get_instrument(symbol)
    src = f"ccxt:{VENUE}"
    end = datetime.now(timezone.utc)
    bars = None
    try:
        ex = _exchange(VENUE)
        if not _has_symbol(ex, inst.ccxt_symbol):
            raise RuntimeError(f"{inst.ccxt_symbol} not listed on {VENUE}")
        bars = _paginate(ex, inst.ccxt_symbol, timeframe, START, end)
        cleaned, report = clean_ohlcv(
            bars,
            symbol=symbol,
            asset_class="crypto",
            timeframe=timeframe,
            source=src,
            as_of=end,
            history_limitations=[
                "Restored from ccxt:binanceus so the live store runs through today. "
                "binanceus is a thin US venue (QA flagged holes and stale 15m bars)."
            ],
            fetch_attempts=[ok_attempt(src, len(bars))],
        )
        if cleaned.empty:
            report.errors.append("binanceus returned no bars")
            return report
        write_series(cleaned, "crypto", symbol, timeframe, as_of=end)
        return report
    except Exception as exc:  # noqa: BLE001 — recorded honestly
        _, report = clean_ohlcv(
            bars,
            symbol=symbol,
            asset_class="crypto",
            timeframe=timeframe,
            source=None,
            errors=[f"{type(exc).__name__}: {exc}"],
            fetch_attempts=[failed(src, str(exc))],
        )
        return report


def main() -> int:
    rc = 0
    for inst in CRYPTO:
        for tf in TFS:
            print(f"==> restore ccxt:binanceus {inst.symbol} {tf}", flush=True)
            report = restore_one(inst.symbol, tf)
            print(
                f"    {report.source or 'NO SOURCE'}: bars={report.n_bars} "
                f"{report.start} -> {report.end} errors={report.errors}",
                flush=True,
            )
            if report.errors or report.n_bars == 0:
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
