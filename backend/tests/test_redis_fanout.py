"""Redis-backed Broadcaster: tenant isolation and no unapproved fan-out."""

from __future__ import annotations

import asyncio
import json

import fakeredis
import fakeredis.aioredis
import pytest
from signal_shared import Signal

from app.core.config import Settings
from app.pipeline.emit import _publish_if_visible
from app.services.broadcaster import Broadcaster, encode_signal_envelope
from app.services.repository import MockRepository
from tests.test_contract import _signal


def _settings(**kwargs) -> Settings:
    return Settings(env="dev", jwt_secret="s" * 32, use_mock_data=False, **kwargs)


async def _pair():
    server = fakeredis.FakeServer()
    pub = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    sub = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    return pub, sub


def test_redis_unapproved_market_never_reaches_ws():
    async def _run():
        pub, sub = await _pair()
        repo = MockRepository(seed_mocks=False)
        settings = _settings(serve_unapproved=False)
        bc = Broadcaster(redis_client=sub)
        q = bc.subscribe("demo")
        await bc.start()
        try:
            publisher = Broadcaster(redis_client=pub)
            sig = _signal(id="unapproved-live", is_mock=False, strategy_id="alpha")
            _publish_if_visible(
                sig, repo=repo, settings=settings, broadcaster=publisher, alert_fn=None,
            )
            await asyncio.sleep(0.2)
            assert q.empty()
        finally:
            await bc.stop()
            await pub.aclose()
            await sub.aclose()

    asyncio.run(_run())


def test_redis_tenant_a_signal_never_reaches_tenant_b():
    async def _run():
        pub, sub = await _pair()
        bc = Broadcaster(redis_client=sub)
        q_a = bc.subscribe("tenant-a")
        q_b = bc.subscribe("tenant-b")
        await bc.start()
        try:
            publisher = Broadcaster(redis_client=pub)
            await publisher.publish(_signal(id="for-a", is_mock=False), tenant_id="tenant-a")
            raw = await asyncio.wait_for(q_a.get(), timeout=2)
            assert Signal.model_validate_json(raw).id == "for-a"
            await asyncio.sleep(0.15)
            assert q_b.empty()
        finally:
            await bc.stop()
            await pub.aclose()
            await sub.aclose()

    asyncio.run(_run())


def test_redis_global_signal_reaches_every_tenant():
    async def _run():
        pub, sub = await _pair()
        bc = Broadcaster(redis_client=sub)
        q_a = bc.subscribe("tenant-a")
        q_b = bc.subscribe("tenant-b")
        await bc.start()
        try:
            publisher = Broadcaster(redis_client=pub)
            await publisher.publish(_signal(id="global-live", is_mock=False), tenant_id=None)
            a = Signal.model_validate_json(await asyncio.wait_for(q_a.get(), timeout=2))
            b = Signal.model_validate_json(await asyncio.wait_for(q_b.get(), timeout=2))
            assert a.id == b.id == "global-live"
        finally:
            await bc.stop()
            await pub.aclose()
            await sub.aclose()

    asyncio.run(_run())


def test_encode_envelope_requires_tenant_id_key():
    sig = _signal(id="e1", is_mock=False)
    raw = encode_signal_envelope(sig, tenant_id="demo")
    body = json.loads(raw)
    assert body["tenant_id"] == "demo"
    assert body["signal"]["id"] == "e1"
    from app.services.broadcaster import decode_signal_envelope
    with pytest.raises(ValueError, match="tenant_id"):
        decode_signal_envelope(json.dumps({"signal": sig.model_dump(mode="json")}))


def test_in_process_publish_still_used_without_redis():
    async def _run():
        bc = Broadcaster()
        q = bc.subscribe("demo")
        await bc.publish(_signal(id="local", is_mock=False), tenant_id="demo")
        raw = await asyncio.wait_for(q.get(), timeout=1)
        assert Signal.model_validate_json(raw).id == "local"

    asyncio.run(_run())
