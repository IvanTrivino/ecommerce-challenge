from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Product
from app.repositories import ProductCategoryRepository, ProductRepository
from tests.utils.product import create_random_category, create_random_product


def test_get_by_sku(db: Session) -> None:
    product = create_random_product(db)
    repo = ProductRepository(db)
    assert repo.get_by_sku(product.sku) == product
    assert repo.get_by_sku("missing-sku") is None


def test_sku_can_be_reused_after_delete(db: Session) -> None:
    product = create_random_product(db)
    repo = ProductRepository(db)
    repo.delete(product)
    assert repo.get_by_sku(product.sku) is None
    reused = repo.save(
        Product(
            name="reused",
            sku=product.sku,
            category_uuid=product.category_uuid,
            price=Decimal("1.00"),
        )
    )
    assert reused.id != product.id


def test_list_and_count_filtered_by_category(db: Session) -> None:
    category = create_random_category(db)
    products = [create_random_product(db, category) for _ in range(2)]
    create_random_product(db)  # other category
    repo = ProductRepository(db)
    assert repo.count_filtered(category_id=category.id) == 2
    listed = repo.list_filtered(category_id=category.id)
    assert {p.id for p in listed} == {p.id for p in products}
    assert len(repo.list_filtered(category_id=category.id, limit=1)) == 1
    assert repo.count_filtered() >= 3


def test_filtered_queries_exclude_deleted(db: Session) -> None:
    category = create_random_category(db)
    product = create_random_product(db, category)
    repo = ProductRepository(db)
    repo.delete(product)
    assert repo.count_filtered(category_id=category.id) == 0
    assert repo.list_filtered(category_id=category.id) == []


def test_category_get_by_code(db: Session) -> None:
    category = create_random_category(db)
    repo = ProductCategoryRepository(db)
    assert repo.get_by_code(category.code) == category
    assert repo.get_by_code("missing-code") is None


def test_category_has_products_ignores_deleted_products(db: Session) -> None:
    category = create_random_category(db)
    repo = ProductCategoryRepository(db)
    assert repo.has_products(category.id) is False
    product = create_random_product(db, category)
    assert repo.has_products(category.id) is True
    ProductRepository(db).delete(product)
    assert repo.has_products(category.id) is False
