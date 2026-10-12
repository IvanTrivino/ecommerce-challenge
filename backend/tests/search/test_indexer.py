import uuid
from datetime import timedelta

import elasticsearch
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.core.search import get_es
from app.models import (
    OutboxEvent,
    OutboxStatus,
    OutboxTopic,
)
from app.models.base import get_datetime_utc
from app.repositories import (
    OutboxRepository,
    ProductCategoryRepository,
    ProductRepository,
)
from app.search import indexer
from app.search.indexer import INDEXER_LOCK_KEY, BatchResult, process_once
from app.search.products_index import alias, ensure_index
from tests.search.conftest import refresh
from tests.utils.product import create_random_category, create_random_product


@pytest.fixture(autouse=True)
def _index() -> None:
    ensure_index(get_es())


def run() -> BatchResult:
    with Session(engine) as session:
        result = process_once(session, get_es())
    refresh()
    return result


def doc(product_id: uuid.UUID) -> dict | None:
    es = get_es()
    if not es.exists(index=alias(), id=str(product_id)):
        return None
    return dict(es.get(index=alias(), id=str(product_id))["_source"])


def statuses() -> list[str]:
    with Session(engine) as session:
        return [
            e.status
            for e in session.scalars(select(OutboxEvent).order_by(OutboxEvent.id))
        ]


def test_create_indexes_document(db: Session) -> None:
    """AC-1"""
    category = create_random_category(db)
    product = create_random_product(db, category)
    result = run()
    source = doc(product.id)
    assert source is not None
    assert set(source) == {"name", "description", "sku", "category_name", "updated_at"}
    assert source["category_name"] == category.name
    assert (
        result.indexed == 2 - 1
    )  # one product; the category event has no live products
    assert set(statuses()) == {OutboxStatus.DONE}


def test_rename_updates_document(db: Session) -> None:
    """AC-4"""
    product = create_random_product(db)
    run()
    product.name = "renamed widget"
    ProductRepository(db).save(product)
    run()
    source = doc(product.id)
    assert source is not None
    assert source["name"] == "renamed widget"


def test_soft_delete_removes_document(db: Session) -> None:
    """AC-5"""
    product = create_random_product(db)
    run()
    assert doc(product.id) is not None
    ProductRepository(db).delete(product)
    run()
    assert doc(product.id) is None


def test_category_delete_removes_all_and_blocks_readd(db: Session) -> None:
    """AC-6"""
    category = create_random_category(db)
    products = [create_random_product(db, category) for _ in range(3)]
    run()
    assert all(doc(p.id) for p in products)

    repo = ProductRepository(db)
    for p in products:
        repo.delete(p)
    ProductCategoryRepository(db).delete(category)
    run()
    assert all(doc(p.id) is None for p in products)

    products[0].is_deleted = False
    repo.save(products[0])
    run()
    assert doc(products[0].id) is None


def test_category_delete_with_live_products(db: Session) -> None:
    """FR-4.2"""
    category = create_random_category(db)
    products = [create_random_product(db, category) for _ in range(2)]
    run()
    ProductCategoryRepository(db).delete(category)
    run()
    assert all(doc(p.id) is None for p in products)


def test_category_rename_updates_products(db: Session) -> None:
    """AC-7"""
    category = create_random_category(db)
    products = [create_random_product(db, category) for _ in range(2)]
    run()
    category.name = "brand new name"
    ProductCategoryRepository(db).save(category)
    run()
    for p in products:
        source = doc(p.id)
        assert source is not None
        assert source["category_name"] == "brand new name"


def test_duplicate_events_are_deduplicated(db: Session) -> None:
    """AC-8"""
    product = create_random_product(db)
    run()
    OutboxRepository(db).add_many(OutboxTopic.SEARCH_PRODUCT, [product.id] * 5)
    db.commit()
    result = run()
    assert result.claimed == 5
    assert result.indexed == 1
    assert set(statuses()) == {OutboxStatus.DONE}


def test_reprocessing_is_idempotent(db: Session) -> None:
    """AC-9"""
    product = create_random_product(db)
    run()
    es = get_es()
    before = es.get(index=alias(), id=str(product.id))["_version"]
    OutboxRepository(db).add_many(OutboxTopic.SEARCH_PRODUCT, [product.id])
    db.commit()
    run()
    assert es.get(index=alias(), id=str(product.id))["_version"] == before
    assert set(statuses()) == {OutboxStatus.DONE}


def test_missing_product_is_deleted_from_index(db: Session) -> None:
    OutboxRepository(db).add_many(OutboxTopic.SEARCH_PRODUCT, [uuid.uuid4()])
    db.commit()
    result = run()
    assert result.deleted == 1
    assert set(statuses()) == {OutboxStatus.DONE}


def test_es_unreachable_retries_then_fails(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-10"""
    product = create_random_product(db)
    # keep only the product event
    db.query(OutboxEvent).filter(
        OutboxEvent.topic != OutboxTopic.SEARCH_PRODUCT
    ).delete()
    db.commit()

    def boom(*_: object, **__: object) -> None:
        raise elasticsearch.ConnectionError("down")

    monkeypatch.setattr(indexer.helpers, "streaming_bulk", boom)
    result = run()
    assert result.retried == 1
    db.expire_all()
    event = db.scalars(
        select(OutboxEvent).where(OutboxEvent.aggregate_id == product.id)
    ).one()
    assert event.status == OutboxStatus.PENDING
    assert event.attempts == 1
    assert event.available_at > get_datetime_utc()

    event.attempts = 9
    event.available_at = get_datetime_utc() - timedelta(seconds=1)
    db.commit()
    result = run()
    assert result.failed == 1
    db.refresh(event)
    assert event.status == OutboxStatus.FAILED


def test_per_item_error_retries_only_that_event(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = create_random_product(db)
    # Make the strict mapping reject this document
    monkeypatch.setattr(
        indexer, "to_document", lambda p, c: {"unknown_field": 1, "name": p.name}
    )
    result = run()
    assert result.retried >= 1
    assert doc(product.id) is None


def test_reindex_pause(db: Session) -> None:
    product = create_random_product(db)
    with engine.connect() as conn:
        conn.execute(select(func.pg_advisory_lock(INDEXER_LOCK_KEY)))
        try:
            result = run()
            assert result == BatchResult()
            assert OutboxStatus.PENDING in statuses()
        finally:
            conn.execute(select(func.pg_advisory_unlock(INDEXER_LOCK_KEY)))
            conn.commit()
    run()
    assert doc(product.id) is not None
