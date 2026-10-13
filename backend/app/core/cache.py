from functools import lru_cache

from redis import Redis

from app.core.config import settings


@lru_cache
def get_cache() -> Redis:
    """Client for the cache Redis instance (not the Celery broker)."""
    return Redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)
