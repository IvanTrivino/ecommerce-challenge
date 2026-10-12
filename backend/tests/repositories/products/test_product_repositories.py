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


def test_get_many_with_category_includes_deleted(db: Session) -> None:
    live = create_random_product(db)
    deleted = create_random_product(db)
    ProductRepository(db).delete(deleted)
    rows = ProductRepository(db).get_many_with_category([live.id, deleted.id])
    assert {p.id for p, _ in rows} == {live.id, deleted.id}
    assert all(c.id == p.category_uuid for p, c in rows)


def test_list_ids_by_category_includes_deleted(db: Session) -> None:
    category = create_random_category(db)
    live = create_random_product(db, category)
    deleted = create_random_product(db, category)
    ProductRepository(db).delete(deleted)
    other = create_random_product(db)
    ids = ProductRepository(db).list_ids_by_category([category.id])
    assert set(ids) == {live.id, deleted.id}
    assert other.id not in ids


def test_iter_indexable_skips_deleted_products_and_categories(db: Session) -> None:
    repo = ProductRepository(db)
    category = create_random_category(db)
    live = create_random_product(db, category)
    deleted = create_random_product(db, category)
    repo.delete(deleted)
    dead_category = create_random_category(db)
    in_dead_category = create_random_product(db, dead_category)
    ProductCategoryRepository(db).delete(dead_category)

    ids = {p.id for p, _ in repo.iter_indexable(10)}
    assert live.id in ids
    assert deleted.id not in ids
    assert in_dead_category.id not in ids
    assert repo.count_indexable() == len(ids)
