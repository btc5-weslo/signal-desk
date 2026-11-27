"""Platform-level licensed data sources. Tenants cannot set or override this list."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Hard-coded: never licensed, even if present in SIGNAL_LICENSED_DATA_SOURCES.
NEVER_LICENSED = frozenset({"binance_vision", "yfinance"})
CCXT_PREFIX = "ccxt:"


def is_never_licensed(source: str | None) -> bool:
    s = (source or "").strip().lower()
    if not s:
        return False
    return s in NEVER_LICENSED or s.startswith(CCXT_PREFIX)


def filter_licensed_sources(sources: list[str]) -> list[str]:
    """Drop never-licensed names (with a warning) and keep the rest in order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in sources:
        item = (raw or "").strip()
        if not item or item in seen:
            continue
        if is_never_licensed(item):
            log.warning(
                "dropping never-licensed data source %r from SIGNAL_LICENSED_DATA_SOURCES",
                raw,
            )
            continue
        seen.add(item)
        out.append(item)
    return out


def is_licensed_source(source: str | None, licensed: list[str] | None = None) -> bool:
    """True if `source` is on the platform allow-list and is not never-licensed."""
    if not source or is_never_licensed(source):
        return False
    if licensed is None:
        from app.core.config import get_settings

        licensed = get_settings().licensed_data_sources
    return source in licensed
