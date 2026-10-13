import uuid
from collections.abc import Collection, Sequence
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import Connection, func, select, text, update
from sqlalchemy.orm import Session

from app.models import (
    ACTIVE_IMPORT_STATUSES,
    ProductImport,
    ProductImportError,
)
from app.repositories.base import BaseRepository


class RowErrorLike(Protocol):
    @property
    def line(self) -> int: ...
    @property
    def sku(self) -> str | None: ...
    @property
    def message(self) -> str: ...


def advisory_key(import_id: uuid.UUID) -> int:
    return int.from_bytes(import_id.bytes[:8], "big", signed=True)


_ACTIVE = [status.value for status in ACTIVE_IMPORT_STATUSES]


class ProductImportRepository(BaseRepository[ProductImport]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ProductImport)

    def get_by_key(self, key: str) -> ProductImport | None:
        statement = self._live().where(ProductImport.file_key == key)
        return self.session.scalars(statement).first()

    def get_active(self) -> ProductImport | None:
        statement = self._live().where(ProductImport.status.in_(_ACTIVE))
        return self.session.scalars(statement).first()

    def add_errors(self, import_id: uuid.UUID, errors: Sequence[RowErrorLike]) -> None:
        self.session.add_all(
            ProductImportError(
                import_id=import_id, line=e.line, sku=e.sku, message=e.message
            )
            for e in errors
        )

    def list_errors(
        self, import_id: uuid.UUID, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ProductImportError]:
        statement = (
            select(ProductImportError)
            .where(ProductImportError.import_id == import_id)
            .order_by(ProductImportError.line, ProductImportError.id)
            .offset(skip)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def count_errors(self, import_id: uuid.UUID) -> int:
        statement = select(func.count()).where(
            ProductImportError.import_id == import_id
        )
        return self.session.scalar(statement) or 0

    def stale(self, now: datetime, minutes: int) -> Sequence[ProductImport]:
        cutoff = now - timedelta(minutes=minutes)
        statement = self._live().where(
            ProductImport.status.in_(_ACTIVE),
            func.coalesce(ProductImport.heartbeat_at, ProductImport.created_at)
            < cutoff,
        )
        return self.session.scalars(statement).all()

    def active_file_keys(self) -> set[str]:
        statement = select(ProductImport.file_key).where(
            ProductImport.status.in_(_ACTIVE)
        )
        return set(self.session.scalars(statement))

    def mark_files_deleted(self, keys: Collection[str], now: datetime) -> None:
        self.session.execute(
            update(ProductImport)
            .where(
                ProductImport.file_key.in_(keys),
                ProductImport.file_deleted_at.is_(None),
            )
            .values(file_deleted_at=now)
        )

    def try_lock(self, conn: Connection, import_id: uuid.UUID) -> bool:
        return bool(
            conn.scalar(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": advisory_key(import_id)},
            )
        )

    def unlock(self, conn: Connection, import_id: uuid.UUID) -> None:
        conn.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": advisory_key(import_id)}
        )

    def try_xact_lock(self, import_id: uuid.UUID) -> bool:
        return bool(
            self.session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": advisory_key(import_id)},
            )
        )
