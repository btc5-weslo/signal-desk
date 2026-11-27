"""End-to-end ingest: fetch (incremental) -> clean -> atomic Parquet write -> quality report."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from signal_data.catalog import refresh_catalog
from signal_data.cleaning import clean_ohlcv
from signal_data.ingestion.base import RawFetch, empty_bars
from signal_data.ingestion.crypto import fetch_crypto
from signal_data.ingestion.equities import fetch_equity
from signal_data.ingestion.forex import fetch_forex
from signal_data.paths import QUALITY_DIR
from signal_data.schema import DataQualityReport
from signal_data.storage import last_open_time, merge_incremental, read_series, write_series
from signal_data.symbols import asset_class_of, to_canonical
from signal_data.timeutil import now_utc, to_utc
from signal_data.universe import Instrument, get_instrument


def _fetch(instrument: Instrument, timeframe: str, start: datetime, end: datetime) -> RawFetch:
    if instrument.asset_class == "crypto":
        return fetch_crypto(instrument, timeframe, start, end)
    if instrument.asset_class == "equity":
        return fetch_equity(instrument, timeframe, start, end)
    if instrument.asset_class == "fx":
        return fetch_forex(instrument, timeframe, start, end)
    raise ValueError(f"unknown asset class {instrument.asset_class}")


def ingest_series(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime | None = None,
    *,
    incremental: bool = True,
    write: bool = True,
    refresh: bool = True,
) -> tuple[pd.DataFrame, DataQualityReport]:
    """Fetch one series of real bars, clean it, and optionally write the store.

    If ``incremental`` and a Parquet file already exists, the fetch window
    starts a few bars before the last stored open so the last closed bar can
    be revised. Forming bars are dropped before write.
    """
    canonical = to_canonical(symbol)
    instrument = get_instrument(canonical)
    asset_class = instrument.asset_class
    end_was_default = end is None
    end = to_utc(end) if end is not None else now_utc()
    start = to_utc(start)

    existing = read_series(asset_class, canonical, timeframe) if incremental else empty_bars()
    fetch_start = start
    if incremental and not existing.empty:
        last = pd.Timestamp(existing["open_time"].iloc[-1])
        # overlap a handful of bars so the previous last close can be updated
        overlap = {"15m": timedelta(hours=2), "1h": timedelta(hours=8), "4h": timedelta(days=2), "1d": timedelta(days=5)}
        fetch_start = min(start, last - overlap[timeframe]) if last > start else last - overlap[timeframe]
        # but do not fetch before the user-requested start when doing a first full window
        # For incremental updates we *do* want to go back from last, even if last > start.
        if last >= start:
            fetch_start = last - overlap[timeframe]

    raw = _fetch(instrument, timeframe, fetch_start, end)
    incoming = raw.bars
    # Cut forming bars against the clock *after* the fetch returns, so a bar
    # that closes mid-request is kept if the venue included it.
    if end_was_default:
        end = now_utc()

    cleaned, report = clean_ohlcv(
        incoming,
        symbol=canonical,
        asset_class=asset_class,
        timeframe=timeframe,
        source=raw.source,
        as_of=end,
        history_limitations=raw.history_limitations,
        fetch_attempts=raw.attempts,
        warnings=raw.warnings,
        errors=raw.errors,
    )

    if incremental and not existing.empty:
        merged = merge_incremental(existing, cleaned)
        # re-run gap/quality on the merged series so the report describes what is stored
        merged, report2 = clean_ohlcv(
            merged,
            symbol=canonical,
            asset_class=asset_class,
            timeframe=timeframe,
            source=report.source or raw.source,
            as_of=end,
            history_limitations=report.history_limitations,
            fetch_attempts=report.fetch_attempts,
            warnings=report.warnings,
            errors=report.errors,
        )
        # preserve fetch-level attempts from the first report
        report = report2
        cleaned = merged

    if write:
        if not cleaned.empty:
            write_series(cleaned, asset_class, canonical, timeframe, as_of=end)
        QUALITY_DIR.mkdir(parents=True, exist_ok=True)
        qpath = QUALITY_DIR / f"{asset_class}_{canonical}_{timeframe}.json"
        qpath.write_text(report.model_dump_json(indent=2) + "\n")
        if refresh:
            refresh_catalog()

    return cleaned, report


def ingest_many(
    requests: list[tuple[str, str]],
    start: datetime,
    end: datetime | None = None,
    *,
    incremental: bool = True,
) -> list[tuple[str, str, pd.DataFrame, DataQualityReport]]:
    """Ingest many (symbol, timeframe) pairs. Failures are recorded, not invented."""
    out = []
    for symbol, timeframe in requests:
        try:
            df, report = ingest_series(symbol, timeframe, start, end, incremental=incremental)
        except Exception as exc:  # noqa: BLE001 — surface as a failed quality report
            canonical = symbol
            try:
                canonical = to_canonical(symbol)
            except Exception:
                pass
            try:
                ac = asset_class_of(canonical)
            except Exception:
                ac = "unknown"
            report = DataQualityReport(
                symbol=canonical,
                asset_class=ac,
                timeframe=timeframe,
                source=None,
                errors=[f"{type(exc).__name__}: {exc}"],
                cleaned_at=now_utc().to_pydatetime(),
            )
            df = empty_bars()
        out.append((report.symbol, timeframe, df, report))
    return out



def refresh_closed(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    *,
    data_dir=None,
    overlap_bars: int = 4,
) -> list[dict]:
    """Incremental closed-bar catch-up of already-stored series through now.

    This is a live tail refresh, not a historical backfill: each series is
    fetched from a short overlap before its last stored open, cleaned with
    ``as_of`` taken after the fetch returns, and merged into the store on
    ``open_time`` (existing sources are kept; ``binance_vision`` still wins
    a duplicate).
    """
    from signal_data.paths import TIMEFRAMES, get_store_dir
    from signal_data.storage import merge_on_open_time, read_series, write_series
    from signal_data.timeutil import TF_DELTA
    from signal_data.universe import CRYPTO, get_instrument

    root = get_store_dir(data_dir)
    insts = list(CRYPTO) if symbols is None else [get_instrument(s) for s in symbols]
    tfs = list(timeframes) if timeframes is not None else list(TIMEFRAMES)
    results: list[dict] = []
    for inst in insts:
        for tf in tfs:
            path = root / inst.asset_class / inst.symbol / f"{tf}.parquet"
            existing = read_series(inst.asset_class, inst.symbol, tf, data_dir=data_dir)
            if existing.empty:
                results.append(
                    {
                        "symbol": inst.symbol,
                        "timeframe": tf,
                        "status": "skipped_missing",
                        "path": str(path),
                    }
                )
                continue
            last = pd.Timestamp(existing["open_time"].iloc[-1])
            delta = TF_DELTA[tf]
            fetch_start = last - delta * int(overlap_bars)
            # Request slightly past "now" so a bar that closes during the
            # round-trip can be returned; clean_ohlcv then drops still-forming.
            fetch_end = now_utc() + delta
            raw = _fetch(inst, tf, fetch_start, fetch_end)
            as_of = now_utc()
            incoming = raw.bars
            cleaned, report = clean_ohlcv(
                incoming,
                symbol=inst.symbol,
                asset_class=inst.asset_class,
                timeframe=tf,
                source=raw.source,
                as_of=as_of,
                history_limitations=raw.history_limitations,
                fetch_attempts=raw.attempts,
                warnings=list(raw.warnings),
                errors=list(raw.errors),
            )
            before_last = existing["close_time"].iloc[-1] if len(existing) else None
            before_n = len(existing)
            if cleaned.empty:
                merged = existing
            else:
                merged = merge_on_open_time(existing, cleaned)
            write_series(merged, inst.asset_class, inst.symbol, tf, as_of=as_of, data_dir=data_dir)
            after_last = merged["close_time"].iloc[-1] if len(merged) else None
            results.append(
                {
                    "symbol": inst.symbol,
                    "timeframe": tf,
                    "status": "ok" if not report.errors else "error",
                    "source": raw.source,
                    "n_before": before_n,
                    "n_after": len(merged),
                    "n_incoming": len(cleaned),
                    "last_close_before": str(before_last) if before_last is not None else None,
                    "last_close_after": str(after_last) if after_last is not None else None,
                    "as_of": str(as_of),
                    "errors": list(report.errors),
                    "path": str(path),
                }
            )
            print(
                f"refresh {inst.symbol} {tf}: {before_n} -> {len(merged)} "
                f"last_close {before_last} -> {after_last} source={raw.source}",
                flush=True,
            )
    return results
