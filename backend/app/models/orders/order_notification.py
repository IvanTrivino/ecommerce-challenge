import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ModelBase, get_datetime_utc


class OrderNotificationKind(StrEnum):
    PLACED = "placed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class OrderNotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class OrderNotification(ModelBase):
    __tablename__ = "order_notification"
    __table_args__ = (
        UniqueConstraint("order_uuid", "kind", name="uq_order_notification_order_kind"),
        CheckConstraint(
            "kind IN ('placed', 'cancelled', 'completed')",
            name="ck_order_notification_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_order_notification_status",
        ),
        Index(
            "ix_order_notification_pending",
            "available_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(10),
        default=OrderNotificationStatus.PENDING.value,
        server_default=OrderNotificationStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime_utc, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
