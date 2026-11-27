"""Per-market visibility: strategy + version + symbol + timeframe must be QA-approved."""

from __future__ import annotations

from signal_shared import Signal

from app.core.config import Settings


def is_live_signal_visible(
    sig: Signal, *, repo, tenant_id: str, settings: Settings,
) -> bool:
    if sig.is_mock:
        return bool(settings.use_mock_data)
    if settings.allow_unapproved():
        return True
    return repo.market_is_approved(
        sig.strategy_id, sig.strategy_version, sig.symbol, sig.timeframe,
        tenant_id=tenant_id,
    )
