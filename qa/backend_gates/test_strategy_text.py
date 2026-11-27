"""Strategy text shown in the product.

- Each registry class's `hypothesis` equals its **Display.** line in quant/docs/hypotheses.md
  word for word (the pre-registered **Hypothesis.** sentence never reaches the product).
- `hypothesis_id` matches the doc section; every H-section is used exactly once.
- `description` and `hypothesis` pass the backend banned-claims check and QA's
  performance-language list.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.claims import tagline_violation
from signal_quant.registry import list_strategies

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "quant" / "docs" / "hypotheses.md"

PERFORMANCE_WORDS = re.compile(
    r"\bexpectancy\b|\bwin\s*rate\b|\baccura(?:te|cy)\b|\bprofit(?:able|s)?\b|\breturns?\b"
    r"|\boutperform|\bbeats?\s+the\s+market\b|\bsharpe\b|\bprofit\s+factor\b|\bdrawdown\b"
    r"|\d+(?:\.\d+)?\s*%|\bedge\b|\balpha\b",
    re.IGNORECASE,
)


def _doc_sections() -> dict[str, dict[str, str]]:
    text = DOC.read_text()
    out: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"^## (H\d+)\b.*?(?=^## H\d+\b|\Z)", text, re.M | re.S):
        body = m.group(0)
        sid = re.search(r"\*\*Strategy id:\*\*\s*`([^`]+)`", body)
        disp = re.search(r"^\*\*Display\.\*\*\s*(.+)$", body, re.M)
        assert sid and disp, f"{m.group(1)} needs a Strategy id and a **Display.** line"
        out[m.group(1)] = {"strategy_id": sid.group(1), "display": disp.group(1).strip()}
    return out


SECTIONS = _doc_sections()
CLASSES = list(list_strategies())


def _sid(cls) -> str:
    return getattr(cls, "strategy_id", None) or getattr(cls, "id", None) or getattr(cls, "name")


def test_every_section_used_once():
    assert sorted(c.hypothesis_id for c in CLASSES) == sorted(SECTIONS)


@pytest.mark.parametrize("cls", CLASSES, ids=_sid)
def test_hypothesis_matches_display_line(cls):
    sec = SECTIONS[cls.hypothesis_id]
    assert _sid(cls) == sec["strategy_id"]
    assert cls.hypothesis == sec["display"]


@pytest.mark.parametrize("cls", CLASSES, ids=_sid)
@pytest.mark.parametrize("field", ["description", "hypothesis"])
def test_text_has_no_claims(cls, field):
    text = getattr(cls, field)
    assert text, f"{_sid(cls)}.{field} is empty"
    assert tagline_violation(text) is None
    assert not PERFORMANCE_WORDS.search(text), PERFORMANCE_WORDS.search(text).group(0)
