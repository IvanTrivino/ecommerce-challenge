import uuid
from collections.abc import Generator
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models import OutboxEvent, OutboxTopic, Product, ProductCategory
from app.repositories import ProductRepository, ProductUpsert
from tests.utils.product import create_random_category
from tests.utils.utils import random_lower_string


@pytest.fixture(autouse=True)
def clean_outbox() -> None:
    with Session(engine) as session:
        session.execute(delete(OutboxEvent))
        session.commit()


@pytest.fixture
def session() -> Generator[Session]:
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def category(db: Session) -> ProductCategory:
    return create_random_category(db)


def row(
    category: ProductCategory, sku: str | None = None, **kwargs: object
) -> ProductUpsert:
    values: dict[str, object] = {
        "sku": sku or random_lower_string(),
        "name": "Mug",
        "category_uuid": category.id,
        "price": Decimal("9.99"),
        "stock": 5,
        "description": "Ceramic",
        "weight": Decimal("0.350"),
    } | kwargs
    return ProductUpsert(**values)  # type: ignore[arg-type]


ALL = {"description", "weight"}


def product_events(session: Session) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(OutboxEvent.aggregate_id).where(
                OutboxEvent.topic == OutboxTopic.SEARCH_PRODUCT.value
            )
        )
    )


def load(session: Session, sku: str) -> Product:
    session.expire_all()
    return session.scalars(
        select(Product).where(Product.sku == sku, ~Product.is_deleted)
    ).one()


def test_new_skus_are_created_with_events(
    session: Session, category: ProductCategory
) -> None:
    rows = [row(category), row(category)]

    result = ProductRepository(session).upsert_many(rows, columns=ALL)
    session.commit()

    assert (result.created, result.updated, result.unchanged) == (2, 0, 0)
    products = [load(session, r.sku) for r in rows]
    assert sorted(product_events(session)) == sorted(p.id for p in products)
    assert all(not p.is_deleted and p.image_key is None for p in products)
    assert products[0].created_at is not None


def test_identical_values_write_nothing(
    session: Session, category: ProductCategory
) -> None:
    rows = [row(category), row(category)]
    repo = ProductRepository(session)
    repo.upsert_many(rows, columns=ALL)
    session.commit()
    before = {r.sku: load(session, r.sku).updated_at for r in rows}
    session.execute(delete(OutboxEvent))
    session.commit()

    result = repo.upsert_many(rows, columns=ALL)
    session.commit()

    assert (result.created, result.updated, result.unchanged) == (0, 0, 2)
    assert product_events(session) == []
    assert {r.sku: load(session, r.sku).updated_at for r in rows} == before


def test_non_search_changes_emit_no_event(
    session: Session, category: ProductCategory
) -> None:
    first = row(category)
    repo = ProductRepository(session)
    repo.upsert_many([first], columns=ALL)
    session.commit()
    created_at = load(session, first.sku).updated_at
    session.execute(delete(OutboxEvent))
    session.commit()

    changed = row(category, sku=first.sku, price=Decimal("19.99"), stock=1)
    result = repo.upsert_many([changed], columns=ALL)
    session.commit()

    assert (result.created, result.updated, result.unchanged) == (0, 1, 0)
    assert product_events(session) == []
    product = load(session, first.sku)
    assert (product.price, product.stock) == (Decimal("19.99"), 1)
    assert product.updated_at > created_at


def test_name_change_emits_one_event(
    session: Session, category: ProductCategory
) -> None:
    first = row(category)
    repo = ProductRepository(session)
    repo.upsert_many([first], columns=ALL)
    session.commit()
    session.execute(delete(OutboxEvent))
    session.commit()

    repo.upsert_many([row(category, sku=first.sku, name="Cup")], columns=ALL)
    session.commit()

    assert product_events(session) == [load(session, first.sku).id]


def test_category_change_emits_an_event(
    session: Session, category: ProductCategory, db: Session
) -> None:
    other = create_random_category(db)
    first = row(category)
    repo = ProductRepository(session)
    repo.upsert_many([first], columns=ALL)
    session.commit()
    session.execute(delete(OutboxEvent))
    session.commit()

    repo.upsert_many([row(other, sku=first.sku)], columns=ALL)
    session.commit()

    assert len(product_events(session)) == 1


