import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.workers.worker import fanout_alerts, publish_signal


class _FakeRedis:
    def __init__(self):
        self.msgs = []

    async def publish(self, channel, message):
        self.msgs.append((channel, message))
        return 1


def test_publish_signal_rejects_lookahead():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    payload = {
        "id": "x", "strategy_id": "s", "strategy_version": "1", "symbol": "BTC-USDT",
        "asset_class": "crypto", "timeframe": "1h", "side": "flat",
        "generated_at": (t - timedelta(minutes=1)).isoformat(),
        "bar_close_time": t.isoformat(), "horizon_bars": 1, "confidence": 0.5, "rationale": "r",
    }
    with pytest.raises(ValidationError):
        asyncio.run(publish_signal({"redis": _FakeRedis()}, payload))


def test_publish_signal_routes_through_visibility(monkeypatch):
    from app.pipeline import emit as emit_mod
    from tests.test_contract import _signal

    seen = []

    def _capture(sig, *, repo, settings, broadcaster, alert_fn):
        seen.append(sig.id)

    monkeypatch.setattr(emit_mod, "_publish_if_visible", _capture)
    sig = _signal(id="live-1", is_mock=False)
    asyncio.run(publish_signal({"redis": _FakeRedis()}, sig.model_dump(mode="json")))
    assert seen == ["live-1"]


def test_fanout_alerts_is_noop():
    assert asyncio.run(fanout_alerts({"redis": _FakeRedis()}, {})) is None


def test_worker_registers_pipeline_cron():
    from app.workers.worker import WorkerSettings, fanout_alerts, scan_pipeline
    assert scan_pipeline in WorkerSettings.functions
    assert fanout_alerts in WorkerSettings.functions
    assert WorkerSettings.cron_jobs
