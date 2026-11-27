"""Importing any signal_data module must not use the network or write store files."""

from __future__ import annotations

import importlib
import pkgutil
import socket
import sys
from pathlib import Path

import pytest

STORE = Path("/workspace/signal-app/data/store")
CATALOG = Path("/workspace/signal-app/data/catalog")
TRACKER = Path("/workspace/signal-app/data/tracker")
REPORTS = Path("/workspace/signal-app/data/reports")


def _iter_module_names() -> list[str]:
    import signal_data

    names = ["signal_data"]
    for m in pkgutil.walk_packages(signal_data.__path__, prefix="signal_data."):
        names.append(m.name)
    return names


class _BlockedSocket(socket.socket):
    def connect(self, *args, **kwargs):  # noqa: D401
        raise AssertionError(f"network connect during import: {args}")

    def connect_ex(self, *args, **kwargs):
        raise AssertionError(f"network connect_ex during import: {args}")

    def sendto(self, *args, **kwargs):
        raise AssertionError("network sendto during import")


def _snapshot(roots: list[Path]) -> dict[str, float]:
    out = {}
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                out[str(p)] = p.stat().st_mtime
    return out


def test_import_every_module_with_network_blocked(monkeypatch):
    monkeypatch.setattr(socket, "socket", _BlockedSocket)

    def deny_create_connection(*args, **kwargs):
        raise AssertionError(f"create_connection during import: {args}")

    monkeypatch.setattr(socket, "create_connection", deny_create_connection)

    # Drop already-imported package modules so this test actually re-executes them.
    doomed = [k for k in list(sys.modules) if k == "signal_data" or k.startswith("signal_data.")]
    for k in doomed:
        del sys.modules[k]

    before = _snapshot([STORE, CATALOG, TRACKER, REPORTS])
    names = []
    # Import package first, then walk — walk needs the package loaded.
    importlib.import_module("signal_data")
    names = _iter_module_names()
    assert "signal_data.store" in names
    assert "signal_data.candles" in names
    assert "signal_data.resample" in names
    assert "signal_data.symbols" in names
    assert "signal_data.masks" in names
    assert "signal_data.barriers" in names
    assert "signal_data.live" in names
    assert "signal_data.bars" in names
    assert "signal_data.ingestion.pipeline" in names
    assert "signal_data.demo" in names
    assert "signal_data.cli" in names
    for name in names:
        importlib.import_module(name)
    after = _snapshot([STORE, CATALOG, TRACKER, REPORTS])
    new_files = set(after) - set(before)
    # Ignore bytecode; we only care about store/catalog/tracker/report artifacts.
    leaked = [f for f in new_files if not f.endswith(".pyc")]
    assert leaked == [], f"import wrote files: {leaked}"


def test_official_get_candles_import_path():
    from signal_data.store import get_candles  # noqa: F401 — the stable Backend path

    import signal_data

    assert not hasattr(signal_data, "get_candles"), (
        "get_candles must be imported from signal_data.store only, "
        "not re-exported from the package root"
    )


def test_stable_public_imports():
    from signal_data.candles import get_candles as _gc  # noqa: F401
    from signal_data.resample import resample_closed as _rc  # noqa: F401
    from signal_data.symbols import to_canonical as _tc, to_source as _ts  # noqa: F401
    from signal_data.masks import is_stale as _is, gap_segments as _gs, STALE_RUN_GAP_BARS as _thr  # noqa: F401
    from signal_data.bars import load_closed as _lc  # noqa: F401
    from signal_data.live import update as _upd  # noqa: F401
    from signal_data.barriers import resolve as _rv  # noqa: F401
