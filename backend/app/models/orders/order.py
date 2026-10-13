import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.users import User

if TYPE_CHECKING:
    from app.models.orders.cart_item import CartItem


class OrderState(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


PLACED_STATES = (OrderState.IN_PROGRESS, OrderState.COMPLETED, OrderState.CANCELLED)


class Order(Base):
    __tablename__ = "order"
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft', 'in_progress', 'completed', 'cancelled')",
            name="ck_order_state",
        ),
        CheckConstraint(
            "state = 'draft' OR (placed_at IS NOT NULL AND total_price IS NOT NULL "
            "AND total_weight IS NOT NULL)",
            name="ck_order_placed_totals",
        ),
        Index(
            "ux_order_user_draft",
            "user_uuid",
            unique=True,
            postgresql_where=text("state = 'draft' AND NOT is_deleted"),
        ),
        Index("ix_order_state_placed_at", "state", text("placed_at DESC")),
        Index(
            "ix_order_user_placed_at",
            "user_uuid",
            text("placed_at DESC"),
            postgresql_where=text("state <> 'draft'"),
        ),
    )

    user_uuid: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    user: Mapped[User] = relationship(lazy="joined", innerjoin=True)
    state: Mapped[str] = mapped_column(
        String(20), default=OrderState.DRAFT.value, server_default="draft"
    )
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    total_weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), default=None)
    currency: Mapped[str] = mapped_column(String(3))
    payment_reference: Mapped[str | None] = mapped_column(String(100), default=None)
    placed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    items: Mapped[list[CartItem]] = relationship(
        back_populates="order",
        order_by="CartItem.created_at",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def number(self) -> str:
        return self.id.hex[:8].upper()

    @property
    def user_email(self) -> str:
        return self.user.email

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)
