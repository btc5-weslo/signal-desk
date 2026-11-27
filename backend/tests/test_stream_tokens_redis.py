"""Redis-backed stream tokens: single-use, expiry, and cross-instance consume."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import fakeredis
import pytest

from app.core.config import Settings
from app.core.security import Principal
from app.services.stream_tokens import (
    STREAM_TOKEN_KEY_PREFIX,
    STREAM_TOKEN_TTL_SECONDS,
    RedisStreamTokenStore,
    StreamTokenError,
    StreamTokenStore,
    build_stream_token_store,
)

PRINCIPAL = Principal(tenant_id="demo", subject="user-1", kind="user")
OTHER = Principal(tenant_id="other", subject="user-2", kind="user")


def test_redis_token_is_single_use():
    r = fakeredis.FakeRedis(decode_responses=True)
    store = RedisStreamTokenStore(r)
    rec = store.issue(PRINCIPAL)
    got = store.consume(rec.token)
    assert got.tenant_id == "demo" and got.subject == "user-1"
    with pytest.raises(StreamTokenError):
        store.consume(rec.token)


def test_redis_token_expires():
    r = fakeredis.FakeRedis(decode_responses=True)
    store = RedisStreamTokenStore(r)
    rec = store.issue(PRINCIPAL)
    key = f"{STREAM_TOKEN_KEY_PREFIX}{rec.token}"
    ttl = r.ttl(key)
    assert 0 < ttl <= STREAM_TOKEN_TTL_SECONDS
    r.pexpire(key, 1)
    time.sleep(0.02)
    with pytest.raises(StreamTokenError):
        store.consume(rec.token)


def test_redis_token_payload_clock_expiry():
    r = fakeredis.FakeRedis(decode_responses=True)
    store = RedisStreamTokenStore(r)
    past = datetime.now(UTC) - timedelta(seconds=1)
    rec = store.issue(PRINCIPAL, now=past - timedelta(seconds=60))
    # Token is still in Redis (TTL is wall-clock from SET EX), but payload
    # expires_at is in the past — consume must reject it.
    with pytest.raises(StreamTokenError, match="expired"):
        store.consume(rec.token, now=datetime.now(UTC))


def test_redis_token_cross_instance():
    server = fakeredis.FakeServer()
    a = fakeredis.FakeRedis(server=server, decode_responses=True)
    b = fakeredis.FakeRedis(server=server, decode_responses=True)
    store_a = RedisStreamTokenStore(a)
    store_b = RedisStreamTokenStore(b)
    rec = store_a.issue(PRINCIPAL)
    got = store_b.consume(rec.token)
    assert got.tenant_id == "demo"
    with pytest.raises(StreamTokenError):
        store_a.consume(rec.token)


def test_build_store_uses_redis_when_url_or_client_set():
    r = fakeredis.FakeRedis(decode_responses=True)
    s = Settings(env="dev", jwt_secret="s" * 32, redis_url=None)
    store = build_stream_token_store(s, redis_client=r)
    assert isinstance(store, RedisStreamTokenStore)


def test_build_store_memory_only_in_dev_without_redis():
    s = Settings(env="dev", jwt_secret="s" * 32, redis_url=None)
    store = build_stream_token_store(s)
    assert isinstance(store, StreamTokenStore)


def test_build_store_prod_requires_redis():
    s = Settings(env="prod", jwt_secret="s" * 32, use_mock_data=False, redis_url=None)
    with pytest.raises(RuntimeError, match="Redis"):
        build_stream_token_store(s)
