"""Banned-claims check for tenant taglines and strategy catalog text.

Product copy only — never applied to metrics labels or backtest report values.
Price phrases come from qa/audits/no_price_scan.py when that file is present,
otherwise the vendored copy in ``app.services.price_patterns``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.services.price_patterns import PATTERNS as VENDED_PRICE_PATTERNS

# Existing copy rules, plus a stricter set used only for taglines and
# strategy description/hypothesis (not for metrics or report values).
_CLAIM_PATTERNS = [
    r"\bguaranteed\b",
    r"\bvalidated\b",
    r"\brisk[-\s]?free\b",
    r"\bsure\s+win\b",
    r"\bcan'?t\s+lose\b",
    r"\bcannot\s+lose\b",
    r"\b100%\s+accurate\b",
    r"\bprofitab(le|ility)\b",
    r"\bexpectancy\b",
    r"\bhigh\s+win\s+rate\b",
    r"\bwin\s+rate\b",
    r"\baccurate\b",
    r"\baccuracy\b",
    r"\boutperform\w*",
    r"\bprofit\s+factor\b",
    r"\bsharpe\b",
    r"\d+(\.\d+)?\s?%",
]


def _load_qa_price_patterns() -> list[str] | None:
    path = Path(__file__).resolve().parents[3] / "qa" / "audits" / "no_price_scan.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("qa_no_price_scan", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw = getattr(mod, "PATTERNS", None)
    if not raw:
        return None
    return list(raw)


def _price_patterns() -> list[str]:
    from_qa = _load_qa_price_patterns()
    if from_qa:
        return from_qa
    vendored = list(VENDED_PRICE_PATTERNS)
    if vendored:
        return vendored
    raise RuntimeError(
        "price patterns are unavailable: qa/audits/no_price_scan.py is missing "
        "and the vendored list is empty"
    )


def _compile() -> re.Pattern[str]:
    return re.compile("|".join(_price_patterns() + _CLAIM_PATTERNS), re.IGNORECASE)


_RX = _compile()


class BannedClaimError(ValueError):
    """Tagline contains a banned claim or product-pricing phrase."""


def tagline_violation(text: str | None) -> str | None:
    if text is None:
        return None
    m = _RX.search(text)
    return m.group(0) if m else None


def require_clean_tagline(text: str | None) -> str | None:
    if text is None:
        return None
    hit = tagline_violation(text)
    if hit:
        raise BannedClaimError(f"tagline contains a banned claim: {hit!r}")
    return text


def sanitize_tagline(text: str | None) -> str | None:
    """Drop the tagline on read if it would fail the write-time check."""
    if text is None or tagline_violation(text):
        return None
    return text
