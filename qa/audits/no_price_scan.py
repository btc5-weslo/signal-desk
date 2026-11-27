#!/usr/bin/env python3
"""Fail if any price/pricing/paywall amount appears in user-facing code or docs.
Usage: python qa/audits/no_price_scan.py [root ...]  (default: web backend shared docs)
Market prices (entry/stop/TP) are fine; this targets *product* pricing.

Exceptions (narrow, per line, reason required):
  1. qa/audits/price_allowlist.txt (QA-owned): `path | exact line text | reason`.
     Matches only that file and that stripped line. Unused entries FAIL the scan,
     so stale exceptions can't linger.
  2. Inline `qa-allow-price: <reason>` -- only honoured in test files
     (a `tests/` dir or *.test.* / test_*.py). Product code can't self-allowlist.
"""
import re, sys, pathlib
PATTERNS = [
    r"\bpricing\b", r"\bper\s+month\b", r"/\s*mo(nth)?\b", r"\bper\s+year\b", r"/\s*yr\b",
    r"\bsubscribe\s+(now|for)\b", r"\bpaywall\b", r"\bfree\s+trial\b", r"\bupgrade\s+to\s+(pro|premium)\b",
    r"\b(plan|tier)s?\b.{0,40}[$€£]\s?\d", r"[$€£]\s?\d+(\.\d{2})?\s*(/|per)\s*(mo|month|yr|year|week)",
    r"\bcheckout\b", r"\bstripe\b",
]
RX = re.compile("|".join(PATTERNS), re.I)
INLINE = re.compile(r"qa-allow-price:\s*\S")
EXTS = {".ts",".tsx",".js",".jsx",".py",".md",".mdx",".json",".html",".css",".yaml",".yml",".txt"}
SKIP = {"node_modules",".next","dist","build",".git","__pycache__",".venv"}
ALLOWLIST = pathlib.Path(__file__).with_name("price_allowlist.txt")
REPO = pathlib.Path(__file__).resolve().parents[2]


def _is_test_file(f: pathlib.Path) -> bool:
    n = f.name
    return "tests" in f.parts or ".test." in n or ".spec." in n or n.startswith("test_")


def load_allowlist(path=ALLOWLIST):
    entries = {}
    if not path.exists():
        return entries
    for ln, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in raw.split(" | ")]
        if len(parts) != 3 or not all(parts):
            raise SystemExit(f"{path}:{ln}: need `path | exact line text | reason`")
        entries[(parts[0], parts[1])] = parts[2]
    return entries


def _rel(f: pathlib.Path) -> str:
    try:
        return f.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return f.as_posix()


def main(roots, allow=None):
    allow = load_allowlist() if allow is None else allow
    used, hits, scanned_roots = set(), [], []
    for root in roots:
        p = pathlib.Path(root)
        if not p.exists(): continue
        scanned_roots.append(_rel(p))
        for f in p.rglob("*"):
            if f.suffix not in EXTS or any(s in f.parts for s in SKIP) or not f.is_file(): continue
            rel = _rel(f)
            for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if not RX.search(line): continue
                if INLINE.search(line) and _is_test_file(f): continue
                key = (rel, line.strip())
                if key in allow:
                    used.add(key); continue
                hits.append(f"{rel}:{i}: {line.strip()[:140]}")
    stale = [k for k in allow if k not in used
             and any(k[0] == r or k[0].startswith(r.rstrip("/") + "/") for r in scanned_roots)]
    for h in hits: print(h)
    for path, text in stale: print(f"STALE allowlist entry (no matching line): {path} | {text}")
    print(f"no_price_scan: {len(hits)} finding(s), {len(stale)} stale allowlist entr(y/ies)")
    return 1 if hits or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["web","backend","shared","docs"]))
