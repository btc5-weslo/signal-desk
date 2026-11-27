"""Strategy description / hypothesis metadata: Display lines, no result claims."""

from __future__ import annotations

import re
from pathlib import Path

from signal_quant.registry import list_strategies

HYPOTHESES_MD = Path(__file__).resolve().parents[1] / "docs" / "hypotheses.md"

# Result / performance language the Backend banned-claims filter rejects.
BANNED = re.compile(
    r"\b("
    r"profit|profits|profitability|profit[ -]?factor|"
    r"win[ _-]?rate|accuracy|accuracies|"
    r"returns?|sharpe|"
    r"guaranteed?|guarantee|"
    r"expectancy|expected[ -]?value|"
    r"after[ -]costs|"
    r"edge"
    r")\b",
    re.IGNORECASE,
)


def _display_lines() -> dict[str, str]:
    text = HYPOTHESES_MD.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for part in re.split(r"(?=## H[1-4]\b)", text):
        head = re.match(r"## (H[1-4])\b", part)
        if not head:
            continue
        body = re.search(r"\*\*Display\.\*\*\s+(.*?)(?=\n\n\*\*)", part, re.S)
        if not body:
            raise AssertionError(f"no Display line for {head.group(1)}")
        out[head.group(1)] = " ".join(body.group(1).split())
    return out


def test_hypothesis_matches_display_line_exactly_and_has_no_banned_words():
    displays = _display_lines()
    assert set(displays) == {"H1", "H2", "H3", "H4"}
    classes = {cls.hypothesis_id: cls for cls in list_strategies()}
    assert set(classes) == {"H1", "H2", "H3", "H4"}
    for hid, cls in classes.items():
        assert isinstance(cls.description, str) and cls.description.strip()
        assert "\n" not in cls.description.strip()
        assert cls.hypothesis == displays[hid], (hid, cls.hypothesis, displays[hid])
        for field, value in (("description", cls.description), ("hypothesis", cls.hypothesis)):
            hit = BANNED.search(value)
            assert hit is None, f"{cls.strategy_id}.{field} contains banned language: {hit.group(0)!r}"
        # Display lines in the doc itself must also be filter-safe.
        hit = BANNED.search(displays[hid])
        assert hit is None, f"{hid} Display line contains banned language: {hit.group(0)!r}"
