import pytest
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import cache
from app.core.cache import CacheNamespace, cached, invalidates
from tests.utils.cache import FakeRedis

NAMESPACE = CacheNamespace("test_item")


class Item(BaseModel):
    name: str


class Repo:
    def __init__(self) -> None:
        self.calls = 0
        self.name = "a"

    @cached(NAMESPACE, Item)
    def read(self, item_id: int, *, upper: bool = False) -> Item:
        self.calls += 1
        return Item(name=self.name.upper() if upper else self.name)

    @invalidates(NAMESPACE)
    def write(self, name: str) -> None:
        self.name = name


def test_cached_serves_second_call_from_cache() -> None:
    repo = Repo()
    assert repo.read(1) == Item(name="a")
    assert repo.read(1) == Item(name="a")
    assert repo.calls == 1


def test_cache_key_depends_on_arguments() -> None:
    repo = Repo()
    repo.read(1)
    repo.read(2)
    repo.read(1, upper=True)
    assert repo.calls == 3
    repo.read(1, upper=False)  # same as read(1) once defaults are applied
    assert repo.calls == 3


def test_invalidates_drops_cached_values() -> None:
    repo = Repo()
    assert repo.read(1).name == "a"
    repo.write("b")
    assert repo.read(1).name == "b"
    assert repo.calls == 2


def test_version_is_reissued_if_evicted(fake_cache: FakeRedis) -> None:
    repo = Repo()
    repo.read(1)
    fake_cache.data.pop("cache:test_item:version")
    repo.read(1)
    assert repo.calls == 2


def test_redis_failure_falls_back_to_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> None:
        raise RedisConnectionError("down")

    monkeypatch.setattr(cache, "get_cache", broken)
    repo = Repo()
    assert repo.read(1) == Item(name="a")
    repo.write("b")  # invalidation failure must not break the write
    assert repo.name == "b"


def test_expiry_is_jittered_within_bounds() -> None:
    namespace = CacheNamespace("jitter", ttl=100, jitter=0.1)
    values = {namespace.expiry() for _ in range(200)}
    assert len(values) > 1
    assert all(90 <= value <= 110 for value in values)
    assert all(180 <= namespace.expiry(200) <= 220 for _ in range(50))


def test_zero_jitter_is_exact_ttl() -> None:
    assert CacheNamespace("exact", ttl=60, jitter=0).expiry() == 60


def test_invalid_jitter_is_rejected() -> None:
    with pytest.raises(ValueError, match="jitter"):
        CacheNamespace("bad", jitter=1)


def test_cached_value_is_stored_with_jittered_ttl(fake_cache: FakeRedis) -> None:
    Repo().read(1)
    ttls = [ex for key, ex in fake_cache.expiries.items() if ex is not None]
    assert len(ttls) == 1
    assert 270 <= ttls[0] <= 330


def test_cache_write_failure_still_returns_result(fake_cache: FakeRedis) -> None:
    fake_cache.fail_writes = True
    assert Repo().read(1) == Item(name="a")
