"""Create product import tables and unique category names

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT lower(name) FROM product_category WHERE NOT is_deleted "
                "GROUP BY lower(name) HAVING count(*) > 1"
            )
        )
        .scalars()
        .all()
    )
    if duplicates:
        raise RuntimeError(
            "Cannot add unique category names, live duplicates exist: "
            + ", ".join(sorted(duplicates))
            + ". Rename or delete them, then re-run the migration."
        )
    op.create_index(
        "ix_product_category_name",
        "product_category",
        [sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
    )

    def count_column(name: str) -> sa.Column:
        return sa.Column(name, sa.Integer(), server_default="0", nullable=False)

    op.create_table(
        "product_import",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("file_key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "bytes_processed", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("etag", sa.String(length=255), nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("next_line", sa.Integer(), server_default="1", nullable=False),
        count_column("created_count"),
        count_column("updated_count"),
        count_column("unchanged_count"),
        count_column("error_count"),
        count_column("blank_count"),
        count_column("categories_created"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_product_import_status",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_key"),
    )
    op.create_index(
        "ix_product_import_active",
        "product_import",
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_index(
        "ix_product_import_created_at",
        "product_import",
        [sa.text("created_at DESC")],
    )

    op.create_table(
        "product_import_error",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_id"], ["product_import.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_import_error_import_line",
        "product_import_error",
        ["import_id", "line"],
    )


def downgrade():
    op.drop_index(
        "ix_product_import_error_import_line", table_name="product_import_error"
    )
    op.drop_table("product_import_error")
    op.drop_index("ix_product_import_created_at", table_name="product_import")
    op.drop_index("ix_product_import_active", table_name="product_import")
    op.drop_table("product_import")
    op.drop_index("ix_product_category_name", table_name="product_category")
