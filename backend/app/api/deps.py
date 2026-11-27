from functools import lru_cache

from app.core.config import get_settings
from app.core.redis import async_redis, sync_redis
from app.services.broadcaster import Broadcaster
from app.services.repository import MockRepository
from app.services.stream_tokens import build_stream_token_store


@lru_cache
def get_repo() -> MockRepository:
    return MockRepository(seed_mocks=get_settings().use_mock_data)


@lru_cache
def get_broadcaster() -> Broadcaster:
    return Broadcaster(redis_client=async_redis(get_settings()))


@lru_cache
def get_stream_tokens():
    return build_stream_token_store(
        get_settings(), redis_client=sync_redis(get_settings()),
    )
