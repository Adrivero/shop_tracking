from pathlib import Path

import pytest

from app.tools.parser import parse_receipt_text


def test_parse_alimerka_receipt_01():
    text = Path("tests/fixtures/alimerka/alimerka_01.txt").read_text(
        encoding="utf-8"
    )

    receipt = parse_receipt_text(text)

    assert receipt.store_name == "ALIMERKA"
    assert receipt.receipt_date == "01/07/2026"
    assert receipt.receipt_time == "13:37:23"
    assert receipt.total == 14.22
    assert len(receipt.items) == 6

    items_by_name = {item.product_name: item for item in receipt.items}

    assert items_by_name["BOLSA PEQ 70% REC"].price == 0.07
    assert items_by_name["CERVEZA DAMM"].price == 0.78
    assert items_by_name["CHOC. VALOR NEGRO 70%"].price == 4.99
    assert items_by_name["COCA COLA ZERO"].price == 1.50
    assert items_by_name["PAN FORNO SCHAR 300G"].price == 2.69
    assert items_by_name["PIMIENTOS ASAD. IBSA"].price == 4.19
    assert sum(item.price for item in receipt.items) == pytest.approx(receipt.total)
