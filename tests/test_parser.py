from pathlib import Path

from app.parser import parse_receipt_text


def test_parse_receipt_text_extracts_basic_receipt_data():
    text = Path("tests/fixtures/receipt_01.txt").read_text(encoding="utf-8")

    receipt = parse_receipt_text(text)

    assert receipt.store_name == "MERCADONA"
    assert receipt.receipt_date == "07/07/2026"
    assert receipt.total == 4.30

    assert len(receipt.items) == 4

    assert receipt.items[0].product_name == "PAN INTEGRAL"
    assert receipt.items[0].price == 1.25

    assert receipt.items[1].product_name == "LECHE ENTERA"
    assert receipt.items[1].price == 0.95

    assert receipt.items[2].product_name == "MANZANAS"
    assert receipt.items[2].price == 2.40

    assert receipt.items[3].product_name == "DESCUENTO"
    assert receipt.items[3].price == -0.30
