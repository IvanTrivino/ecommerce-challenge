import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ModelBase, get_datetime_utc


class OutboxTopic(StrEnum):
    SEARCH_PRODUCT = "search.product"
    SEARCH_PRODUCT_CATEGORY = "search.product_category"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class OutboxEvent(ModelBase):
    __tablename__ = "outbox_event"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'done', 'failed')", name="ck_outbox_event_status"
        ),
        Index(
            "ix_outbox_event_pending",
            "available_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    topic: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(
        String(10),
        default=OutboxStatus.PENDING,
        server_default=OutboxStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime_utc, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime_utc, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
