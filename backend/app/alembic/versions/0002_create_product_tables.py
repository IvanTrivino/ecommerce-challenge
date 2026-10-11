"""Create product_category and product tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_category",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_category_code",
        "product_category",
        ["code"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
    )
    op.create_table(
        "product",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_uuid", sa.Uuid(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
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
        sa.ForeignKeyConstraint(["category_uuid"], ["product_category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_category_uuid", "product", ["category_uuid"])
    op.create_index(
        "ix_product_sku",
        "product",
        ["sku"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def downgrade():
    op.drop_index("ix_product_sku", table_name="product")
    op.drop_index("ix_product_category_uuid", table_name="product")
    op.drop_table("product")
    op.drop_index("ix_product_category_code", table_name="product_category")
    op.drop_table("product_category")
