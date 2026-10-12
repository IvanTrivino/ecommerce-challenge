import pytest
from elasticsearch import BadRequestError
from sqlalchemy.orm import Session

from app.core.search import get_es
from app.models import Product, ProductCategory
from app.search import products_index
from app.search.products_index import (
    alias,
    ensure_index,
    is_indexable,
    to_document,
    version,
)
from tests.search.conftest import refresh
from tests.utils.product import create_random_category, create_random_product


def _pair(db: Session, **changes: str) -> tuple[Product, ProductCategory]:
    category = create_random_category(db)
    product = create_random_product(db, category)
    for key, value in changes.items():
        setattr(product, key, value)
    return product, category


def test_to_document_has_exact_fields(db: Session) -> None:
    product, category = _pair(db)
    assert product.description is None
    document = to_document(product, category)
    assert set(document) == {
        "name",
        "description",
        "sku",
        "category_name",
        "updated_at",
    }
    assert document["description"] is None
    assert document["category_name"] == category.name


def test_version_is_epoch_microseconds(db: Session) -> None:
    product, category = _pair(db)
    latest = max(product.updated_at, category.updated_at)
    assert version(product, category) == int(latest.timestamp() * 1_000_000)


def test_is_indexable(db: Session) -> None:
    product, category = _pair(db)
    assert is_indexable(product, category)
    category.is_deleted = True
    assert not is_indexable(product, category)


def test_ensure_index_is_idempotent() -> None:
    es = get_es()
    first = ensure_index(es)
    assert first.startswith(f"{alias()}_")
    assert ensure_index(es) == first


def test_strict_mapping_rejects_extra_field() -> None:
    es = get_es()
    ensure_index(es)
    with pytest.raises(BadRequestError):
        es.index(index=alias(), id="1", document={"name": "x", "price": 1})


def test_english_analysis() -> None:
    es = get_es()
    ensure_index(es)
    es.index(index=alias(), id="1", document={"name": "Run Shoe"})
    refresh()
    result = es.search(index=alias(), query={"match": {"name": "running shoes"}})
    assert result["hits"]["total"]["value"] == 1


def test_sku_exact_case_insensitive() -> None:
    es = get_es()
    ensure_index(es)
    es.index(index=alias(), id="1", document={"sku": "ABC-123"})
    refresh()

    def hits(value: str) -> int:
        result = es.search(index=alias(), query={"term": {"sku": value}})
        return int(result["hits"]["total"]["value"])

    assert hits("abc-123") == 1
    assert hits("abc") == 0


def test_new_index_name_uses_alias() -> None:
    assert products_index.new_index_name().startswith(f"{alias()}_")
