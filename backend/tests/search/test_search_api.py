import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.core.search import get_es
from app.repositories import ProductRepository
from app.search.indexer import process_once
from app.search.products_index import ensure_index
from tests.search.conftest import refresh
from tests.utils.product import create_random_category, create_random_product

URL = f"{settings.API_V1_STR}/products/search"


@pytest.fixture(autouse=True)
def _index() -> None:
    ensure_index(get_es())


def index_all() -> None:
    with Session(engine) as session:
        process_once(session, get_es())
    refresh()


def test_search_returns_products_from_postgres(client: TestClient, db: Session) -> None:
    product = create_random_product(db)
    product.name = "Running Shoe"
    ProductRepository(db).save(product)
    create_random_product(db)
    index_all()

    response = client.get(URL, params={"q": "running shoes"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["data"][0]["id"] == str(product.id)
    assert body["data"][0]["sku"] == product.sku


def test_search_by_sku_and_category_name(client: TestClient, db: Session) -> None:
    category = create_random_category(db)
    category.name = "Outdoor Gear"
    from app.repositories import ProductCategoryRepository

    ProductCategoryRepository(db).save(category)
    product = create_random_product(db, category)
    index_all()

    by_sku = client.get(URL, params={"q": product.sku.upper()}).json()
    assert [p["id"] for p in by_sku["data"]] == [str(product.id)]
    by_category = client.get(URL, params={"q": "outdoor"}).json()
    assert [p["id"] for p in by_category["data"]] == [str(product.id)]


def test_deleted_product_not_returned_even_if_index_is_stale(
    client: TestClient, db: Session
) -> None:
    product = create_random_product(db)
    product.name = "Stale Gadget"
    ProductRepository(db).save(product)
    index_all()
    ProductRepository(db).delete(product)  # indexer has not run yet

    body = client.get(URL, params={"q": "gadget"}).json()
    assert body["data"] == []


def test_pagination(client: TestClient, db: Session) -> None:
    for _ in range(3):
        product = create_random_product(db)
        product.name = "Pager Item"
        ProductRepository(db).save(product)
    index_all()

    page = client.get(URL, params={"q": "pager", "limit": 2}).json()
    assert page["count"] == 3
    assert len(page["data"]) == 2
    rest = client.get(URL, params={"q": "pager", "limit": 2, "skip": 2}).json()
    assert len(rest["data"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "x", "limit": 0},
        {"q": "x", "limit": 101},
        {"q": "x", "skip": -1},
    ],
)
def test_validation(client: TestClient, params: dict[str, object]) -> None:
    assert client.get(URL, params=params).status_code == 422


def test_no_match(client: TestClient) -> None:
    body = client.get(URL, params={"q": f"nomatch{uuid.uuid4().hex}"}).json()
    assert body == {"data": [], "count": 0}


def test_search_unavailable_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import elasticsearch

    def boom(*_: object, **__: object) -> None:
        raise elasticsearch.ConnectionError("down")

    monkeypatch.setattr(get_es(), "search", boom)
    response = client.get(URL, params={"q": "anything"})
    assert response.status_code == 503


def test_second_search_is_served_from_cache(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = create_random_product(db)
    product.name = "Cacheable Lamp"
    ProductRepository(db).save(product)
    index_all()
    first = client.get(URL, params={"q": "lamp"}).json()

    def no_db(*_: object, **__: object) -> None:
        raise AssertionError("Postgres should not be queried on a cache hit")

    monkeypatch.setattr(ProductRepository, "get_many", no_db)
    assert client.get(URL, params={"q": "lamp"}).json() == first


def test_search_shares_entries_with_get_by_id(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = create_random_product(db)
    product.name = "Shared Chair"
    ProductRepository(db).save(product)
    index_all()
    assert client.get(f"{settings.API_V1_STR}/products/{product.id}").status_code == 200

    def no_db(*_: object, **__: object) -> None:
        raise AssertionError("Postgres should not be queried on a cache hit")

    monkeypatch.setattr(ProductRepository, "get_many", no_db)
    body = client.get(URL, params={"q": "chair"}).json()
    assert [p["id"] for p in body["data"]] == [str(product.id)]


def test_product_update_invalidates_cached_search_data(
    client: TestClient, db: Session
) -> None:
    from app.repositories import ProductCategoryRepository
    from app.schemas import ProductUpdate
    from app.services import ProductService

    product = create_random_product(db)
    product.name = "Old Desk"
    ProductRepository(db).save(product)
    index_all()
    client.get(URL, params={"q": "desk"})  # warms the cache

    ProductService(ProductRepository(db), ProductCategoryRepository(db)).update_product(
        product.id, ProductUpdate(price=77)
    )
    body = client.get(URL, params={"q": "desk"}).json()
    assert body["data"][0]["price"] == "77.00"


def test_search_works_when_cache_is_down(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    from app.core import cache

    product = create_random_product(db)
    product.name = "Resilient Sofa"
    ProductRepository(db).save(product)
    index_all()

    def down() -> None:
        raise RedisConnectionError("down")

    monkeypatch.setattr(cache, "get_cache", down)
    body = client.get(URL, params={"q": "sofa"}).json()
    assert [p["id"] for p in body["data"]] == [str(product.id)]
