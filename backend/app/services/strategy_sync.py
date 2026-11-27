"""Idempotent sync of Quant-registered strategies into the catalog.

Seeded rows are global (tenant_id None), unvalidated (latest_run_id stays
unset unless a previous sync already stored one), and carry no metrics.

Reads ``signal_quant.registry.list_strategies()`` (``strategy_id``,
``version``, ``supported``, plus optional ``description``, ``hypothesis``,
and ``hypothesis_id``). Missing text attrs are stored as null — the name
and docstring are never copied into ``description``. A bare id like ``H1``
in ``hypothesis`` is moved to ``hypothesis_id``. ``description`` and
``hypothesis`` are run through the existing banned-claims check; a hit is
dropped (null) and logged.
"""

from __future__ import annotations

import logging
import re

from signal_shared import TIMEFRAMES, AssetClass, Strategy

from app.services.claims import tagline_violation

log = logging.getLogger(__name__)

_BARE_HYPOTHESIS_ID = re.compile(r"^H\d+$", re.IGNORECASE)


def _list_registry_classes() -> list:
    from signal_quant.registry import list_strategies

    return list(list_strategies())


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _drop_banned(strategy_id: str, version: str, field: str, text: str | None) -> str | None:
    if text is None:
        return None
    hit = tagline_violation(text)
    if hit:
        log.error(
            "strategy %s version %s: dropping %s; banned claim %r",
            strategy_id, version, field, hit,
        )
        return None
    return text


def strategy_from_registry_class(cls) -> Strategy | None:
    """Map a Quant strategy class to a catalog row. No metrics are invented."""
    if getattr(cls, "is_mock", False):
        return None
    sid = getattr(cls, "strategy_id", None)
    version = getattr(cls, "version", None) or getattr(cls, "strategy_version", None)
    if not sid or not version:
        log.warning("skipping registry class %r: missing strategy_id or version", cls)
        return None
    version = str(version)
    supported = getattr(cls, "supported", ()) or ()
    asset_classes: list[AssetClass] = []
    timeframes: list[str] = []
    for pair in supported:
        try:
            ac, tf = pair
        except (TypeError, ValueError):
            continue
        try:
            parsed = AssetClass(ac)
        except ValueError:
            continue
        if parsed not in asset_classes:
            asset_classes.append(parsed)
        if tf in TIMEFRAMES and tf not in timeframes:
            timeframes.append(tf)
    name = getattr(cls, "name", None) or sid
    description = _optional_text(getattr(cls, "description", None))
    hypothesis = _optional_text(getattr(cls, "hypothesis", None))
    hypothesis_id = _optional_text(getattr(cls, "hypothesis_id", None))
    if hypothesis_id is None and hypothesis and _BARE_HYPOTHESIS_ID.fullmatch(hypothesis):
        hypothesis_id = hypothesis
        hypothesis = None
    elif hypothesis and _BARE_HYPOTHESIS_ID.fullmatch(hypothesis):
        if hypothesis_id is None:
            hypothesis_id = hypothesis
        hypothesis = None
    description = _drop_banned(sid, version, "description", description)
    hypothesis = _drop_banned(sid, version, "hypothesis", hypothesis)
    return Strategy(
        id=sid,
        version=version,
        name=name,
        description=description,
        hypothesis=hypothesis,
        hypothesis_id=hypothesis_id,
        asset_classes=asset_classes,
        timeframes=timeframes,
        latest_run_id=None,
    )


def sync_strategies(repo) -> int:
    """Upsert registered strategies as global catalog rows. Returns rows written."""
    classes = _list_registry_classes()
    written = 0
    for cls in classes:
        try:
            row = strategy_from_registry_class(cls)
        except (ValueError, TypeError) as exc:
            log.warning("skipping registry class %r: %s", cls, exc)
            continue
        if row is None:
            continue
        if repo.upsert_strategy(row, tenant_id=None):
            written += 1
    return written
