from decimal import Decimal
from io import BytesIO

from app.analytics import dashboard_stats
from app.db import Base, ReceiptRepository, create_db_engine
from app.tools.parser import ParsedReceipt, ReceiptItem
from app.web import create_app


def sample_receipt() -> ParsedReceipt:
    return ParsedReceipt(
        store_name="LOCAL MARKET",
        receipt_date="08/07/2026",
        receipt_time="12:30",
        total=5.50,
        items=[
            ReceiptItem("COFFEE", quantity=1, unit_price=3.50, price=3.50),
            ReceiptItem("OAT MILK", quantity=2, unit_price=1.00, price=2.00),
        ],
    )


def make_engine(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'dashboard.db'}")
    Base.metadata.create_all(engine)
    return engine


def test_dashboard_statistics_aggregate_receipts_and_products(tmp_path):
    engine = make_engine(tmp_path)
    repository = ReceiptRepository(engine)
    second_receipt = sample_receipt()
    second_receipt.receipt_time = "12:45"

    repository.save_receipt(sample_receipt())
    repository.save_receipt(second_receipt)

    stats = dashboard_stats(engine)

    assert stats.receipt_count == 2
    assert stats.item_count == 4
    assert stats.unique_products == 2
    assert stats.total_spend == Decimal("11.00")
    assert stats.average_basket == Decimal("5.50")
    assert stats.products[0].name == "COFFEE"
    assert stats.products[0].spend == Decimal("7.00")
    assert stats.stores[0].receipts == 2


def test_dashboard_pages_render_with_saved_data(tmp_path):
    engine = make_engine(tmp_path)
    receipt = ReceiptRepository(engine).save_receipt(sample_receipt())
    client = create_app(engine).test_client()

    for path in (
        "/",
        "/products",
        "/receipts",
        f"/receipts/{receipt.id}",
        f"/receipts/{receipt.id}/edit",
        "/scan",
    ):
        response = client.get(path)
        assert response.status_code == 200, path

    assert b"LOCAL MARKET" in client.get("/").data
    assert b"COFFEE" in client.get("/products").data


def test_database_page_is_not_exposed(tmp_path):
    response = create_app(make_engine(tmp_path)).test_client().get("/database")

    assert response.status_code == 404


def test_shutdown_button_is_available_and_route_can_render_without_exiting(tmp_path):
    app = create_app(make_engine(tmp_path))
    app.config["SHUTDOWN_ON_REQUEST"] = False
    client = app.test_client()

    page = client.get("/")
    assert page.status_code == 200
    assert b"Stop app" in page.data

    response = client.post("/shutdown")
    assert response.status_code == 200
    assert b"Stopping the" in response.data


def test_shutdown_route_is_post_only(tmp_path):
    response = create_app(make_engine(tmp_path)).test_client().get("/shutdown")

    assert response.status_code == 405


