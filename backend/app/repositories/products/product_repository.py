import uuid
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, func, literal_column, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable

from app.models import OutboxTopic, Product, ProductCategory
from app.outbox.fields import PRODUCT_SEARCH_FIELDS
from app.repositories.base import BaseRepository
from app.repositories.outbox import OutboxRepository


@dataclass(frozen=True)
class ProductUpsert:
    sku: str
    name: str
    category_uuid: uuid.UUID
    price: Decimal
    stock: int
    description: str | None
    weight: Decimal | None


@dataclass(frozen=True)
class UpsertResult:
    created: int
    updated: int
    unchanged: int


_ALWAYS = ("name", "category_uuid", "price", "stock")
_OPTIONAL = ("description", "weight")
_SEARCH_UPSERTABLE = tuple(
    field for field in PRODUCT_SEARCH_FIELDS if field in _ALWAYS + _OPTIONAL
)


class ProductRepository(BaseRepository[Product]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Product)

    def get_many(self, ids: Collection[uuid.UUID]) -> Sequence[Product]:
        return self.session.scalars(self._live().where(Product.id.in_(ids))).all()

    def lock_many(self, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, Product]:
        """Lock products in id order, so checkouts sharing products can't deadlock.

        Includes soft-deleted products: callers decide what a deleted product means.
        """
        if not ids:
            return {}
        statement = (
            select(Product)
            .where(Product.id.in_(ids))
            .order_by(Product.id)
            .with_for_update(of=Product)
            .execution_options(populate_existing=True)
        )
        return {p.id: p for p in self.session.scalars(statement)}

    def referenced_image_keys(self, keys: Collection[str]) -> set[str]:
        statement = select(Product.image_key).where(Product.image_key.in_(keys))
        return {key for key in self.session.scalars(statement) if key}

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

    def upsert_many(
        self, rows: Sequence[ProductUpsert], *, columns: Collection[str]
    ) -> UpsertResult:
        if not rows:
            return UpsertResult(0, 0, 0)
        if len({row.sku for row in rows}) != len(rows):
            raise ValueError("upsert_many needs unique SKUs")

        written = [f for f in _ALWAYS + _OPTIONAL if f in _ALWAYS or f in columns]
        insert = pg_insert(Product).values(
            [
                {
                    "id": uuid.uuid4(),
                    "sku": row.sku,
                    **{field: getattr(row, field) for field in _ALWAYS + _OPTIONAL},
                }
                for row in rows
            ]
        )
        excluded = insert.excluded
        old_values = tuple_(*[getattr(Product, f) for f in written])
        new_values = tuple_(*[getattr(excluded, f) for f in written])
        search_old = ", ".join(f"old.{f}" for f in _SEARCH_UPSERTABLE)
        search_new = ", ".join(f"new.{f}" for f in _SEARCH_UPSERTABLE)
        statement: Executable = insert.on_conflict_do_update(
            index_elements=["sku"],
            index_where=text("NOT is_deleted"),
            set_={f: getattr(excluded, f) for f in written}
            | {"updated_at": func.now()},
            where=old_values.is_distinct_from(new_values),
        ).returning(
            literal_column("new.id").label("id"),
            literal_column("old.id IS NULL").label("inserted"),
            literal_column(f"({search_old}) IS DISTINCT FROM ({search_new})").label(
                "search_changed"
            ),
        )
        returned = self.session.execute(statement).all()

        OutboxRepository(self.session).add_many(
            OutboxTopic.SEARCH_PRODUCT,
            [r.id for r in returned if r.inserted or r.search_changed],
        )
        self.session.flush()
        created = sum(1 for r in returned if r.inserted)
        return UpsertResult(
            created=created,
            updated=len(returned) - created,
            unchanged=len(rows) - len(returned),
        )
