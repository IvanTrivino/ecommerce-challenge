import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


class ModelBase(DeclarativeBase):
    """Declarative base that only holds the metadata"""


class Base(ModelBase):
    """Abstract base for domain models, with audit columns"""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime_utc, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_datetime_utc,
        onupdate=get_datetime_utc,
        server_default=func.now(),
    )
