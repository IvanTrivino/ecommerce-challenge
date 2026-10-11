import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Product, ProductCategory
from app.repositories.base import BaseRepository


class ProductCategoryRepository(BaseRepository[ProductCategory]):

    def __init__(self, session: Session) -> None:
        super().__init__(session, ProductCategory)

    def get_by_code(self, code: str) -> ProductCategory | None:
        statement = self._live().where(ProductCategory.code == code)
        return self.session.scalars(statement).first()

    def has_products(self, category_id: uuid.UUID) -> bool:
        statement = select(
            exists().where(Product.category_uuid == category_id, ~Product.is_deleted)
        )
        return bool(self.session.scalar(statement))
