#!/usr/bin/env python3
"""Rebuild / extend binance_vision series in staging/ only. Does not write store/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from signal_data.ingestion.binance_vision import ingest_all_crypto_vision
from signal_data.quality_batch import write_batch_reports


def main() -> int:
    reports = ingest_all_crypto_vision(write=True)
    write_batch_reports(
        "crypto_vision_staging",
        reports,
        notes=[
            "Backfill written only to staging/. store/ was not touched.",
            "Source is binance_vision. CHECKSUM SHA-256 verified. "
            "2025+ archives use microsecond timestamps (parsed, not dropped).",
        ],
    )
    failed = [r for r in reports if r.errors or r.n_bars == 0]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
