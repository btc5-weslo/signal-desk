#!/usr/bin/env python3
"""Merge staging/ backfills into store/ on open_time.

Each bar keeps its own source (never relabeled). On a duplicate open_time,
binance_vision wins. source_seam is set where the source changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from signal_data.paths import STAGING_DIR, STORE_DIR, TIMEFRAMES
from signal_data.storage import merge_on_open_time, read_parquet, write_series
from signal_data.universe import CRYPTO


def merge_one(symbol: str, timeframe: str) -> dict:
    staged = STAGING_DIR / "crypto" / symbol / f"{timeframe}.parquet"
    stored = STORE_DIR / "crypto" / symbol / f"{timeframe}.parquet"
    left = read_parquet(stored) if stored.exists() else None
    right = read_parquet(staged) if staged.exists() else None
    if left is None and right is None:
        return {"symbol": symbol, "timeframe": timeframe, "status": "missing"}
    if right is None:
        merged = left
        origin = "store_only"
    elif left is None:
        merged = merge_on_open_time(right)
        origin = "staging_only"
    else:
        merged = merge_on_open_time(left, right)
        origin = "merged"
    write_series(merged, "crypto", symbol, timeframe)
    sources = merged["source"].astype(str).value_counts().to_dict() if len(merged) else {}
    n_seam = int(merged["source_seam"].sum()) if "source_seam" in merged.columns and len(merged) else 0
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "status": origin,
        "n_bars": int(len(merged)),
        "first_open": None if merged.empty else str(merged["open_time"].iloc[0]),
        "last_close": None if merged.empty else str(merged["close_time"].iloc[-1]),
        "sources": sources,
        "n_source_seams": n_seam,
        "duplicate_open_time": int(merged["open_time"].duplicated().sum()) if len(merged) else 0,
    }


def main() -> int:
    rows = []
    for inst in CRYPTO:
        for tf in TIMEFRAMES:
            row = merge_one(inst.symbol, tf)
            rows.append(row)
            print(
                f"{row['symbol']} {row['timeframe']}: {row.get('status')} "
                f"bars={row.get('n_bars')} seams={row.get('n_source_seams')} "
                f"sources={row.get('sources')} {row.get('first_open')} -> {row.get('last_close')}",
                flush=True,
            )
            if row.get("duplicate_open_time"):
                print("  ERROR: duplicate open_time after merge", flush=True)
    return 1 if any(r.get("duplicate_open_time") for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
