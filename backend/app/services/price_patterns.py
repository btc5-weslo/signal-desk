"""Vendored copy of qa/audits/no_price_scan.py PATTERNS.

Used when that file is not present (backend-only deploy). A test asserts
this list stays identical to ``no_price_scan.PATTERNS`` so drift fails CI.
"""

PATTERNS = [
    r"\bpricing\b", r"\bper\s+month\b", r"/\s*mo(nth)?\b", r"\bper\s+year\b", r"/\s*yr\b",
    r"\bsubscribe\s+(now|for)\b", r"\bpaywall\b", r"\bfree\s+trial\b", r"\bupgrade\s+to\s+(pro|premium)\b",
    r"\b(plan|tier)s?\b.{0,40}[$€£]\s?\d", r"[$€£]\s?\d+(\.\d{2})?\s*(/|per)\s*(mo|month|yr|year|week)",
    r"\bcheckout\b", r"\bstripe\b",
]
