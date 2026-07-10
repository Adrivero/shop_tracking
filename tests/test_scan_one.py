from app import scan_one


def test_scan_receipt_runs_ocr_and_returns_structured_data(tmp_path, monkeypatch):
    image_path = tmp_path / "receipt.jpeg"
    image_path.write_bytes(b"test image placeholder")

    ocr_text = """MERCADONA
    07/07/2026 09:42
    2 LECHE ENTERA 0,95 1,90
    1 MANZANAS
    0,500 kg 2,40 €/kg 1,20
    TOTAL 3,10
    """
    monkeypatch.setattr(scan_one, "extract_text_from_image", lambda path: ocr_text)

    receipt = scan_one.scan_receipt(image_path)

    assert receipt.receipt_date == "07/07/2026"
    assert receipt.receipt_time == "09:42"
    assert receipt.total == 3.10
    assert receipt.items[0].quantity == 2
    assert receipt.items[0].unit_price == 0.95
    assert receipt.items[0].price == 1.90
    assert receipt.items[1].weight_kg == 0.500
    assert receipt.items[1].price_per_kg == 2.40
    assert receipt.items[1].price == 1.20


def test_scan_receipt_rejects_a_missing_image(tmp_path):
    missing_image = tmp_path / "missing.jpeg"

    try:
        scan_one.scan_receipt(missing_image)
    except FileNotFoundError as error:
        assert str(missing_image) in str(error)
    else:
        raise AssertionError("Expected scan_receipt to reject a missing image")
