"""End-to-end tests: receipt JPEG -> OCR -> parser -> dataclasses."""

import shutil

import pytest

from decimal import Decimal

from app.db import Base, ReceiptRepository, create_db_engine
from app.scan_one import PROJECT_ROOT, scan_and_save_receipt, scan_receipt


pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="The end-to-end OCR tests require the Tesseract executable",
)


def raw_image(filename: str):
    direct_path = PROJECT_ROOT / "data/raw" / filename
    if direct_path.exists():
        return direct_path
    matches = sorted((PROJECT_ROOT / "data/raw").glob(f"*-{filename}"))
    if matches:
        return matches[-1]
    pytest.skip(f"Receipt image is not present: {filename}")


def test_mercadona_01_image_pipeline():
    receipt = scan_receipt(raw_image("receipt_mercadona_01.jpeg"))

    assert receipt.store_name == "MERCADONA S.A."
    assert receipt.receipt_date == "25/06/2026"
    assert receipt.receipt_time == "10:01"
    assert receipt.total == 81.04

    items = {item.product_name: item for item in receipt.items}
    assert items["CEREAL RELLENO S/G"].quantity == 2
    assert items["CEREAL RELLENO S/G"].unit_price == 2.25
    assert items["CEREAL RELLENO S/G"].price == 4.50
    assert items["AGUACATE"].weight_kg == 0.268
    assert items["AGUACATE"].price_per_kg == 5.00
    assert items["AGUACATE"].price == 1.34


def test_mercadona_02_image_pipeline():
    receipt = scan_receipt(raw_image("receipt_mercadona_02.jpeg"))

    assert receipt.store_name == "MERCADONA S.A."
    assert receipt.receipt_date == "02/07/2026"
    assert receipt.receipt_time == "18:35"
    assert receipt.total == 83.72

    items = {item.product_name: item for item in receipt.items}
    assert items["JAMON S. EXTRA FINO"].quantity == 2
    assert items["JAMON S. EXTRA FINO"].unit_price == 2.45
    assert items["JAMON S. EXTRA FINO"].price == 4.90
    assert items["PAN DE FIBRA"].quantity == 2
    assert items["PAN DE FIBRA"].price == 2.26


def test_alimerka_01_imagepipeline():
    receipt = scan_receipt(raw_image("receipt_Alimerka_01.jpeg"))

    assert receipt.store_name == "ALIMERKA"
    assert receipt.receipt_date == "01/07/2026"
    assert receipt.receipt_time == "13:37:23"
    assert receipt.total == 14.22
    assert len(receipt.items) == 6

    items = {item.product_name: item for item in receipt.items}
    assert items["BOLSA PEQ 70% REC"].price == 0.07
    assert items["CERVEZA DAMM"].price == 0.78
    assert items["PIMIENTOS ASAD. IBSA"].price == 4.19


def test_receipt_image_to_database_pipeline(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'pipeline.db'}")
    Base.metadata.create_all(engine)
    repository = ReceiptRepository(engine)

    stored = scan_and_save_receipt(
        raw_image("receipt_Alimerka_01.jpeg"), repository
    )
    loaded = repository.get_receipt(stored.id)

    assert loaded is not None
    assert loaded.store_name == "ALIMERKA"
    assert loaded.total == Decimal("14.22")
    assert len(loaded.items) == 6
    assert loaded.items[0].line_total == Decimal("0.07")
