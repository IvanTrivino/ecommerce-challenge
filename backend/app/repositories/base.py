import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base


def constraint_name(exc: IntegrityError) -> str | None:
    diag: Any = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


class BaseRepository[ModelT: Base]:
    """
    Models are soft-deleted, so every read here ignores rows with `is_deleted`.
    Repositories for new models should extend this class and build their own
    queries on top of `_live()`, so the soft-delete filter is never forgotten.
    """

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def _live(self) -> Select[tuple[ModelT]]:
        """Base query: all rows of the model that are not soft-deleted."""
        return select(self.model).where(~self.model.is_deleted)

    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        statement = self._live().where(self.model.id == entity_id)
        return self.session.scalars(statement).first()

    def list(self, *, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        statement = (
            self._live()
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def count(self) -> int:
        statement = select(func.count()).select_from(self._live().subquery())
        return self.session.scalar(statement) or 0

    def save(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        entity.is_deleted = True
        self.session.add(entity)
        self.session.commit()
