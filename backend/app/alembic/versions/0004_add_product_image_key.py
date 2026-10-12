"""Add product.image_key

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "product", sa.Column("image_key", sa.String(length=512), nullable=True)
    )


def downgrade():
    op.drop_column("product", "image_key")
