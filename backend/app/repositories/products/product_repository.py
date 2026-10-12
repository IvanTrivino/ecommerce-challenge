import uuid
from collections.abc import Collection, Iterator, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Product, ProductCategory
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

    def get_many_with_category(
        self, ids: Collection[uuid.UUID]
    ) -> list[tuple[Product, ProductCategory]]:
        statement = (
            select(Product, ProductCategory)
            .join(ProductCategory, Product.category_uuid == ProductCategory.id)
            .where(Product.id.in_(ids))
        )
        return [(p, c) for p, c in self.session.execute(statement).all()]

    def list_ids_by_category(
        self, category_ids: Collection[uuid.UUID]
    ) -> list[uuid.UUID]:
        statement = select(Product.id).where(Product.category_uuid.in_(category_ids))
        return list(self.session.scalars(statement).all())

    def _indexable(self) -> Select[tuple[Product, ProductCategory]]:
        return (
            select(Product, ProductCategory)
            .join(ProductCategory, Product.category_uuid == ProductCategory.id)
            .where(~Product.is_deleted, ~ProductCategory.is_deleted)
        )

    def iter_indexable(
        self, batch_size: int
    ) -> Iterator[tuple[Product, ProductCategory]]:
        statement = self._indexable().execution_options(yield_per=batch_size)
        yield from self.session.execute(statement).tuples()

    def count_indexable(self) -> int:
        statement = select(func.count()).select_from(self._indexable().subquery())
        return self.session.scalar(statement) or 0
