import re
from dataclasses import dataclass


PRICE_PATTERN = re.compile(r"(-?\d+[,.]\d{2})")


@dataclass
class ReceiptItem:
    product_name: str
    quantity: float
    price: float


@dataclass
class ParsedReceipt:
    store_name: str | None
    receipt_date: str | None
    total: float | None
    items: list[ReceiptItem]


def to_float(value: str) -> float:
    return float(value.replace(",", "."))


def parse_receipt_text(text: str) -> ParsedReceipt:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    store_name = lines[0] if lines else None
    receipt_date = None
    total = None
    items: list[ReceiptItem] = []

    for line in lines:
        lower = line.lower()

        date_match = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", line)
        if date_match and receipt_date is None:
            receipt_date = date_match.group()

        price_matches = PRICE_PATTERN.findall(line)

        if not price_matches:
            continue

        price_text = price_matches[-1]
        price = to_float(price_text)

        if "total" in lower:
            total = price
            continue

        product_name = line.replace(price_text, "").strip()

        if len(product_name) >= 2:
            items.append(
                ReceiptItem(
                    product_name=product_name,
                    quantity=1,
                    price=price,
                )
            )

    return ParsedReceipt(
        store_name=store_name,
        receipt_date=receipt_date,
        total=total,
        items=items,
    )
import re
from dataclasses import dataclass


PRICE_PATTERN = re.compile(r"(-?\d+[,.]\d{2})")


@dataclass
class ReceiptItem:
    product_name: str
    quantity: float
    price: float


@dataclass
class ParsedReceipt:
    store_name: str | None
    receipt_date: str | None
    total: float | None
    items: list[ReceiptItem]


def to_float(value: str) -> float:
    return float(value.replace(",", "."))


def parse_receipt_text(text: str) -> ParsedReceipt:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    store_name = lines[0] if lines else None
    receipt_date = None
    total = None
    items: list[ReceiptItem] = []

    for line in lines:
        lower = line.lower()

        date_match = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", line)
        if date_match and receipt_date is None:
            receipt_date = date_match.group()

        price_matches = PRICE_PATTERN.findall(line)

        if not price_matches:
            continue

        price_text = price_matches[-1]
        price = to_float(price_text)

        if "total" in lower:
            total = price
            continue

        product_name = line.replace(price_text, "").strip()

        if len(product_name) >= 2:
            items.append(
                ReceiptItem(
                    product_name=product_name,
                    quantity=1,
                    price=price,
                )
            )

    return ParsedReceipt(
        store_name=store_name,
        receipt_date=receipt_date,
        total=total,
        items=items,
    )