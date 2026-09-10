import hashlib
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import Engine, delete, or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.tools.parser import ParsedReceipt

from .models import Receipt, ReceiptItem


MONEY_QUANTUM = Decimal("0.01")
MEASUREMENT_QUANTUM = Decimal("0.001")


def _decimal(value: float | Decimal | None, quantum: Decimal) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def _purchase_datetime(receipt_date: str | None, receipt_time: str | None) -> datetime | None:
    if receipt_date is None:
        return None

    normalized_time = receipt_time or "00:00"
    value = f"{receipt_date} {normalized_time}"
    for date_format in ("%d/%m/%Y", "%d-%m-%Y"):
        for time_format in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(value, f"{date_format} {time_format}")
            except ValueError:
                continue
    raise ValueError(f"Unsupported receipt date/time: {value}")


def _normalized_text(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _decimal_text(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _item_signature(item: ReceiptItem) -> tuple[str, str, str, str, str, str]:
    return (
        _normalized_text(item.product_name),
        _decimal_text(item.quantity),
        _decimal_text(item.unit_price),
        _decimal_text(item.weight_kg),
        _decimal_text(item.price_per_kg),
        _decimal_text(item.line_total),
    )


def _receipt_signature(receipt: Receipt) -> tuple[object, ...]:
    return (
        _normalized_text(receipt.store_name),
        receipt.purchased_at.isoformat(timespec="seconds") if receipt.purchased_at else "",
        _decimal_text(receipt.total),
        tuple(_item_signature(item) for item in receipt.items),
    )


def _receipt_fingerprint(receipt: Receipt) -> str:
    return hashlib.sha256(repr(_receipt_signature(receipt)).encode("utf-8")).hexdigest()


class ReceiptRepository:
    """Transactional persistence API for parsed receipts."""

    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def save_receipt(self, parsed: ParsedReceipt) -> Receipt:
        receipt = Receipt(
            store_name=parsed.store_name,
            purchased_at=_purchase_datetime(parsed.receipt_date, parsed.receipt_time),
            total=_decimal(parsed.total, MONEY_QUANTUM),
            items=self._item_models(parsed),
        )
        receipt.duplicate_fingerprint = _receipt_fingerprint(receipt)

        with self._session_factory.begin() as session:
            duplicate = self._find_duplicate(session, receipt)
            if duplicate is not None:
                duplicate.was_duplicate = True
                return duplicate

            receipt.was_duplicate = False
            session.add(receipt)
            session.flush()
        return receipt

    def find_by_date_and_total(self, parsed: ParsedReceipt) -> Receipt | None:
        purchased_at = _purchase_datetime(parsed.receipt_date, parsed.receipt_time)
        total = _decimal(parsed.total, MONEY_QUANTUM)
        if purchased_at is None or total is None:
            return None

        day_start = purchased_at.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items))
            .where(
                Receipt.total == total,
                Receipt.purchased_at >= day_start,
                Receipt.purchased_at < day_end,
            )
            .order_by(Receipt.id)
            .limit(1)
        )
        with self._session_factory() as session:
            return session.scalar(statement)

    @staticmethod
    def _item_models(parsed: ParsedReceipt) -> list[ReceiptItem]:
        return [
            ReceiptItem(
                product_name=item.product_name,
                quantity=_decimal(item.quantity, MEASUREMENT_QUANTUM),
                unit_price=_decimal(item.unit_price, MONEY_QUANTUM),
                weight_kg=_decimal(item.weight_kg, MEASUREMENT_QUANTUM),
                price_per_kg=_decimal(item.price_per_kg, MONEY_QUANTUM),
                line_total=_decimal(item.price, MONEY_QUANTUM),
            )
            for item in parsed.items
        ]

    def update_receipt(self, receipt_id: int, parsed: ParsedReceipt) -> bool:
        """Replace a receipt and its items in one transaction."""
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items))
            .where(Receipt.id == receipt_id)
        )
        with self._session_factory.begin() as session:
            receipt = session.scalar(statement)
            if receipt is None:
                return False
            receipt.store_name = parsed.store_name
            receipt.purchased_at = _purchase_datetime(
                parsed.receipt_date, parsed.receipt_time
            )
            receipt.total = _decimal(parsed.total, MONEY_QUANTUM)
            receipt.items = self._item_models(parsed)
            receipt.duplicate_fingerprint = _receipt_fingerprint(receipt)
            session.flush()
        return True

    @staticmethod
    def _find_duplicate(session: Session, receipt: Receipt) -> Receipt | None:
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items))
            .where(
                or_(
                    Receipt.duplicate_fingerprint == receipt.duplicate_fingerprint,
                    (
                        (Receipt.store_name == receipt.store_name)
                        & (Receipt.purchased_at == receipt.purchased_at)
                        & (Receipt.total == receipt.total)
                    ),
                )
            )
            .order_by(Receipt.id)
        )
        receipt_signature = _receipt_signature(receipt)
        for candidate in session.scalars(statement):
            if candidate.duplicate_fingerprint == receipt.duplicate_fingerprint:
                return candidate
            if _receipt_signature(candidate) == receipt_signature:
                if candidate.duplicate_fingerprint is None:
                    candidate.duplicate_fingerprint = receipt.duplicate_fingerprint
                    session.flush()
                return candidate
        return None

    def get_receipt(self, receipt_id: int) -> Receipt | None:
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items))
            .where(Receipt.id == receipt_id)
        )
        with self._session_factory() as session:
            return session.scalar(statement)

    def list_receipts(self, *, limit: int = 100, offset: int = 0) -> list[Receipt]:
        if limit < 1 or offset < 0:
            raise ValueError("limit must be positive and offset cannot be negative")
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items))
            .order_by(Receipt.purchased_at.desc(), Receipt.id.desc())
            .limit(limit)
            .offset(offset)
        )
        with self._session_factory() as session:
            return list(session.scalars(statement))

    def delete_receipt(self, receipt_id: int) -> bool:
        with self._session_factory.begin() as session:
            result = session.execute(delete(Receipt).where(Receipt.id == receipt_id))
            return result.rowcount > 0

    def count_receipts(self) -> int:
        with self._session_factory() as session:
            return len(session.scalars(select(Receipt.id)).all())
