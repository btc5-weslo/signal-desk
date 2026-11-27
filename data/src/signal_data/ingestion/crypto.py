"""Crypto OHLCV via ccxt: Binance first, then Coinbase, then Kraken.

Only USDT pairs are written as *-USDT. A USD-only book is a failed attempt for
this universe, not silently stored as USDT.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from signal_data.ingestion.base import RawFetch, empty_bars, failed, make_bars, ok_attempt
from signal_data.timeutil import to_utc
from signal_data.universe import Instrument

# Exchange ids to try, in order. binanceus is a geo-block workaround, not a different quote.
EXCHANGE_IDS = ("binance", "binanceus", "coinbase", "coinbaseexchange", "kraken")

# Exchanges that failed in this process (e.g. 451 geo-block) are skipped for later calls.
_SKIP_EXCHANGES: set[str] = set()
CCXT_TF = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
LIMIT = 1000
# 15m * ~8 years is ~280k bars; 200 pages would truncate history.
MAX_PAGES = 4000


def _exchange(id_: str):
    import ccxt

    cls = getattr(ccxt, id_, None)
    if cls is None:
        raise RuntimeError(f"ccxt has no exchange id {id_!r}")
    ex = cls({"enableRateLimit": True, "timeout": 20000})
    return ex


def _has_symbol(ex, symbol: str) -> bool:
    try:
        ex.load_markets()
    except Exception as exc:  # noqa: BLE001 — we record the failure upstream
        raise RuntimeError(f"load_markets failed: {exc}") from exc
    return symbol in ex.symbols


def _paginate(ex, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    since = int(to_utc(start).timestamp() * 1000)
    end_ms = int(to_utc(end).timestamp() * 1000)
    rows: list[list] = []
    tf = CCXT_TF[timeframe]
    # safety cap so a runaway loop cannot hammer an API
    for _ in range(MAX_PAGES):
        batch = ex.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=LIMIT)
        if not batch:
            break
        for row in batch:
            ts = int(row[0])
            if ts >= end_ms:
                continue
            rows.append(row)
        last = int(batch[-1][0])
        if last <= since:
            break
        since = last + 1
        if since >= end_ms:
            break
        if len(batch) < LIMIT:
            break
        # Rate limiting is handled by ccxt (enableRateLimit=True).
    if not rows:
        return empty_bars()
    # dedupe in case of overlap
    data = {}
    for ts, o, h, l, c, v in rows:
        data[int(ts)] = (o, h, l, c, v)
    times = sorted(data)
    opens, highs, lows, closes, vols = zip(*(data[t] for t in times))
    open_times = [datetime.fromtimestamp(t / 1000.0, tz=timezone.utc) for t in times]
    return make_bars(
        open_times, opens, highs, lows, closes, vols,
        source=f"ccxt:{ex.id}", timeframe=timeframe, asset_class="crypto",
    )


def fetch_crypto(
    instrument: Instrument,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> RawFetch:
    attempts = []
    warnings: list[str] = []
    errors: list[str] = []
    symbol = instrument.ccxt_symbol
    if not symbol:
        err = "instrument has no ccxt_symbol"
        return RawFetch(empty_bars(), attempts=[failed("ccxt", err)], errors=[err])

    last_error = None
    for ex_id in EXCHANGE_IDS:
        try:
            import ccxt  # noqa: F401
        except Exception as exc:  # pragma: no cover
            attempts.append(failed("ccxt", f"ccxt import failed: {exc}"))
            return RawFetch(empty_bars(), attempts=attempts, errors=[str(exc)])
        if ex_id in _SKIP_EXCHANGES:
            attempts.append(failed(f"ccxt:{ex_id}", "skipped (earlier failure in this process, e.g. geo-block)"))
            continue
        try:
            ex = _exchange(ex_id)
        except Exception as exc:
            attempts.append(failed(f"ccxt:{ex_id}", f"could not construct exchange: {exc}"))
            last_error = exc
            continue
        try:
            if not _has_symbol(ex, symbol):
                # Do not substitute USD and call it USDT.
                usd = symbol.replace("/USDT", "/USD")
                note = f"{symbol} not listed"
                if usd != symbol and _has_symbol(ex, usd):
                    note += f"; {usd} is listed but was not used (universe is USDT, not USD)"
                attempts.append(failed(f"ccxt:{ex_id}", note, notes=[note]))
                continue
            bars = _paginate(ex, symbol, timeframe, start, end)
            if bars.empty:
                attempts.append(failed(f"ccxt:{ex_id}", "fetch_ohlcv returned no bars"))
                continue
            attempts.append(ok_attempt(f"ccxt:{ex_id}", len(bars)))
            return RawFetch(
                bars=bars,
                attempts=attempts,
                source=f"ccxt:{ex_id}",
                warnings=warnings,
                errors=errors,
            )
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            attempts.append(failed(f"ccxt:{ex_id}", msg))
            last_error = exc
            low = msg.lower()
            if "restricted location" in low or "451" in msg or "cloudfront" in low or "unavailable from a restricted" in low:
                _SKIP_EXCHANGES.add(ex_id)
            continue
    if last_error is not None:
        errors.append(f"all crypto sources failed; last error: {last_error}")
    else:
        errors.append("all crypto sources failed")
    return RawFetch(empty_bars(), attempts=attempts, warnings=warnings, errors=errors)



def ingest_single_venue_fallback(
    venues: tuple[str, ...] = ("okx", "bybit"),
) -> tuple[list, list[str]]:
    """Use the first ccxt venue that can serve ALL five USDT pairs.

    No stitching across venues or with binanceus. Returns (reports, notes).
    """
    from datetime import datetime, timezone

    from signal_data.cleaning import clean_ohlcv
    from signal_data.ingestion.base import empty_bars, failed
    from signal_data.schema import DataQualityReport
    from signal_data.storage import write_series
    from signal_data.universe import CRYPTO, get_instrument

    start = datetime(2017, 1, 1, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    symbols = [i.symbol for i in CRYPTO]
    tfs = ("15m", "1h", "4h", "1d")
    notes: list[str] = []

    chosen = None
    probe_errors: list[str] = []
    for ex_id in venues:
        try:
            ex = _exchange(ex_id)
            if not all(_has_symbol(ex, get_instrument(s).ccxt_symbol) for s in symbols):
                missing = [s for s in symbols if not _has_symbol(ex, get_instrument(s).ccxt_symbol)]
                probe_errors.append(f"ccxt:{ex_id} missing {missing}")
                continue
            # Probe one daily fetch per symbol so we don't commit to a thin/broken venue.
            ok_all = True
            for s in symbols:
                inst = get_instrument(s)
                try:
                    df = _paginate(ex, inst.ccxt_symbol, "1d", start, end)
                except Exception as exc:  # noqa: BLE001
                    probe_errors.append(f"ccxt:{ex_id} {s} 1d probe failed: {exc}")
                    ok_all = False
                    break
                if df is None or df.empty:
                    probe_errors.append(f"ccxt:{ex_id} {s} 1d probe returned no bars")
                    ok_all = False
                    break
            if ok_all:
                chosen = ex_id
                break
        except Exception as exc:  # noqa: BLE001
            probe_errors.append(f"ccxt:{ex_id} probe failed: {exc}")
            continue

    if chosen is None:
        notes = [
            "No single ccxt venue (okx, then bybit) served all five USDT pairs. "
            "binanceus was NOT used as a fallback (QA rejected that venue; no stitching).",
            *probe_errors,
        ]
        reports = [
            DataQualityReport(
                symbol=s,
                asset_class="crypto",
                timeframe=tf,
                source=None,
                errors=["no eligible single venue after Vision unavailability"],
                warnings=probe_errors[:20],
            )
            for s in symbols
            for tf in tfs
        ]
        return reports, notes

    notes = [
        f"Fell back to a single ccxt venue for all five symbols: ccxt:{chosen}. No stitching.",
        *probe_errors,
    ]
    reports = []
    ex = _exchange(chosen)
    src = f"ccxt:{chosen}"
    for s in symbols:
        inst = get_instrument(s)
        for tf in tfs:
            try:
                bars = _paginate(ex, inst.ccxt_symbol, tf, start, end)
                cleaned, report = clean_ohlcv(
                    bars,
                    symbol=s,
                    asset_class="crypto",
                    timeframe=tf,
                    source=src,
                    history_limitations=[f"ccxt pagination from {src}; Vision was unreachable"],
                    fetch_attempts=[__import__("signal_data.ingestion.base", fromlist=["ok_attempt"]).ok_attempt(src, len(bars))],
                )
                if not cleaned.empty:
                    dest = __import__("signal_data.paths", fromlist=["series_path"]).series_path("crypto", s, tf)
                    if dest.exists():
                        dest.unlink()
                    write_series(cleaned, "crypto", s, tf)
            except Exception as exc:  # noqa: BLE001
                cleaned, report = clean_ohlcv(
                    empty_bars(),
                    symbol=s,
                    asset_class="crypto",
                    timeframe=tf,
                    source=None,
                    errors=[f"{type(exc).__name__}: {exc}"],
                    fetch_attempts=[failed(src, str(exc))],
                )
            reports.append(report)
    return reports, notes