def test_scan_upload_can_save_to_dashboard_database_and_raw_folder(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    scanned_paths = []

    def fake_scan(path):
        scanned_paths.append(path)
        assert path.is_file()
        return sample_receipt()

    monkeypatch.setattr("app.web.scan_receipt", fake_scan)
    client = create_app(engine).test_client()

    response = client.post(
        "/scan",
        data={"receipt": (BytesIO(b"image"), "receipt.jpg"), "save": "yes"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"Saved as receipt #1" in response.data
    assert ReceiptRepository(engine).count_receipts() == 1
    assert len(scanned_paths) == 1
    assert scanned_paths[0].parent == tmp_path / "raw"
    assert scanned_paths[0].suffix == ".jpg"
    assert scanned_paths[0].read_bytes() == b"image"


def test_bulk_scan_upload_saves_each_valid_receipt(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    scanned_paths = []

    def fake_scan(path):
        scanned_paths.append(path)
        receipt = sample_receipt()
        receipt.receipt_time = "12:30" if path.name.endswith("first.jpg") else "12:45"
        return receipt

    monkeypatch.setattr("app.web.scan_receipt", fake_scan)
    client = create_app(engine).test_client()

    response = client.post(
        "/scan",
        data={
            "receipt": [
                (BytesIO(b"first"), "first.jpg"),
                (BytesIO(b"second"), "second.jpg"),
            ],
            "save": "yes",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"Bulk scan complete" in response.data
    assert b"Saved #1" in response.data
    assert b"Saved #2" in response.data
    assert ReceiptRepository(engine).count_receipts() == 2
    assert len(scanned_paths) == 2
    assert {path.read_bytes() for path in scanned_paths} == {b"first", b"second"}


def test_bulk_scan_upload_reports_invalid_files_without_stopping_batch(
    tmp_path, monkeypatch
):
    engine = make_engine(tmp_path)
    monkeypatch.setattr("app.web.scan_receipt", lambda _path: sample_receipt())
    client = create_app(engine).test_client()

    response = client.post(
        "/scan",
        data={
            "receipt": [
                (BytesIO(b"image"), "receipt.jpg"),
                (BytesIO(b"text"), "notes.txt"),
            ],
            "save": "yes",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"receipt.jpg" in response.data
    assert b"notes.txt" in response.data
    assert b"Use a JPG" in response.data
    assert ReceiptRepository(engine).count_receipts() == 1


def test_scan_upload_rejects_unsupported_files(tmp_path):
    client = create_app(make_engine(tmp_path)).test_client()

    response = client.post(
        "/scan",
        data={"receipt": (BytesIO(b"text"), "receipt.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert b"Use a JPG" in response.data


def test_receipt_can_be_manually_edited(tmp_path):
    engine = make_engine(tmp_path)
    receipt_id = ReceiptRepository(engine).save_receipt(sample_receipt()).id
    client = create_app(engine).test_client()

    response = client.post(
        f"/receipts/{receipt_id}/edit",
        data={
            "store_name": "EDITED MARKET",
            "purchased_at": "2026-07-09T16:45",
            "total": "9.75",
            "item_name": ["TEA", "BREAD"],
            "item_quantity": ["1", "2"],
            "item_unit_price": ["4.25", "2.75"],
            "item_weight_kg": ["", ""],
            "item_price_per_kg": ["", ""],
            "item_line_total": ["4.25", "5.50"],
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/receipts/{receipt_id}?updated=1")
    updated = ReceiptRepository(engine).get_receipt(receipt_id)
    assert updated is not None
    assert updated.store_name == "EDITED MARKET"
    assert updated.total == Decimal("9.75")
    assert [item.product_name for item in updated.items] == ["TEA", "BREAD"]


def test_invalid_receipt_edit_preserves_existing_data(tmp_path):
    engine = make_engine(tmp_path)
    receipt_id = ReceiptRepository(engine).save_receipt(sample_receipt()).id
    client = create_app(engine).test_client()

    response = client.post(
        f"/receipts/{receipt_id}/edit",
        data={
            "store_name": "SHOULD NOT SAVE",
            "total": "not-money",
            "item_name": ["COFFEE"],
            "item_quantity": ["1"],
            "item_line_total": ["3.50"],
        },
    )

    assert response.status_code == 400
    assert b"Receipt total must be a valid number" in response.data
    assert ReceiptRepository(engine).get_receipt(receipt_id).store_name == "LOCAL MARKET"


def test_receipt_can_be_deleted_from_dashboard(tmp_path):
    engine = make_engine(tmp_path)
    receipt_id = ReceiptRepository(engine).save_receipt(sample_receipt()).id
    client = create_app(engine).test_client()

    response = client.post(f"/receipts/{receipt_id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/receipts?deleted=1")
    assert ReceiptRepository(engine).get_receipt(receipt_id) is None
    assert dashboard_stats(engine).receipt_count == 0
