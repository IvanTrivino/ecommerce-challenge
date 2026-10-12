from redis.exceptions import ConnectionError as RedisConnectionError


class FakeRedis:
    """Minimal in-memory stand-in for the Redis commands the cache uses."""

    def __init__(self) -> None:
        self.data: dict[str, str | bytes] = {}
        self.expiries: dict[str, int | None] = {}
        self.fail_writes = False

    def get(self, key: str) -> str | bytes | None:
        return self.data.get(key)

    def mget(self, keys: list[str]) -> list[str | bytes | None]:
        return [self.data.get(key) for key in keys]

    def set(
        self, key: str, value: str | bytes, nx: bool = False, ex: int | None = None
    ) -> None:
        if self.fail_writes and not key.endswith(":version"):
            raise RedisConnectionError("down")
        self.expiries[key] = ex
        if nx and key in self.data:
            return
        self.data[key] = value.decode() if isinstance(value, bytes) else value
