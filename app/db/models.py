from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        Index("ix_receipts_purchased_at", "purchased_at"),
        Index("ix_receipts_store_name", "store_name"),
        Index("ux_receipts_duplicate_fingerprint", "duplicate_fingerprint", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_name: Mapped[str | None] = mapped_column(String(255))
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime())
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    duplicate_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )
    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReceiptItem.id",
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    price_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    receipt: Mapped[Receipt] = relationship(back_populates="items")
