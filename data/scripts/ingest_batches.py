#!/usr/bin/env python3
"""Explicit batch ingestion of the locked v1 universe into store/.

Does nothing on import. Run:  python -m signal_data  is the CLI;
this script is:  python scripts/ingest_batches.py crypto|equities_fx_1d|equities_fx_intraday|all
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from the repo root without installation if needed
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from signal_data.ingestion.binance_vision import ingest_all_crypto_vision, vision_reachable
from signal_data.ingestion.pipeline import ingest_series
from signal_data.quality_batch import write_batch_reports
from signal_data.schema import DataQualityReport
from signal_data.universe import CRYPTO, EQUITIES, FOREX

CRYPTO_START = datetime(2017, 1, 1, tzinfo=timezone.utc)  # as deep as the source allows
# Equities/FX daily: at least 3 years, request a longer window
CASH_DAILY_START = datetime(2015, 1, 1, tzinfo=timezone.utc)
# Intraday will be clipped by yfinance limits; request 3y and record the true span
CASH_INTRADAY_START = datetime(2023, 1, 1, tzinfo=timezone.utc)

CRYPTO_TFS = ("1d", "4h", "1h", "15m")  # daily first so something lands early


def _run(pairs: list[tuple[str, str]], start: datetime, incremental: bool = True) -> list[DataQualityReport]:
    reports: list[DataQualityReport] = []
    for symbol, tf in pairs:
        print(f"==> ingest {symbol} {tf} from {start.date()}", flush=True)
        try:
            df, report = ingest_series(symbol, tf, start, incremental=incremental)
            print(
                f"    {report.source or 'NO SOURCE'}: bars={report.n_bars} "
                f"{report.start} -> {report.end} errors={report.errors}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"    EXCEPTION {type(exc).__name__}: {exc}", flush=True)
            report = DataQualityReport(
                symbol=symbol,
                asset_class="unknown",
                timeframe=tf,
                source=None,
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        reports.append(report)
    return reports


def batch_crypto() -> list[DataQualityReport]:
    """Primary path: data.binance.vision public kline archives (checksummed).

    If Vision is unreachable, fall back to ONE ccxt venue (okx, then bybit)
    for all five symbols. Never stitch binanceus or mixed venues into a file.
    """
    ok, msg = vision_reachable()
    print(f"binance.vision probe: ok={ok} ({msg})", flush=True)
    if ok:
        reports = ingest_all_crypto_vision()
        notes = [
            "Universe: BTC, ETH, SOL, BNB, XRP vs USDT. Timeframes 15m, 1h, 4h, 1d.",
            "Source: data.binance.vision public kline archives; every zip verified against its SHA-256 CHECKSUM file.",
            "source column is 'binance_vision'. Stale bars are kept in the raw store with is_stale=True.",
            "Existing ccxt:binanceus files were replaced, not merged (no stitching).",
            msg,
        ]
    else:
        from signal_data.ingestion.crypto import ingest_single_venue_fallback
        reports, venue_notes = ingest_single_venue_fallback()
        notes = [
            "Universe: BTC, ETH, SOL, BNB, XRP vs USDT. Timeframes 15m, 1h, 4h, 1d.",
            "data.binance.vision was unreachable from this box; did not write a partial Vision file.",
            *venue_notes,
        ]
    write_batch_reports("crypto", reports, notes=notes)
    return reports


def batch_equities_fx_1d() -> list[DataQualityReport]:
    pairs = [(i.symbol, "1d") for i in EQUITIES + FOREX]
    reports = _run(pairs, CASH_DAILY_START)
    write_batch_reports(
        "equities_fx_1d",
        reports,
        notes=[
            "Equities: SPY, QQQ, AAPL, MSFT, NVDA, TSLA, AMZN, META. FX: EURUSD, GBPUSD, USDJPY, AUDUSD.",
            "Timeframe 1d only. yfinance first (auto-adjusted); Stooq daily fallback for equities; Frankfurter/ECB daily fallback for FX (O=H=L=C reference rates, not exchange OHLC).",
            "Requested start 2015-01-01 UTC; actual span is whatever the source returned.",
        ],
    )
    return reports


def batch_equities_fx_intraday() -> list[DataQualityReport]:
    # 1h first (needed to resample 4h), then 4h, then 15m
    pairs = []
    for inst in EQUITIES + FOREX:
        for tf in ("1h", "4h", "15m"):
            pairs.append((inst.symbol, tf))
    reports = _run(pairs, CASH_INTRADAY_START)
    write_batch_reports(
        "equities_fx_intraday",
        reports,
        notes=[
            "Equities and FX intraday: 1h, 4h (resampled from 1h closed buckets only), 15m.",
            "yfinance typically caps 15m at ~60 days and 1h at ~730 days; those limits are recorded per series, not padded with synthetic bars.",
            "Frankfurter/Stooq do not provide intraday; if yfinance fails, the series is recorded as failed.",
        ],
    )
    return reports


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ingest real market data into store/")
    p.add_argument(
        "batch",
        choices=("crypto", "equities_fx_1d", "equities_fx_intraday", "all"),
        help="Which batch to run",
    )
    args = p.parse_args(argv)
    if args.batch in ("crypto", "all"):
        batch_crypto()
    if args.batch in ("equities_fx_1d", "all"):
        batch_equities_fx_1d()
    if args.batch in ("equities_fx_intraday", "all"):
        batch_equities_fx_intraday()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
