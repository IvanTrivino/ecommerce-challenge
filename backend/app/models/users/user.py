from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        Index(
            "ix_user_email",
            "email",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
    )

    email: Mapped[str] = mapped_column(String(255))
    password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    full_name: Mapped[str | None] = mapped_column(String(255), default=None)
