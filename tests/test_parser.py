from pathlib import Path

from app.tools.parser import parse_receipt_text


def test_parse_receipt_text_extracts_time_after_a_label():
    text = """ALIMERKA
    BOLSA PEQ 70% REC       0,07 N
    CERVEZA DAMM            0,78 N
    TOTAL.                  0,85 EUR
    Tienda:0500 Fecha:01/07/2026 Hora: 13:37:23
    """

    receipt = parse_receipt_text(text)

    assert receipt.store_name == "ALIMERKA"
    assert receipt.receipt_date == "01/07/2026"
    assert receipt.receipt_time == "13:37:23"
    assert receipt.total == 0.85
    assert [item.product_name for item in receipt.items] == [
        "BOLSA PEQ 70% REC",
        "CERVEZA DAMM",
    ]


def test_payment_total_wins_over_the_vat_base_total():
    text = """MERCADONA S.A.
    25/06/2026 10:01
    PAN INTEGRAL 1,25
    TARJETA BANCARIA 81,04
    IVA BASE IMPONIBLE (€) CUOTA (€)
    4% 35,88 1,44
    10% 39,75 3,97
    TOTAL 75,63 5,41
    """

    receipt = parse_receipt_text(text)

    assert receipt.total == 81.04
    assert len(receipt.items) == 1
