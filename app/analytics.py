"""Read-only statistics used by the local dashboard."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Receipt


ZERO = Decimal("0")


@dataclass(frozen=True)
class StoreStat:
    name: str
    receipts: int
    spend: Decimal
    share: float


@dataclass(frozen=True)
class TrendPoint:
    key: str
    label: str
    spend: Decimal
    receipts: int


@dataclass(frozen=True)
class ProductStat:
    name: str
    purchases: int
    quantity: Decimal
    spend: Decimal
    average_line_price: Decimal
    latest_purchase: datetime | None


@dataclass(frozen=True)
class DashboardStats:
    receipt_count: int
    item_count: int
    unique_products: int
    total_spend: Decimal
    average_basket: Decimal
    stores: list[StoreStat]
    trend: list[TrendPoint]
    products: list[ProductStat]
    recent_receipts: list[Receipt]


def _money(value: Decimal | None) -> Decimal:
    return value or ZERO


def _product_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def dashboard_stats(engine: Engine) -> DashboardStats:
    """Build the complete dashboard read model from saved receipts."""
    statement = (
        select(Receipt)
        .options(selectinload(Receipt.items))
        .order_by(Receipt.purchased_at.desc(), Receipt.id.desc())
    )
    with Session(engine) as session:
        receipts = list(session.scalars(statement))

    total_spend = sum((_money(receipt.total) for receipt in receipts), ZERO)
    item_count = sum(len(receipt.items) for receipt in receipts)

    store_values: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"receipts": 0, "spend": ZERO}
    )
    trend_values: dict[str, dict[str, Decimal | int | str]] = {}
    product_values: dict[str, dict[str, object]] = {}

    for receipt in receipts:
        store = (receipt.store_name or "Unknown store").strip() or "Unknown store"
        store_values[store]["receipts"] += 1
        store_values[store]["spend"] += _money(receipt.total)

        if receipt.purchased_at:
            key = receipt.purchased_at.strftime("%Y-%m")
            trend_values.setdefault(
                key,
                {
                    "label": receipt.purchased_at.strftime("%b %Y"),
                    "spend": ZERO,
                    "receipts": 0,
                },
            )
            trend_values[key]["spend"] += _money(receipt.total)
            trend_values[key]["receipts"] += 1

        for item in receipt.items:
            key = _product_key(item.product_name)
            values = product_values.setdefault(
                key,
                {
                    "name": item.product_name.strip(),
                    "purchases": 0,
                    "quantity": ZERO,
                    "spend": ZERO,
                    "latest": None,
                },
            )
            values["purchases"] += 1
            values["quantity"] += item.quantity
            values["spend"] += item.line_total
            if receipt.purchased_at and (
                values["latest"] is None or receipt.purchased_at > values["latest"]
            ):
                values["latest"] = receipt.purchased_at
                values["name"] = item.product_name.strip()

    stores = [
        StoreStat(
            name=name,
            receipts=int(values["receipts"]),
            spend=Decimal(values["spend"]),
            share=float(Decimal(values["spend"]) / total_spend * 100)
            if total_spend
            else 0,
        )
        for name, values in store_values.items()
    ]
    stores.sort(key=lambda value: value.spend, reverse=True)

    trend = [
        TrendPoint(
            key=key,
            label=str(values["label"]),
            spend=Decimal(values["spend"]),
            receipts=int(values["receipts"]),
        )
        for key, values in sorted(trend_values.items())[-12:]
    ]

    products = [
        ProductStat(
            name=str(values["name"]),
            purchases=int(values["purchases"]),
            quantity=Decimal(values["quantity"]),
            spend=Decimal(values["spend"]),
            average_line_price=Decimal(values["spend"])
            / int(values["purchases"]),
            latest_purchase=values["latest"],
        )
        for values in product_values.values()
    ]
    products.sort(key=lambda value: value.spend, reverse=True)

    return DashboardStats(
        receipt_count=len(receipts),
        item_count=item_count,
        unique_products=len(products),
        total_spend=total_spend,
        average_basket=total_spend / len(receipts) if receipts else ZERO,
        stores=stores,
        trend=trend,
        products=products,
        recent_receipts=receipts[:8],
    )
