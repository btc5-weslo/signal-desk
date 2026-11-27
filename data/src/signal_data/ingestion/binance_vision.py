"""Backfill crypto OHLCV from data.binance.vision public kline archives.

Lead decision: this is the primary crypto source. Each zip is verified against
its companion ``.CHECKSUM`` (SHA-256) before any rows are used.
``source`` is written as ``binance_vision``. Stale bars are kept in the raw
store with ``is_stale=True``. Existing ``ccxt:binanceus`` files are replaced
wholesale — they are never merged into the same Parquet file.

If the Vision archives are unreachable from this box, callers may fall back
to ONE ccxt venue (okx, then bybit) for all five symbols. That fallback is
explicit and does not stitch venues or binanceus into a Vision file.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

from signal_data.cleaning import clean_ohlcv
from signal_data.ingestion.base import RawFetch, empty_bars, failed, make_bars, ok_attempt
from signal_data.paths import PACKAGE_ROOT
from signal_data.schema import DataQualityReport, FetchAttempt
from signal_data.symbols import to_canonical
from signal_data.universe import CRYPTO

log = logging.getLogger("signal_data.binance_vision")

SOURCE = "binance_vision"
VISION_BASE = "https://data.binance.vision"
S3_LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
CACHE_DIR = PACKAGE_ROOT / "vision_cache"
S3_NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}

# Canonical -> Vision pair name (spot USDT).
VISION_SYMBOL = {
    "BTC-USDT": "BTCUSDT",
    "ETH-USDT": "ETHUSDT",
    "SOL-USDT": "SOLUSDT",
    "BNB-USDT": "BNBUSDT",
    "XRP-USDT": "XRPUSDT",
}
VISION_INTERVALS = ("15m", "1h", "4h", "1d")
USER_AGENT = "signal-data-binance-vision/1.0"
MAX_WORKERS = 12
RETRIES = 4
TIMEOUT = 60



def _epoch_to_utc(values) -> pd.Series:
    """Vision timestamps are milliseconds through 2024 and microseconds from 2025-01."""
    v = pd.to_numeric(values, errors="coerce")
    med = float(v.dropna().median()) if v.notna().any() else 0.0
    if med >= 1e18:
        unit = "ns"
    elif med >= 1e14:
        unit = "us"
    else:
        unit = "ms"
    return pd.to_datetime(v, unit=unit, utc=True)


class ChecksumError(RuntimeError):
    """A Vision zip failed CHECKSUM verification or had no CHECKSUM file."""


def _canonical_to_vision(symbol: str) -> str:
    canon = to_canonical(symbol)
    if canon not in VISION_SYMBOL:
        raise ValueError(f"{canon} is not in the v1 crypto USDT universe")
    return VISION_SYMBOL[canon]


def parse_checksum_file(text: str, expected_name: str | None = None) -> str:
    """Return the hex SHA-256 digest from a Vision ``.CHECKSUM`` body."""
    text = text.strip()
    if not text:
        raise ChecksumError("empty CHECKSUM file")
    # "hex  filename"  or  "SHA256 (filename) = hex"
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not m:
        raise ChecksumError(f"no SHA-256 digest in CHECKSUM: {text!r}")
    return m.group(1).lower()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_checksum(data: bytes, checksum_text: str, *, filename: str | None = None) -> str:
    expected = parse_checksum_file(checksum_text, filename)
    actual = sha256_bytes(data)
    if actual != expected:
        raise ChecksumError(
            f"SHA-256 mismatch for {filename or 'archive'}: expected {expected}, got {actual}"
        )
    return actual


def _http_get(url: str, *, timeout: int = TIMEOUT) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last = exc
            if isinstance(exc, HTTPError) and exc.code == 404:
                raise
            time.sleep(min(2 ** attempt, 16))
    raise RuntimeError(f"GET {url} failed after {RETRIES} tries: {last}") from last


def list_keys(prefix: str) -> list[str]:
    """List object keys under a Vision prefix via the S3 list API."""
    keys: list[str] = []
    token: str | None = None
    while True:
        params: dict[str, str] = {
            "list-type": "2",
            "prefix": prefix,
            "max-keys": "1000",
        }
        if token:
            params["continuation-token"] = token
        url = S3_LIST + "?" + urlencode(params)
        body = _http_get(url, timeout=30)
        root = ET.fromstring(body)
        for el in root.findall("s:Contents/s:Key", S3_NS):
            if el.text:
                keys.append(el.text)
        truncated = (root.findtext("s:IsTruncated", default="false", namespaces=S3_NS) or "").lower() == "true"
        token = root.findtext("s:NextContinuationToken", default=None, namespaces=S3_NS)
        if not truncated or not token:
            break
    return keys


def list_archives(vision_symbol: str, interval: str) -> tuple[list[str], list[str]]:
    """Return (monthly zip keys, daily zip keys that extend past the last monthly)."""
    monthly_prefix = f"data/spot/monthly/klines/{vision_symbol}/{interval}/"
    daily_prefix = f"data/spot/daily/klines/{vision_symbol}/{interval}/"
    monthly_keys = [k for k in list_keys(monthly_prefix) if k.endswith(".zip") and ".CHECKSUM" not in k]
    monthly_keys.sort()
    last_month = None
    if monthly_keys:
        # .../BTCUSDT-15m-2026-10.zip
        m = re.search(r"(\d{4})-(\d{2})\.zip$", monthly_keys[-1])
        if m:
            last_month = (int(m.group(1)), int(m.group(2)))
    daily_keys = [k for k in list_keys(daily_prefix) if k.endswith(".zip") and ".CHECKSUM" not in k]
    daily_keys.sort()
    if last_month is not None:
        y, mo = last_month
        kept = []
        for k in daily_keys:
            dm = re.search(r"(\d{4})-(\d{2})-(\d{2})\.zip$", k)
            if not dm:
                continue
            dy, dmo = int(dm.group(1)), int(dm.group(2))
            if (dy, dmo) > (y, mo):
                kept.append(k)
        daily_keys = kept
    return monthly_keys, daily_keys


def _cache_path(key: str) -> Path:
    return CACHE_DIR / key


def download_verified_zip(key: str) -> Path:
    """Download ``key`` and its ``.CHECKSUM``, verify SHA-256, cache the zip."""
    dest = _cache_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    checksum_key = key + ".CHECKSUM"
    checksum_url = f"{VISION_BASE}/{checksum_key}"
    zip_url = f"{VISION_BASE}/{key}"
    try:
        checksum_text = _http_get(checksum_url, timeout=30).decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise ChecksumError(f"CHECKSUM missing for {key} (HTTP {exc.code})") from exc
    if dest.is_file():
        data = dest.read_bytes()
        try:
            verify_checksum(data, checksum_text, filename=Path(key).name)
            return dest
        except ChecksumError:
            dest.unlink(missing_ok=True)
    data = _http_get(zip_url)
    verify_checksum(data, checksum_text, filename=Path(key).name)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def parse_kline_zip(path: Path, *, timeframe: str, source: str = SOURCE) -> pd.DataFrame:
    """Parse a Vision kline zip (one CSV, typically no header) into OHLCV bars."""
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"{path} contains no CSV")
        raw = zf.read(names[0])
    # No header in the official dumps; some mirrors add one.
    text = raw.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    header = 0 if "open" in text.lower() and not text.strip()[:1].isdigit() else None
    df = pd.read_csv(
        BytesIO(raw),
        header=header,
        names=[
            "open_time_ms",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time_ms",
            "quote_volume",
            "trades",
            "taker_base",
            "taker_quote",
            "ignore",
        ],
    )
    open_times = _epoch_to_utc(df["open_time_ms"])
    return make_bars(
        open_times,
        df["open"],
        df["high"],
        df["low"],
        df["close"],
        df["volume"],
        source=source,
        timeframe=timeframe,
        asset_class="crypto",
    )


def fetch_vision(symbol: str, timeframe: str) -> RawFetch:
    """Download and concatenate every verified monthly (plus leftover daily) archive."""
    if timeframe not in VISION_INTERVALS:
        err = f"unsupported timeframe {timeframe}"
        return RawFetch(empty_bars(), attempts=[failed(SOURCE, err)], errors=[err])
    try:
        vs = _canonical_to_vision(symbol)
    except ValueError as exc:
        return RawFetch(empty_bars(), attempts=[failed(SOURCE, str(exc))], errors=[str(exc)])

    attempts: list[FetchAttempt] = []
    warnings: list[str] = []
    errors: list[str] = []
    try:
        monthly, daily = list_archives(vs, timeframe)
    except Exception as exc:  # noqa: BLE001 — recorded honestly
        err = f"Vision listing failed: {type(exc).__name__}: {exc}"
        return RawFetch(empty_bars(), attempts=[failed(SOURCE, err)], errors=[err])

    keys = monthly + daily
    if not keys:
        err = f"no Vision archives listed for {vs} {timeframe}"
        return RawFetch(empty_bars(), attempts=[failed(SOURCE, err)], errors=[err])

    frames: list[pd.DataFrame] = []
    failed_keys: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(download_verified_zip, k): k for k in keys}
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                path = fut.result()
                frames.append(parse_kline_zip(path, timeframe=timeframe))
            except Exception as exc:  # noqa: BLE001
                failed_keys.append(f"{key}: {type(exc).__name__}: {exc}")
                log.warning("archive failed %s: %s", key, exc)

    if failed_keys:
        warnings.append(f"{len(failed_keys)} archive(s) failed checksum or download")
        # A missing month would hide a hole if we silently continued with a
        # partial history. Fail the series unless every listed zip verified.
        err = f"{len(failed_keys)}/{len(keys)} Vision archives failed: " + "; ".join(failed_keys[:8])
        attempts.append(failed(SOURCE, err, notes=failed_keys[:20]))
        return RawFetch(empty_bars(), attempts=attempts, warnings=warnings, errors=[err])

    bars = pd.concat(frames, ignore_index=True) if frames else empty_bars()
    if not bars.empty:
        bars = bars.sort_values("open_time").drop_duplicates(subset=["open_time"], keep="last")
        bars["source"] = SOURCE
    notes = [
        f"monthly_zips={len(monthly)}",
        f"daily_zips={len(daily)}",
        "checksums=sha256 verified",
    ]
    attempts.append(ok_attempt(SOURCE, len(bars), notes=notes))
    limitations = [
        "History is whatever data.binance.vision published for this pair "
        f"(first monthly archive through the latest daily file). No binanceus rows were merged."
    ]
    return RawFetch(
        bars.reset_index(drop=True),
        attempts=attempts,
        source=SOURCE,
        history_limitations=limitations,
        warnings=warnings,
        errors=errors,
    )


def ingest_vision_series(symbol: str, timeframe: str, *, write: bool = True) -> tuple[pd.DataFrame, DataQualityReport]:
    """Fetch one series from Vision, clean it, and replace the store file.

    Existing files (including ``ccxt:binanceus``) are overwritten, never merged.
    """
    canonical = to_canonical(symbol)
    raw = fetch_vision(canonical, timeframe)
    cleaned, report = clean_ohlcv(
        raw.bars,
        symbol=canonical,
        asset_class="crypto",
        timeframe=timeframe,
        source=SOURCE,
        history_limitations=raw.history_limitations,
        fetch_attempts=raw.attempts,
        warnings=raw.warnings,
        errors=raw.errors,
    )
    if write and not cleaned.empty:
        # Backfills land in staging/ only. Merging into store/ is a separate step.
        from signal_data.storage import write_staging
        write_staging(cleaned, "crypto", canonical, timeframe)
    return cleaned, report


def vision_reachable() -> tuple[bool, str]:
    """Probe listing + a known checksummed monthly zip."""
    try:
        keys = list_keys("data/spot/monthly/klines/BTCUSDT/1d/")
        zips = [k for k in keys if k.endswith(".zip") and not k.endswith(".CHECKSUM")]
        if not zips:
            return False, "Vision S3 listing returned no BTCUSDT 1d monthly zips"
        # Verify we can fetch a CHECKSUM (cheaper than a zip).
        _http_get(f"{VISION_BASE}/{zips[0]}.CHECKSUM", timeout=20)
        return True, f"reachable; listed {len(zips)} monthly 1d BTCUSDT archives"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def ingest_all_crypto_vision(
    *,
    symbols: list[str] | None = None,
    timeframes: tuple[str, ...] = VISION_INTERVALS,
    write: bool = True,
) -> list[DataQualityReport]:
    """Ingest all 5 symbols × 4 timeframes from Vision (or return listing failures)."""
    symbols = symbols or [i.symbol for i in CRYPTO]
    reports: list[DataQualityReport] = []
    for symbol in symbols:
        for tf in timeframes:
            print(f"==> binance_vision {symbol} {tf}", flush=True)
            try:
                _df, report = ingest_vision_series(symbol, tf, write=write)
                print(
                    f"    {report.source or 'NO SOURCE'}: bars={report.n_bars} "
                    f"stale={report.n_stale_bars} stale_runs>3={report.n_stale_runs_gt_3} "
                    f"gaps>3={report.n_gaps_gt_3x} {report.start} -> {report.end} "
                    f"errors={report.errors}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"    EXCEPTION {type(exc).__name__}: {exc}", flush=True)
                report = DataQualityReport(
                    symbol=to_canonical(symbol),
                    asset_class="crypto",
                    timeframe=tf,
                    source=None,
                    errors=[f"{type(exc).__name__}: {exc}"],
                )
            reports.append(report)
    return reports
