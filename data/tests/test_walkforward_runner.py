"""scripts/run_quant_walkforward.py v2: product signal path only, no hard-coded horizon."""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_quant_walkforward.py"


def _load():
    spec = importlib.util.spec_from_file_location("rqw", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_monkeypatch_no_signals_at_slicing_no_fixed_horizon():
    code = re.sub(r'"""[\s\S]*?"""', "", SCRIPT.read_text())  # ignore docstrings
    assert "last_bar_context" not in code
    assert "signals_at(" not in code
    assert "install_lastbar_cache" not in code
    assert not re.search(r"horizon\s*=\s*\d", code)
    assert "generate_range" in code


def test_missing_generate_range_fails_loudly(monkeypatch):
    mod = _load()
    fake = types.ModuleType("signal_quant.registry")  # no generate_range attribute
    pkg = types.ModuleType("signal_quant")
    pkg.registry = fake
    monkeypatch.setitem(sys.modules, "signal_quant", pkg)
    monkeypatch.setitem(sys.modules, "signal_quant.registry", fake)
    with pytest.raises(mod.MissingQuantFastPath):
        mod.require_generate_range()


def test_entry_position_deciles_spread():
    from datetime import datetime, timedelta, timezone

    mod = _load()
    a = datetime(2024, 1, 1, tzinfo=timezone.utc)
    W = types.SimpleNamespace(test_start=a, test_end=a + timedelta(days=100))
    trades = [types.SimpleNamespace(entry_time=a + timedelta(days=d)) for d in (1, 15, 35, 55, 95, 100)]
    assert mod.entry_position_deciles(trades, [W]) == [1, 1, 0, 1, 0, 1, 0, 0, 0, 1]  # day 100 is outside
