import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.products import Product

if TYPE_CHECKING:
    from app.models.orders.order import Order

MAX_QUANTITY_PER_ITEM = 99


class CartItem(Base):
    __tablename__ = "cart_item"
    __table_args__ = (
        UniqueConstraint(
            "order_uuid", "product_uuid", name="uq_cart_item_order_product"
        ),
        CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_QUANTITY_PER_ITEM}",
            name="ck_cart_item_quantity",
        ),
    )

    order_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order.id", ondelete="CASCADE"), index=True
    )
    order: Mapped[Order] = relationship(back_populates="items")
    product_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product.id"), index=True
    )
    # Not filtered by is_deleted on purpose: a deleted product still shows in old orders
    product: Mapped[Product] = relationship(lazy="joined", innerjoin=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    unit_weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), default=None)
    product_name: Mapped[str | None] = mapped_column(String(255), default=None)
    product_sku: Mapped[str | None] = mapped_column(String(100), default=None)

    # Fixed values once placed, live product values while the order is a Draft
    @property
    def name(self) -> str:
        return self.product_name or self.product.name

    @property
    def sku(self) -> str:
        return self.product_sku or self.product.sku

    @property
    def line_total(self) -> Decimal | None:
        return None if self.unit_price is None else self.unit_price * self.quantity
