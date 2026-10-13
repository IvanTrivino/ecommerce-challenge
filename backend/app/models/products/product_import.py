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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ModelBase
from app.models.users import User


class ProductImportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


ACTIVE_IMPORT_STATUSES = (ProductImportStatus.PENDING, ProductImportStatus.RUNNING)


class ProductImport(Base):
    __tablename__ = "product_import"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_product_import_status",
        ),
        Index(
            "ix_product_import_active",
            text("(true)"),
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        Index("ix_product_import_created_at", text("created_at DESC")),
    )

    file_key: Mapped[str] = mapped_column(String(512), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), default=None
    )
    created_by: Mapped[User | None] = relationship(lazy="joined")
    status: Mapped[str] = mapped_column(
        String(16), default=ProductImportStatus.PENDING.value
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), default=None)
    total_bytes: Mapped[int] = mapped_column(BigInteger)
    bytes_processed: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0"
    )
    etag: Mapped[str] = mapped_column(String(255))
    columns: Mapped[dict[str, int] | None] = mapped_column(JSONB, default=None)
    next_line: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    blank_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    categories_created: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    file_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    @property
    def created_by_email(self) -> str | None:
        return self.created_by.email if self.created_by else None


class ProductImportError(ModelBase):
    __tablename__ = "product_import_error"
    __table_args__ = (
        Index("ix_product_import_error_import_line", "import_id", "line"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_import.id", ondelete="CASCADE")
    )
    line: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str | None] = mapped_column(String(100), default=None)
    message: Mapped[str] = mapped_column(Text)
