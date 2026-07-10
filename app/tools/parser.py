import re
from dataclasses import dataclass


MONEY_PATTERN = re.compile(r"-?\d+[,.]\d{2}")
DATE_PATTERN = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\b")
WEIGHT_PATTERN = re.compile(
    r"(?P<weight>\d+[,.]\d{3})\s*kg\s+"
    r"(?P<price_per_kg>\d+[,.]\d{2})\s*(?:€|e)?\s*/\s*kg\s+"
    r"(?P<total>\d+[,.]\d{2})",
    re.IGNORECASE,
)
QUANTITY_PATTERN = re.compile(r"^[^\w+]*(?P<quantity>\d+)\s+(?P<name>.+)$")

ITEM_SECTION_END_MARKERS = (
    "tarjeta",
    "efectivo",
    "iva base",
    "base imponible",
    "cambio",
)
NON_ITEM_MARKERS = (
    "factura",
    "telefono",
    "avda",
    "op:",
    "tienda:",
    "fecha:",
    "hora:",
    "ticket",
)


@dataclass
class ReceiptItem:
    """One purchasable receipt line, ready to map to a database row."""

    product_name: str
    quantity: float
    price: float
    unit_price: float | None = None
    weight_kg: float | None = None
    price_per_kg: float | None = None


@dataclass
class ParsedReceipt:
    """Structured data extracted from one receipt."""

    store_name: str | None
    receipt_date: str | None
    receipt_time: str | None
    total: float | None
    items: list[ReceiptItem]


def to_float(value: str) -> float:
    return float(value.replace(",", "."))


def _store_name(lines: list[str]) -> str | None:
    if not lines:
        return None

    upper_text = "\n".join(lines).upper()
    first_line = lines[0].strip(" |:_-")

    # Tesseract often misses the Mercadona wordmark, but its CIF is stable.
    compact_text = re.sub(r"\W", "", upper_text)
    if "MERCADONA" in upper_text or "46103834" in compact_text or "103834" in compact_text:
        if "MERCADONA" in first_line.upper():
            return "MERCADONA S.A." if "S.A" in first_line.upper() else "MERCADONA"
        return "MERCADONA S.A."
    if "ALIMERKA" in upper_text:
        return "ALIMERKA"
    return first_line or None


def _clean_product_name(value: str) -> str:
    value = value.strip()
    value = value.replace("$/", "S/")
    value = re.sub(r"^[^\w+]+", "", value)
    value = re.sub(r"[\s.:;|_=\"'`“”‘’´-]+$", "", value)
    return re.sub(r"\s+", " ", value)


def _quantity_and_name(value: str) -> tuple[float, str]:
    match = QUANTITY_PATTERN.match(value.strip())
    if match:
        return float(match.group("quantity")), _clean_product_name(match.group("name"))
    return 1.0, _clean_product_name(value)


def _is_total_line(line: str) -> bool:
    return bool(re.search(r"(?:^|[^A-Z])TOTAL(?:\s|[.:(€])", line.upper()))


def _parse_regular_item(line: str) -> ReceiptItem | None:
    prices = list(MONEY_PATTERN.finditer(line))
    if not prices:
        return None

    quantity, product_name = _quantity_and_name(line[: prices[0].start()])
    if len(product_name) < 2:
        return None

    total_price = to_float(prices[-1].group())
    unit_price = to_float(prices[-2].group()) if len(prices) > 1 else total_price

    return ReceiptItem(
        product_name=product_name,
        quantity=quantity,
        unit_price=unit_price,
        price=total_price,
    )


def _normalize_ocr_line(line: str) -> str:
    line = re.sub(r"(?<=\d)[;:](?=\d{2}\b)", ",", line)
    line = re.sub(r"(?<=\d)\)\s*,\s*(?=\d{2}\b)", ",", line)
    line = re.sub(r"(?<=\d)\s*,\s*(?=\d{2}\b)", ",", line)
    return line


def parse_receipt_text(text: str) -> ParsedReceipt:
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = [_normalize_ocr_line(line) for line in raw_lines]

    receipt_date = None
    receipt_time = None
    total = None
    total_priority = 0
    items: list[ReceiptItem] = []
    accept_items = True
    in_tax_summary = False

    for index, line in enumerate(lines):
        raw_line = raw_lines[index]
        if receipt_date is None:
            date_match = DATE_PATTERN.search(raw_line)
            if date_match:
                receipt_date = date_match.group(1)

        if receipt_time is None:
            time_match = TIME_PATTERN.search(raw_line.replace(";", ":"))
            if time_match:
                receipt_time = time_match.group()

        lower_line = line.lower()

        if "descrip" in lower_line or "producto" in lower_line:
            accept_items = True
            continue

        if DATE_PATTERN.search(raw_line) or any(
            marker in lower_line for marker in NON_ITEM_MARKERS
        ):
            continue

        if "iva" in lower_line and ("base" in lower_line or "cuota" in lower_line):
            in_tax_summary = True
            accept_items = False
            continue

        prices = MONEY_PATTERN.findall(line)
        is_card_payment = any(
            marker in lower_line for marker in ("tarjeta", "bancaria", "bancarta")
        )
        is_explicit_amount = "importe" in lower_line and bool(prices)
        if is_card_payment or is_explicit_amount:
            payment_priority = 3 if "importe" in lower_line else 1
            if prices and total_priority < payment_priority:
                total = to_float(prices[-1])
                total_priority = payment_priority
            accept_items = False
            continue

        if _is_total_line(line):
            prices = MONEY_PATTERN.findall(line)
            if prices and not in_tax_summary and total_priority < 2:
                total = to_float(prices[-1])
                total_priority = 2
            accept_items = False
            continue

        if any(marker in lower_line for marker in ITEM_SECTION_END_MARKERS):
            accept_items = False
            continue

        if not accept_items:
            continue

        weight_match = WEIGHT_PATTERN.search(line)
        if weight_match and items:
            # A weighed product is printed over two lines. The preceding line
            # supplied its name and quantity; this line supplies its prices.
            pending_item = items[-1]
            if pending_item.price == 0:
                pending_item.weight_kg = to_float(weight_match.group("weight"))
                pending_item.price_per_kg = to_float(weight_match.group("price_per_kg"))
                pending_item.price = to_float(weight_match.group("total"))
                pending_item.unit_price = None
            continue

        item = _parse_regular_item(line)
        if item:
            items.append(item)
            continue

        # Only retain a price-less line when the next line is a weight detail.
        if index + 1 < len(lines) and WEIGHT_PATTERN.search(lines[index + 1]):
            quantity, product_name = _quantity_and_name(line)
            if len(product_name) >= 2:
                items.append(
                    ReceiptItem(
                        product_name=product_name,
                        quantity=quantity,
                        unit_price=None,
                        price=0,
                    )
                )

    return ParsedReceipt(
        store_name=_store_name(lines),
        receipt_date=receipt_date,
        receipt_time=receipt_time,
        total=total,
        items=items,
    )
