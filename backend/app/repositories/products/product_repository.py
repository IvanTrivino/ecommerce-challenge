import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):

    def __init__(self, session: Session) -> None:
        super().__init__(session, Product)

    def get_by_sku(self, sku: str) -> Product | None:
        return self.session.scalars(self._live().where(Product.sku == sku)).first()

    def _filtered(self, category_id: uuid.UUID | None) -> Select[tuple[Product]]:
        statement = self._live()
        if category_id is not None:
            statement = statement.where(Product.category_uuid == category_id)
        return statement

    def list_filtered(
        self, *, category_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        statement = (
            self._filtered(category_id)
            .order_by(Product.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def count_filtered(self, *, category_id: uuid.UUID | None = None) -> int:
        statement = select(func.count()).select_from(
            self._filtered(category_id).subquery()
        )
        return self.session.scalar(statement) or 0
