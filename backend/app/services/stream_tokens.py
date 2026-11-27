"""Short-lived, single-use, tenant-scoped WebSocket stream tokens.

Minted by POST /v1/stream/token so a web proxy can keep the API key
server-side and hand the browser a 60s token for first-message WS auth.

When SIGNAL_REDIS_URL is set, tokens live in Redis (SET EX 60, atomic
GETDEL / Lua fallback) so any API instance can consume them. The in-memory
store is used only when Redis is unset in dev. Prod requires Redis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from app.core.security import Principal

log = logging.getLogger(__name__)

STREAM_TOKEN_TTL = timedelta(seconds=60)
STREAM_TOKEN_TTL_SECONDS = 60
STREAM_TOKEN_KEY_PREFIX = "stream_token:"

_GETDEL_LUA = """
local v = redis.call('GET', KEYS[1])
if v then redis.call('DEL', KEYS[1]) end
return v
"""


@dataclass
class IssuedStreamToken:
    token: str
    tenant_id: str
    subject: str
    kind: str
    expires_at: datetime
    used: bool = False


class StreamTokenError(ValueError):
    pass


def _key(token: str) -> str:
    return f"{STREAM_TOKEN_KEY_PREFIX}{token}"


class StreamTokenStore:
    """In-memory fallback for local dev when Redis is not configured."""

    def __init__(self) -> None:
        self._items: dict[str, IssuedStreamToken] = {}

    def issue(self, principal: Principal, *, now: datetime | None = None) -> IssuedStreamToken:
        now = now or datetime.now(UTC)
        rec = IssuedStreamToken(
            token=token_urlsafe(32),
            tenant_id=principal.tenant_id,
            subject=principal.subject,
            kind=principal.kind,
            expires_at=now + STREAM_TOKEN_TTL,
        )
        self._items[rec.token] = rec
        return rec

    def consume(self, token: str, *, now: datetime | None = None) -> Principal:
        now = now or datetime.now(UTC)
        rec = self._items.get(token)
        if rec is None:
            raise StreamTokenError("invalid stream token")
        if rec.used:
            raise StreamTokenError("stream token already used")
        if rec.expires_at <= now:
            raise StreamTokenError("stream token expired")
        rec.used = True
        return Principal(tenant_id=rec.tenant_id, subject=rec.subject, kind=rec.kind)


class RedisStreamTokenStore:
    """Cross-instance store: SET EX 60, atomic get-and-delete on use."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def issue(self, principal: Principal, *, now: datetime | None = None) -> IssuedStreamToken:
        now = now or datetime.now(UTC)
        rec = IssuedStreamToken(
            token=token_urlsafe(32),
            tenant_id=principal.tenant_id,
            subject=principal.subject,
            kind=principal.kind,
            expires_at=now + STREAM_TOKEN_TTL,
        )
        payload = json.dumps({
            "tenant_id": rec.tenant_id,
            "subject": rec.subject,
            "kind": rec.kind,
            "expires_at": rec.expires_at.isoformat(),
        })
        self._redis.set(_key(rec.token), payload, ex=STREAM_TOKEN_TTL_SECONDS)
        return rec

    def consume(self, token: str, *, now: datetime | None = None) -> Principal:
        now = now or datetime.now(UTC)
        raw = self._getdel(_key(token))
        if raw is None:
            raise StreamTokenError("invalid or expired stream token")
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw)
        expires_at = datetime.fromisoformat(data["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise StreamTokenError("stream token expired")
        return Principal(
            tenant_id=data["tenant_id"],
            subject=data.get("subject", ""),
            kind=data.get("kind", "user"),
        )

    def _getdel(self, key: str):
        getdel = getattr(self._redis, "getdel", None)
        if callable(getdel):
            try:
                return getdel(key)
            except (AttributeError, TypeError, NotImplementedError):
                pass
        return self._redis.eval(_GETDEL_LUA, 1, key)


def build_stream_token_store(settings, *, redis_client=None):
    """Redis store when a URL/client is available; in-memory only in dev without Redis."""
    from app.core.redis import sync_redis

    client = sync_redis(settings, client=redis_client)
    if client is not None:
        return RedisStreamTokenStore(client)
    if settings.env == "prod":
        raise RuntimeError("stream tokens require Redis in prod (set SIGNAL_REDIS_URL)")
    return StreamTokenStore()
