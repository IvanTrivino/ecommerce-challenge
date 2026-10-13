"""Create order, cart item and order notification tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def base_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade():
    op.create_table(
        "order",
        *base_columns(),
        sa.Column("user_uuid", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_weight", sa.Numeric(12, 3), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_reference", sa.String(length=100), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('draft', 'in_progress', 'completed', 'cancelled')",
            name="ck_order_state",
        ),
        sa.CheckConstraint(
            "state = 'draft' OR (placed_at IS NOT NULL AND total_price IS NOT NULL "
            "AND total_weight IS NOT NULL)",
            name="ck_order_placed_totals",
        ),
        sa.ForeignKeyConstraint(["user_uuid"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_user_uuid", "order", ["user_uuid"])
    op.create_index(
        "ux_order_user_draft",
        "order",
        ["user_uuid"],
        unique=True,
        postgresql_where=sa.text("state = 'draft' AND NOT is_deleted"),
    )
    op.create_index(
        "ix_order_state_placed_at", "order", ["state", sa.text("placed_at DESC")]
    )
    op.create_index(
        "ix_order_user_placed_at",
        "order",
        ["user_uuid", sa.text("placed_at DESC")],
        postgresql_where=sa.text("state <> 'draft'"),
    )

    op.create_table(
        "cart_item",
        *base_columns(),
        sa.Column("order_uuid", sa.Uuid(), nullable=False),
        sa.Column("product_uuid", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit_weight", sa.Numeric(10, 3), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("product_sku", sa.String(length=100), nullable=True),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_cart_item_quantity"),
        sa.ForeignKeyConstraint(["order_uuid"], ["order.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_uuid"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_uuid", "product_uuid", name="uq_cart_item_order_product"
        ),
    )
    op.create_index("ix_cart_item_order_uuid", "cart_item", ["order_uuid"])
    op.create_index("ix_cart_item_product_uuid", "cart_item", ["product_uuid"])

    op.create_table(
        "order_notification",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("order_uuid", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('placed', 'cancelled', 'completed')",
            name="ck_order_notification_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_order_notification_status",
        ),
        sa.ForeignKeyConstraint(["order_uuid"], ["order.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_uuid", "kind", name="uq_order_notification_order_kind"
        ),
    )
    op.create_index(
        "ix_order_notification_pending",
        "order_notification",
        ["available_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade():
    op.drop_index("ix_order_notification_pending", table_name="order_notification")
    op.drop_table("order_notification")
    op.drop_index("ix_cart_item_product_uuid", table_name="cart_item")
    op.drop_index("ix_cart_item_order_uuid", table_name="cart_item")
    op.drop_table("cart_item")
    op.drop_index("ix_order_user_placed_at", table_name="order")
    op.drop_index("ix_order_state_placed_at", table_name="order")
    op.drop_index("ux_order_user_draft", table_name="order")
    op.drop_index("ix_order_user_uuid", table_name="order")
    op.drop_table("order")
