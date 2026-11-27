"""Banned-claims and vendored price-pattern guards."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.services.claims import tagline_violation
from app.services.price_patterns import PATTERNS as VENDED_PRICE_PATTERNS

_QA = Path(__file__).resolve().parents[2] / "qa" / "audits" / "no_price_scan.py"


def test_vendored_price_patterns_match_no_price_scan():
    assert _QA.is_file(), "qa/audits/no_price_scan.py is missing from the repo"
    spec = importlib.util.spec_from_file_location("qa_no_price_scan", _QA)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert list(VENDED_PRICE_PATTERNS) == list(mod.PATTERNS)


def test_price_phrase_is_caught():
    assert tagline_violation("$49/month")  # qa-allow-price: fixture proving the guard rejects price phrases
    assert tagline_violation("only $19/month")  # qa-allow-price: fixture proving the guard rejects price phrases
    assert tagline_violation("Upgrade to Pro")  # qa-allow-price: fixture proving the guard rejects price phrases
    assert tagline_violation("free trial")  # qa-allow-price: fixture proving the guard rejects price phrases


def test_price_patterns_raise_if_both_unavailable(monkeypatch):
    from app.services import claims

    monkeypatch.setattr(claims, "_load_qa_price_patterns", lambda: None)
    monkeypatch.setattr(claims, "VENDED_PRICE_PATTERNS", [])
    with pytest.raises(RuntimeError, match="price patterns are unavailable"):
        claims._price_patterns()


def test_stricter_claims_catch_win_rate_and_percent():
    assert tagline_violation("improves win rate")
    assert tagline_violation("high accuracy")
    assert tagline_violation("will outperform the market")
    assert tagline_violation("great profit factor")
    assert tagline_violation("high sharpe")
    assert tagline_violation("returns of 12%")
