import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Product(Base):
    __tablename__ = "product"
    __table_args__ = (
        Index(
            "ix_product_sku",
            "sku",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255))
    sku: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_category.id"), index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), default=None)
    image_key: Mapped[str | None] = mapped_column(String(512), default=None)
