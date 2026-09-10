from datetime import datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base, ReceiptItem, ReceiptRepository, create_db_engine
from app.tools.backup_database import backup_database
from app.tools.parser import ParsedReceipt, ReceiptItem as ParsedReceiptItem


def make_repository(tmp_path) -> tuple[ReceiptRepository, object]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return ReceiptRepository(engine), engine


def sample_receipt() -> ParsedReceipt:
    return ParsedReceipt(
        store_name="MERCADONA S.A.",
        receipt_date="07/07/2026",
        receipt_time="09:42:13",
        total=3.10,
        items=[
            ParsedReceiptItem(
                product_name="LECHE ENTERA",
                quantity=2,
                unit_price=0.95,
                price=1.90,
            ),
            ParsedReceiptItem(
                product_name="MANZANAS",
                quantity=1,
                unit_price=None,
                weight_kg=0.500,
                price_per_kg=2.40,
                price=1.20,
            ),
        ],
    )


def test_save_and_reload_receipt_with_exact_values(tmp_path):
    repository, _engine = make_repository(tmp_path)

    stored = repository.save_receipt(sample_receipt())
    loaded = repository.get_receipt(stored.id)

    assert loaded is not None
    assert loaded.store_name == "MERCADONA S.A."
    assert loaded.purchased_at == datetime(2026, 7, 7, 9, 42, 13)
    assert loaded.total == Decimal("3.10")
    assert len(loaded.items) == 2
    assert loaded.items[0].quantity == Decimal("2.000")
    assert loaded.items[0].unit_price == Decimal("0.95")
    assert loaded.items[0].line_total == Decimal("1.90")
    assert loaded.items[1].weight_kg == Decimal("0.500")
    assert loaded.items[1].price_per_kg == Decimal("2.40")


def test_save_receipt_returns_existing_row_for_duplicate(tmp_path):
    repository, _engine = make_repository(tmp_path)

    first = repository.save_receipt(sample_receipt())
    second = repository.save_receipt(sample_receipt())

    assert second.id == first.id
    assert second.was_duplicate is True
    assert repository.count_receipts() == 1


def test_find_by_date_and_total_matches_same_day_and_price(tmp_path):
    repository, _engine = make_repository(tmp_path)
    existing = repository.save_receipt(sample_receipt())
    scanned = sample_receipt()
    scanned.store_name = "OCR STORE"
    scanned.receipt_time = "22:15"
    scanned.items[0] = ParsedReceiptItem(
        product_name="DIFFERENT OCR PRODUCT",
        quantity=1,
        unit_price=1.90,
        price=1.90,
    )

    match = repository.find_by_date_and_total(scanned)

    assert match is not None
    assert match.id == existing.id


def test_save_receipt_allows_same_header_with_different_items(tmp_path):
    repository, _engine = make_repository(tmp_path)
    changed = sample_receipt()
    changed.items[0] = ParsedReceiptItem(
        product_name="LECHE ENTERA",
        quantity=1,
        unit_price=0.95,
        price=0.95,
    )

    first = repository.save_receipt(sample_receipt())
    second = repository.save_receipt(changed)

    assert second.id != first.id
    assert second.was_duplicate is False
    assert repository.count_receipts() == 2


def test_save_receipt_rolls_back_every_item_on_failure(tmp_path):
    repository, _engine = make_repository(tmp_path)
    parsed = sample_receipt()
    parsed.items.append(
        ParsedReceiptItem(product_name=None, quantity=1, unit_price=1, price=1)
    )

    with pytest.raises(IntegrityError):
        repository.save_receipt(parsed)

    assert repository.count_receipts() == 0


def test_delete_receipt_cascades_to_items(tmp_path):
    repository, engine = make_repository(tmp_path)
    receipt_id = repository.save_receipt(sample_receipt()).id

    assert repository.delete_receipt(receipt_id) is True
    assert repository.get_receipt(receipt_id) is None
    with Session(engine) as session:
        item_count = session.scalar(select(func.count()).select_from(ReceiptItem))
    assert item_count == 0


def test_update_receipt_replaces_details_and_items(tmp_path):
    repository, _engine = make_repository(tmp_path)
    receipt_id = repository.save_receipt(sample_receipt()).id
    replacement = ParsedReceipt(
        store_name="CORRECTED STORE",
        receipt_date="08/07/2026",
        receipt_time="18:15",
        total=7.25,
        items=[
            ParsedReceiptItem(
                product_name="CORRECTED PRODUCT",
                quantity=1,
                unit_price=7.25,
                price=7.25,
            )
        ],
    )

    assert repository.update_receipt(receipt_id, replacement) is True

    loaded = repository.get_receipt(receipt_id)
    assert loaded is not None
    assert loaded.store_name == "CORRECTED STORE"
    assert loaded.total == Decimal("7.25")
    assert loaded.purchased_at == datetime(2026, 7, 8, 18, 15)
    assert [item.product_name for item in loaded.items] == ["CORRECTED PRODUCT"]


def test_update_missing_receipt_returns_false(tmp_path):
    repository, _engine = make_repository(tmp_path)

    assert repository.update_receipt(999, sample_receipt()) is False


def test_list_receipts_validates_pagination(tmp_path):
    repository, _engine = make_repository(tmp_path)
    repository.save_receipt(sample_receipt())

    assert len(repository.list_receipts(limit=1)) == 1
    with pytest.raises(ValueError, match="limit"):
        repository.list_receipts(limit=0)


def test_alembic_migration_creates_database_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    command.upgrade(Config("alembic.ini"), "head")

    engine = create_db_engine(f"sqlite:///{database_path}")
    schema = inspect(engine)
    assert {"receipts", "receipt_items"} <= set(schema.get_table_names())
    assert {column["name"] for column in schema.get_columns("receipt_items")} >= {
        "receipt_id",
        "quantity",
        "unit_price",
        "weight_kg",
        "price_per_kg",
        "line_total",
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"


def test_missing_sqlite_database_can_be_created_by_migrations(tmp_path, monkeypatch):
    database_path = tmp_path / "nested" / "created.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    command.upgrade(Config("alembic.ini"), "head")

    assert database_path.is_file()


def test_sqlite_backup_contains_saved_receipts(tmp_path):
    database_path = tmp_path / "source.db"
    engine = create_db_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    ReceiptRepository(engine).save_receipt(sample_receipt())

    backup_path = backup_database(
        tmp_path / "backups" / "backup.db",
        database_url=f"sqlite:///{database_path}",
    )

    backup_repository = ReceiptRepository(
        create_db_engine(f"sqlite:///{backup_path}")
    )
    assert backup_repository.count_receipts() == 1
