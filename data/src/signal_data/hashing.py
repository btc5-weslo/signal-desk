"""Deterministic hashes for data files and backtest run configs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parquet_sha256(path: Path) -> str:
    """Hash of parquet *content* (columns + rows), stable across metadata noise when possible.

    Falls back to the raw file hash if the file cannot be opened as parquet.
    """
    try:
        table = pq.read_table(path)
        h = hashlib.sha256()
        h.update("|".join(table.column_names).encode())
        # to_pandas then csv would be huge; hash each column's combined buffers
        for name in table.column_names:
            col = table.column(name)
            for chunk in col.chunks:
                for buf in chunk.buffers():
                    if buf is not None:
                        h.update(buf)
        return h.hexdigest()
    except Exception:
        return file_sha256(path)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config).encode()).hexdigest()


def data_hash(paths: Iterable[Path]) -> str:
    """Combined hash of the Parquet series used in a run, in sorted path order."""
    h = hashlib.sha256()
    for p in sorted(Path(x) for x in paths):
        h.update(str(p).encode())
        h.update(b":")
        if p.exists():
            h.update(parquet_sha256(p).encode())
        else:
            h.update(b"MISSING")
        h.update(b"\n")
    return h.hexdigest()


def run_id(strategy_id: str, config: dict[str, Any], data: str) -> str:
    raw = f"{strategy_id}:{config_hash(config)}:{data}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
