import hashlib
import inspect
import json
import logging
import random
import time
from collections.abc import Callable
from functools import lru_cache, wraps
from typing import Any, cast

from pydantic import TypeAdapter
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def get_cache() -> Redis:
    return Redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)


class CacheNamespace:
    def __init__(self, name: str, *, ttl: int = 300, jitter: float = 0.1) -> None:
        if not 0 <= jitter < 1:
            raise ValueError("jitter must be in [0, 1)")
        self.name = name
        self.ttl = ttl
        self.jitter = jitter
        self._version_key = f"cache:{name}:version"

    def _version(self) -> str:
        cache = get_cache()
        version = cache.get(self._version_key)
        if version is None:
            cache.set(self._version_key, str(time.time_ns()), nx=True)
            version = cache.get(self._version_key)
        return str(version)

    def key(self, func: Callable[..., Any], arguments: dict[str, Any]) -> str:
        return self.keys(func, [arguments])[0]

    def keys(
        self, func: Callable[..., Any], arguments: list[dict[str, Any]]
    ) -> list[str]:
        prefix = f"cache:{self.name}:{self._version()}:{func.__qualname__}"
        return [
            f"{prefix}:{hashlib.sha256(json.dumps(a, sort_keys=True, default=str).encode()).hexdigest()[:16]}"
            for a in arguments
        ]

    def expiry(self, ttl: int | None = None) -> int:
        base = ttl or self.ttl
        return max(1, round(base * random.uniform(1 - self.jitter, 1 + self.jitter)))  # noqa: S311

    def invalidate(self) -> None:
        get_cache().set(self._version_key, str(time.time_ns()))


def cached[**P, R](
    namespace: CacheNamespace, schema: Any, *, ttl: int | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    adapter = TypeAdapter(schema)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                arguments = {k: v for k, v in bound.arguments.items() if k != "self"}
                key = namespace.key(func, arguments)
                hit = cast(str | None, get_cache().get(key))
                if hit is not None:
                    return cast(R, adapter.validate_json(hit))
            except RedisError:
                logger.warning("Cache read failed, skipping cache", exc_info=True)
                return func(*args, **kwargs)
            result = func(*args, **kwargs)
            try:
                get_cache().set(
                    key, adapter.dump_json(result), ex=namespace.expiry(ttl)
                )
            except RedisError:
                logger.warning("Cache write failed", exc_info=True)
            return result

        return wrapper

    return decorator


def invalidates[**P, R](
    *namespaces: CacheNamespace,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Invalidate `namespaces` after the decorated function succeeds.

    If Redis is unavailable the failure is logged and staleness is bounded by
    the namespace TTL.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = func(*args, **kwargs)
            for namespace in namespaces:
                try:
                    namespace.invalidate()
                except RedisError:
                    logger.warning(
                        "Cache invalidation failed for %s",
                        namespace.name,
                        exc_info=True,
                    )
            return result

        return wrapper

    return decorator
