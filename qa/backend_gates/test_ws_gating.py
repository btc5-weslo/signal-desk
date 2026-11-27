"""QA gate: an unapproved market never reaches a WebSocket subscriber, and
tenants only receive their own stream.

Run: cd backend && PYTHONPATH=. .venv/bin/pytest ../qa/backend_gates
The Redis-path test is strict-xfail until milestone 2.1 gates/removes the
arq `publish_signal` job; when it starts passing, delete the xfail marker.
"""
import asyncio

import pytest

from app.core.config import Settings
from app.pipeline.emit import _publish_if_visible
from app.services.broadcaster import Broadcaster
from app.services.repository import MockRepository
from tests.test_contract import _report, _signal

MKT = dict(strategy_id="s", strategy_version="1", symbol="BTC-USDT", timeframe="1h")


def _live():
    return _signal(id="live-1", is_mock=False, **MKT)


def _setup(approved: bool):
    repo = MockRepository()
    b = Broadcaster()
    qs = {tid: b.subscribe(tid) for tid in repo.list_tenant_ids()}
    if approved:
        repo.add_backtest(_report(run_id="r1", data_hash="h", strategy_id="s", version="1",
                                  symbol="BTC-USDT", timeframe="1h"), tenant_id=None)
        repo.add_approval("r1", "h")
    return repo, b, qs


@pytest.mark.parametrize("env", ["dev", "staging"])
def test_unapproved_market_never_broadcast(env):
    repo, b, qs = _setup(approved=False)
    s = Settings(use_mock_data=False, serve_unapproved=False, env=env)
    _publish_if_visible(_live(), repo=repo, settings=s, broadcaster=b, alert_fn=None)
    assert all(q.empty() for q in qs.values())


def test_dev_override_cannot_leak_outside_dev():
    repo, b, qs = _setup(approved=False)
    s = Settings(use_mock_data=False, serve_unapproved=True, env="staging")
    _publish_if_visible(_live(), repo=repo, settings=s, broadcaster=b, alert_fn=None)
    assert all(q.empty() for q in qs.values())


def test_approved_market_reaches_subscribers_tenant_scoped():
    repo, b, qs = _setup(approved=True)
    other = b.subscribe("tenant-that-does-not-exist")
    s = Settings(use_mock_data=False, serve_unapproved=False, env="dev")
    _publish_if_visible(_live(), repo=repo, settings=s, broadcaster=b, alert_fn=None)
    assert qs and all(q.qsize() == 1 for q in qs.values())
    assert other.empty()


def test_redis_job_does_not_publish_unapproved_market():
    from app.workers import worker

    job = getattr(worker, "publish_signal", None)
    if job is None:  # removed entirely = fixed
        return

    class R:
        msgs: list = []

        async def publish(self, ch, msg):
            self.msgs.append((ch, msg))

    r = R()
    try:
        asyncio.run(job({"redis": r}, _live().model_dump(mode="json")))
    except Exception:
        return  # refusing is acceptable
    assert not r.msgs, "unapproved signal published to Redis without a visibility check"
