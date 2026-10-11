import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories import ProductCategoryRepository, ProductRepository
from app.schemas import ProductCreate, ProductUpdate
from app.services import ProductService
from tests.utils.product import create_random_category, create_random_product
from tests.utils.utils import random_lower_string


def _service(db: Session) -> ProductService:
    return ProductService(ProductRepository(db), ProductCategoryRepository(db))


def _product_in(category_uuid: uuid.UUID, sku: str | None = None) -> ProductCreate:
    return ProductCreate(
        name=random_lower_string(),
        sku=sku or random_lower_string(),
        category_uuid=category_uuid,
        price=Decimal("10.50"),
    )


def test_create_product(db: Session) -> None:
    category = create_random_category(db)
    product = _service(db).create_product(_product_in(category.id))
    assert product.stock == 0
    assert product.category_uuid == category.id


def test_create_product_duplicate_sku(db: Session) -> None:
    existing = create_random_product(db)
    with pytest.raises(ConflictError):
        _service(db).create_product(_product_in(existing.category_uuid, existing.sku))


def test_create_product_unknown_category(db: Session) -> None:
    with pytest.raises(NotFoundError):
        _service(db).create_product(_product_in(uuid.uuid4()))


def test_get_by_id_not_found(db: Session) -> None:
    with pytest.raises(NotFoundError):
        _service(db).get_by_id(uuid.uuid4())


def test_list_products_filters_by_category(db: Session) -> None:
    category = create_random_category(db)
    product = create_random_product(db, category)
    result = _service(db).list_products(category_id=category.id, skip=0, limit=10)
    assert result.count == 1
    assert result.data[0].id == product.id


def test_update_product(db: Session) -> None:
    product = create_random_product(db)
    new_category = create_random_category(db)
    updated = _service(db).update_product(
        product.id,
        ProductUpdate(name="new", price=Decimal("1.00"), category_uuid=new_category.id),
    )
    assert updated.name == "new"
    assert updated.price == Decimal("1.00")
    assert updated.category_uuid == new_category.id


def test_update_ignores_null_for_required_fields_but_clears_nullable(
    db: Session,
) -> None:
    product = create_random_product(db)
    product.description = "to be cleared"
    updated = _service(db).update_product(
        product.id, ProductUpdate(name=None, description=None)
    )
    assert updated.name == product.name
    assert updated.description is None


def test_update_product_keeping_own_sku_is_allowed(db: Session) -> None:
    product = create_random_product(db)
    updated = _service(db).update_product(product.id, ProductUpdate(sku=product.sku))
    assert updated.sku == product.sku


def test_update_product_duplicate_sku(db: Session) -> None:
    first, second = create_random_product(db), create_random_product(db)
    with pytest.raises(ConflictError):
        _service(db).update_product(second.id, ProductUpdate(sku=first.sku))


def test_update_product_unknown_category(db: Session) -> None:
    product = create_random_product(db)
    with pytest.raises(NotFoundError):
        _service(db).update_product(
            product.id, ProductUpdate(category_uuid=uuid.uuid4())
        )


def test_delete_product(db: Session) -> None:
    product = create_random_product(db)
    service = _service(db)
    service.delete_product(product.id)
    with pytest.raises(NotFoundError):
        service.get_by_id(product.id)


def test_write_invalidates_cached_reads(db: Session) -> None:
    product = create_random_product(db)
    service = _service(db)
    assert service.get_by_id(product.id).name == product.name  # fills the cache
    service.update_product(product.id, ProductUpdate(name="renamed"))
    assert service.get_by_id(product.id).name == "renamed"
