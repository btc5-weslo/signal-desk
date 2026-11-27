"""No silent ImportError fallbacks in product code.

Any `except ImportError` / `except ModuleNotFoundError` in backend/app, quant/signal_quant
or data/src must re-raise. A missing dependency has to fail loudly, never switch to a
second code path (QA gate requested by the Lead Architect).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ROOTS = [REPO / "backend" / "app", REPO / "quant" / "signal_quant", REPO / "data" / "src"]
CAUGHT = {"ImportError", "ModuleNotFoundError"}


def _names(node: ast.expr | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Tuple):
        return set().union(*(_names(e) for e in node.elts))
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def _findings() -> list[str]:
    out: list[str] = []
    for root in ROOTS:
        assert root.is_dir(), f"missing source root {root}"
        for py in sorted(root.rglob("*.py")):
            tree = ast.parse(py.read_text(), filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and _names(node.type) & CAUGHT:
                    if not (node.body and isinstance(node.body[-1], ast.Raise)):
                        out.append(f"{py.relative_to(REPO)}:{node.lineno}")
    return out


def test_no_silent_import_fallbacks():
    found = _findings()
    assert not found, "ImportError handlers that do not re-raise:\n" + "\n".join(found)


def test_claims_guard_does_not_silently_drop_price_patterns():
    from app.services import claims

    for text in ("only $19/month", "Upgrade to Pro", "free trial"):
        assert claims.tagline_violation(text), f"price phrase not caught: {text!r}"
