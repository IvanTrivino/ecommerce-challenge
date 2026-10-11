from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductCategory(Base):
    __tablename__ = "product_category"
    __table_args__ = (
        Index(
            "ix_product_category_code",
            "code",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(50))
