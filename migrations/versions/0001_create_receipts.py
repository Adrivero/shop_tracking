"""Create receipts and receipt items.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_name", sa.String(length=255), nullable=True),
        sa.Column("purchased_at", sa.DateTime(), nullable=True),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_receipts_purchased_at", "receipts", ["purchased_at"])
    op.create_index("ix_receipts_store_name", "receipts", ["store_name"])

    op.create_table(
        "receipt_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "receipt_id",
            sa.Integer(),
            sa.ForeignKey("receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_name", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("price_per_kg", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=False),
    )
    op.create_index("ix_receipt_items_receipt_id", "receipt_items", ["receipt_id"])


def downgrade() -> None:
    op.drop_index("ix_receipt_items_receipt_id", table_name="receipt_items")
    op.drop_table("receipt_items")
    op.drop_index("ix_receipts_store_name", table_name="receipts")
    op.drop_index("ix_receipts_purchased_at", table_name="receipts")
    op.drop_table("receipts")
