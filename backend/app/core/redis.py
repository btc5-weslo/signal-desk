"""Redis client helpers.

Returns an injected client, a client from SIGNAL_REDIS_URL, or None when
no URL is configured (in-process mode for local dev and tests).
"""

from __future__ import annotations

from redis import Redis
from redis.asyncio import Redis as AsyncRedis


def sync_redis(settings, *, client=None):
    if client is not None:
        return client
    if not settings.redis_url:
        return None
    return Redis.from_url(settings.redis_url, decode_responses=True)


def async_redis(settings, *, client=None):
    if client is not None:
        return client
    if not settings.redis_url:
        return None
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)
