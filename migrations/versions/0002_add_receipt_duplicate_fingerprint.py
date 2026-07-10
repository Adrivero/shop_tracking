"""Add receipt duplicate fingerprint.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipts",
        sa.Column("duplicate_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ux_receipts_duplicate_fingerprint",
        "receipts",
        ["duplicate_fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_receipts_duplicate_fingerprint", table_name="receipts")
    op.drop_column("receipts", "duplicate_fingerprint")
