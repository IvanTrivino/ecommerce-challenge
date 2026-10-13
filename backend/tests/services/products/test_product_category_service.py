import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories import ProductCategoryRepository
from app.schemas import ProductCategoryCreate, ProductCategoryUpdate
from app.services import ProductCategoryService
from tests.utils.product import create_random_category, create_random_product
from tests.utils.utils import random_lower_string


def _service(db: Session) -> ProductCategoryService:
    return ProductCategoryService(ProductCategoryRepository(db))


def test_create_category_and_duplicate_code(db: Session) -> None:
    code = random_lower_string()[:20]
    service = _service(db)
    category = service.create_category(
        ProductCategoryCreate(name=random_lower_string(), code=code)
    )
    assert category.code == code
    with pytest.raises(ConflictError):
        service.create_category(
            ProductCategoryCreate(name=random_lower_string(), code=code)
        )


def test_list_categories(db: Session) -> None:
    category = create_random_category(db)
    result = _service(db).list_categories(skip=0, limit=1000)
    assert result.count >= 1
    assert category.id in {c.id for c in result.data}


def test_update_category(db: Session) -> None:
    category = create_random_category(db)
    service = _service(db)
    new_name = random_lower_string()
    updated = service.update_category(category.id, ProductCategoryUpdate(name=new_name))
    assert updated.name == new_name
    assert updated.code == category.code
    # keeping its own code is not a conflict
    service.update_category(category.id, ProductCategoryUpdate(code=category.code))


def test_update_category_duplicate_code(db: Session) -> None:
    first, second = create_random_category(db), create_random_category(db)
    with pytest.raises(ConflictError):
        _service(db).update_category(second.id, ProductCategoryUpdate(code=first.code))


def test_delete_category(db: Session) -> None:
    category = create_random_category(db)
    service = _service(db)
    service.delete_category(category.id)
    with pytest.raises(NotFoundError):
        service.get_by_id(category.id)


def test_delete_category_with_products(db: Session) -> None:
    product = create_random_product(db)
    with pytest.raises(ConflictError):
        _service(db).delete_category(product.category_uuid)


def test_category_names_are_unique_ignoring_case(db: Session) -> None:
    service = _service(db)
    name = f"Electronics {random_lower_string()}"
    category = service.create_category(
        ProductCategoryCreate(name=name, code=random_lower_string()[:20])
    )

    with pytest.raises(ConflictError, match="name already exists"):
        service.create_category(
            ProductCategoryCreate(name=name.lower(), code=random_lower_string()[:20])
        )

    # renaming a category to its own name in another case is not a conflict
    service.update_category(category.id, ProductCategoryUpdate(name=name.upper()))

    other = create_random_category(db)
    with pytest.raises(ConflictError, match="name already exists"):
        service.update_category(other.id, ProductCategoryUpdate(name=name))
