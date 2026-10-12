import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OutboxEvent, OutboxTopic, Product, ProductCategory
from app.repositories import ProductCategoryRepository, ProductRepository
from tests.utils.product import create_random_category, create_random_product
from tests.utils.utils import random_lower_string


def _events(db: Session) -> list[OutboxEvent]:
    db.expire_all()
    return list(db.scalars(select(OutboxEvent).order_by(OutboxEvent.id)).all())


def test_create_product_emits_one_event(db: Session) -> None:
    """AC-1 (outbox part)"""
    category = create_random_category(db)
    db.execute(OutboxEvent.__table__.delete())
    db.commit()
    product = create_random_product(db, category)
    events = _events(db)
    assert [(e.topic, e.aggregate_id) for e in events] == [
        (OutboxTopic.SEARCH_PRODUCT.value, product.id)
    ]


def test_rollback_leaves_no_product_and_no_event(db: Session) -> None:
    """AC-2"""
    category = create_random_category(db)
    product = Product(
        name="x",
        sku=random_lower_string(),
        category_uuid=category.id,
        price=Decimal("1"),
        stock=1,
    )
    db.add(product)
    db.flush()
    product_id = product.id
    db.rollback()
    assert db.get(Product, product_id) is None
    assert all(e.aggregate_id != product_id for e in _events(db))


@pytest.mark.parametrize(
    "field, value",
    [
        ("stock", 99),
        ("price", Decimal("1.50")),
        ("image_key", "products/00000000-0000-0000-0000-000000000000.png"),
    ],
)
def test_non_search_update_emits_no_event(
    db: Session, field: str, value: object
) -> None:
    """AC-3"""
    product = create_random_product(db)
    before = len(_events(db))
    setattr(product, field, value)
    ProductRepository(db).save(product)
    assert len(_events(db)) == before


@pytest.mark.parametrize(
    "field", ["name", "description", "sku", "category_uuid", "is_deleted"]
)
def test_search_field_update_emits_event(db: Session, field: str) -> None:
    """AC-4"""
    product = create_random_product(db)
    before = len(_events(db))
    repo = ProductRepository(db)
    if field == "category_uuid":
        new_category_id = create_random_category(db).id
        before = len(_events(db))
        product.category_uuid = new_category_id
    elif field == "is_deleted":
        repo.delete(product)
        events = _events(db)
        assert len(events) == before + 1
        assert events[-1].aggregate_id == product.id
        return
    elif field == "description":
        product.description = "new description"
    else:
        setattr(product, field, random_lower_string())
    repo.save(product)
    events = _events(db)
    assert len(events) == before + 1
    assert events[-1].topic == OutboxTopic.SEARCH_PRODUCT.value
    assert events[-1].aggregate_id == product.id


def test_category_events(db: Session) -> None:
    repo = ProductCategoryRepository(db)
    category = create_random_category(db)
    topic = OutboxTopic.SEARCH_PRODUCT_CATEGORY.value
    count = lambda: len([e for e in _events(db) if e.topic == topic])  # noqa: E731
    created = count()

    category.name = random_lower_string()
    repo.save(category)
    assert count() == created + 1

    category.code = random_lower_string()[:20]
    repo.save(category)
    assert count() == created + 1

    repo.delete(category)
    assert count() == created + 2


def test_new_object_gets_id_before_flush(db: Session) -> None:
    category = ProductCategory(name="n", code=random_lower_string()[:20])
    db.add(category)
    db.flush()
    assert isinstance(category.id, uuid.UUID)
    assert any(e.aggregate_id == category.id for e in _events(db))
    db.rollback()