def test_missing_optional_columns_keep_existing_values(
    session: Session, category: ProductCategory
) -> None:
    first = row(category)
    repo = ProductRepository(session)
    repo.upsert_many([first], columns=ALL)
    session.commit()

    update = row(
        category, sku=first.sku, price=Decimal("1.00"), description=None, weight=None
    )
    repo.upsert_many([update], columns=set())
    session.commit()

    product = load(session, first.sku)
    assert product.price == Decimal("1.00")
    assert product.description == "Ceramic"
    assert product.weight == Decimal("0.350")


def test_missing_optional_columns_are_null_on_insert(
    session: Session, category: ProductCategory
) -> None:
    new = row(category, description=None, weight=None)

    ProductRepository(session).upsert_many([new], columns=set())
    session.commit()

    product = load(session, new.sku)
    assert product.description is None
    assert product.weight is None


def test_present_empty_optional_column_clears_the_value(
    session: Session, category: ProductCategory
) -> None:
    first = row(category)
    repo = ProductRepository(session)
    repo.upsert_many([first], columns=ALL)
    session.commit()

    repo.upsert_many(
        [row(category, sku=first.sku, description=None)], columns={"description"}
    )
    session.commit()

    product = load(session, first.sku)
    assert product.description is None
    assert product.weight == Decimal("0.350")


def test_soft_deleted_sku_creates_a_new_product(
    session: Session, category: ProductCategory
) -> None:
    sku = random_lower_string()
    old = Product(
        name="Old", sku=sku, category_uuid=category.id, price=Decimal(1), stock=1
    )
    old.is_deleted = True
    session.add(old)
    session.commit()

    result = ProductRepository(session).upsert_many(
        [row(category, sku=sku)], columns=ALL
    )
    session.commit()

    assert result.created == 1
    session.refresh(old)
    assert old.name == "Old"
    assert old.is_deleted
    assert load(session, sku).id != old.id


def test_image_key_and_created_at_are_never_changed(
    session: Session, category: ProductCategory
) -> None:
    sku = random_lower_string()
    product = Product(
        name="Old",
        sku=sku,
        category_uuid=category.id,
        price=Decimal(1),
        stock=1,
        image_key="products/x.png",
    )
    session.add(product)
    session.commit()
    created_at = product.created_at

    ProductRepository(session).upsert_many([row(category, sku=sku)], columns=ALL)
    session.commit()

    loaded = load(session, sku)
    assert loaded.id == product.id
    assert loaded.image_key == "products/x.png"
    assert loaded.created_at == created_at


def test_concurrently_created_sku_is_updated_not_rejected(
    session: Session, category: ProductCategory, db: Session
) -> None:
    sku = random_lower_string()
    ProductRepository(db).save(
        Product(
            name="By admin",
            sku=sku,
            category_uuid=category.id,
            price=Decimal(1),
            stock=1,
        )
    )

    result = ProductRepository(session).upsert_many(
        [row(category, sku=sku)], columns=ALL
    )
    session.commit()

    assert (result.created, result.updated) == (0, 1)
    assert load(session, sku).name == "Mug"


def test_rollback_leaves_no_products_and_no_events(
    session: Session, category: ProductCategory
) -> None:
    rows = [row(category), row(category)]

    ProductRepository(session).upsert_many(rows, columns=ALL)
    session.rollback()

    assert (
        session.scalars(
            select(Product).where(Product.sku.in_([r.sku for r in rows]))
        ).all()
        == []
    )
    assert product_events(session) == []


def test_empty_input_runs_no_sql(session: Session) -> None:
    result = ProductRepository(session).upsert_many([], columns=ALL)

    assert (result.created, result.updated, result.unchanged) == (0, 0, 0)


def test_duplicate_skus_in_one_call_are_rejected(
    session: Session, category: ProductCategory
) -> None:
    sku = random_lower_string()

    with pytest.raises(ValueError):
        ProductRepository(session).upsert_many(
            [row(category, sku=sku), row(category, sku=sku)], columns=ALL
        )
