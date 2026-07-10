from dataclasses import asdict
from pathlib import Path

from app.tools.parser import parse_receipt_text


def test_parse_mercadona_receipt_01():
    text = Path("tests/fixtures/mercadona/mercadona_01.txt").read_text(encoding="utf-8")

    receipt = parse_receipt_text(text)

    assert receipt.store_name == "MERCADONA S.A."
    assert receipt.receipt_date == "25/06/2026"
    assert receipt.receipt_time == "10:01"
    assert receipt.total == 81.04

    items_by_name = {item.product_name: item for item in receipt.items}

    assert items_by_name["PAN M. 100% INTEGRAL"].price == 0.90
    assert items_by_name["TORTILLA PAT C/CEB"].price == 2.60
    assert items_by_name["BEBIDA AVENA CHOCO"].price == 7.50
    assert items_by_name["PIPA GIGANTE AGUASAL"].price == 1.10
    assert items_by_name["GAZPACHO TRADICIONAL"].price == 1.60
    assert items_by_name["CEREAL RELLENO S/G"].price == 4.50
    assert items_by_name["CEREAL RELLENO S/G"].quantity == 2
    assert items_by_name["CEREAL RELLENO S/G"].unit_price == 2.25
    assert items_by_name["PAN M. BLANCO S/GLU"].price == 8.22
    assert items_by_name["PAN M. BLANCO S/GLU"].quantity == 3
    assert items_by_name["MAYONESA BOCA ABAJO"].price == 2.80
    assert items_by_name["MAYONESA BOCA ABAJO"].quantity == 2
    assert items_by_name["TORTITA CAMPESTRE"].price == 5.25
    assert items_by_name["TORTITA CAMPESTRE"].quantity == 3

    assert items_by_name["AGUACATE"].price == 1.34
    assert items_by_name["AGUACATE"].weight_kg == 0.268
    assert items_by_name["AGUACATE"].price_per_kg == 5.00
    assert items_by_name["AGUACATE"].unit_price is None
    assert items_by_name["PLATANO"].price == 3.06
    assert items_by_name["PLATANO"].weight_kg == 1.056
    assert items_by_name["PLATANO"].price_per_kg == 2.90
    assert items_by_name["PARAGUAYO"].price == 1.96
    assert items_by_name["PARAGUAYO"].weight_kg == 0.560
    assert items_by_name["PARAGUAYO"].price_per_kg == 3.50

    assert len(receipt.items) == 27

    # Dataclasses can be converted directly into primitive dictionaries before
    # inserting them through a database layer.
    receipt_data = asdict(receipt)
    assert receipt_data["items"][24]["weight_kg"] == 0.268


def test_parse_mercadona_receipt_02():
    text = Path("tests/fixtures/mercadona/mercadona_02.txt").read_text(
        encoding="utf-8"
    )

    receipt = parse_receipt_text(text)

    assert receipt.store_name == "MERCADONA S.A."
    assert receipt.receipt_date == "02/07/2026"
    assert receipt.receipt_time == "18:35"
    assert receipt.total == 83.72
    assert len(receipt.items) == 25

    items_by_name = {item.product_name: item for item in receipt.items}

    assert items_by_name["CEREZA 1 KG"].price == 5.81
    assert items_by_name["JAMON S. EXTRA FINO"].quantity == 2
    assert items_by_name["JAMON S. EXTRA FINO"].unit_price == 2.45
    assert items_by_name["JAMON S. EXTRA FINO"].price == 4.90
    assert items_by_name["PAN M. BLANCO S/GLU"].quantity == 2
    assert items_by_name["PAN M. BLANCO S/GLU"].price == 5.48

    platano = items_by_name["PLATANO"]
    assert platano.quantity == 1
    assert platano.weight_kg == 1.080
    assert platano.price_per_kg == 2.90
    assert platano.unit_price is None
    assert platano.price == 3.13
