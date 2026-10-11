from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Product, ProductCategory
from app.repositories import ProductCategoryRepository, ProductRepository
from tests.utils.utils import random_lower_string


def create_random_category(db: Session) -> ProductCategory:
    return ProductCategoryRepository(db).save(
        ProductCategory(name=random_lower_string(), code=random_lower_string()[:20])
    )


def create_random_product(
    db: Session, category: ProductCategory | None = None
) -> Product:
    category = category or create_random_category(db)
    return ProductRepository(db).save(
        Product(
            name=random_lower_string(),
            sku=random_lower_string(),
            category_uuid=category.id,
            price=Decimal("9.99"),
            stock=5,
        )
    )
