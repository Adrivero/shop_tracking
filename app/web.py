"""Local-only web dashboard for Shop Tracking."""

import argparse
import os
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from flask import Flask, abort, redirect, render_template, request, url_for
from sqlalchemy import Engine
from sqlalchemy.engine import make_url
from werkzeug.utils import secure_filename

from app.analytics import dashboard_stats
from app.db.config import PROJECT_ROOT
from app.db import ReceiptRepository, create_db_engine
from app.scan_one import scan_receipt_result
from app.tools.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    llm_settings_from_form,
    load_llm_settings,
    save_llm_settings,
)
from app.tools.parser import ParsedReceipt, ReceiptItem as ParsedReceiptItem


ALLOWED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def _schedule_process_exit(delay_seconds: float = 0.35) -> None:
    timer = threading.Timer(delay_seconds, lambda: os._exit(0))
    timer.daemon = True
    timer.start()


def _optional_decimal(value: str, label: str) -> Decimal | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{label} must be a valid number.") from error


def _editor_data_from_form() -> dict[str, object]:
    names = request.form.getlist("item_name")
    quantities = request.form.getlist("item_quantity")
    unit_prices = request.form.getlist("item_unit_price")
    weights = request.form.getlist("item_weight_kg")
    kilogram_prices = request.form.getlist("item_price_per_kg")
    line_totals = request.form.getlist("item_line_total")
    size = max(
        map(
            len,
            (names, quantities, unit_prices, weights, kilogram_prices, line_totals),
        ),
        default=0,
    )

    def value(values: list[str], index: int) -> str:
        return values[index] if index < len(values) else ""

    return {
        "store_name": request.form.get("store_name", ""),
        "purchased_at": request.form.get("purchased_at", ""),
        "total": request.form.get("total", ""),
        "items": [
            {
                "product_name": value(names, index),
                "quantity": value(quantities, index),
                "unit_price": value(unit_prices, index),
                "weight_kg": value(weights, index),
                "price_per_kg": value(kilogram_prices, index),
                "line_total": value(line_totals, index),
            }
            for index in range(size)
        ],
    }


def _parsed_receipt_from_form() -> ParsedReceipt:
    editor = _editor_data_from_form()
    purchased_at_text = str(editor["purchased_at"]).strip()
    purchased_at = None
    if purchased_at_text:
        try:
            purchased_at = datetime.fromisoformat(purchased_at_text)
        except ValueError as error:
            raise ValueError("Purchase date and time are not valid.") from error

    items: list[ParsedReceiptItem] = []
    for index, values in enumerate(editor["items"], start=1):
        name = str(values["product_name"]).strip()
        row_has_data = any(str(value).strip() for value in values.values())
        if not row_has_data:
            continue
        if not name:
            raise ValueError(f"Product {index} needs a name.")
        quantity = _optional_decimal(str(values["quantity"]), f"Product {index} quantity")
        line_total = _optional_decimal(str(values["line_total"]), f"Product {index} total")
        if quantity is None or quantity <= 0:
            raise ValueError(f"Product {index} quantity must be greater than zero.")
        if line_total is None:
            raise ValueError(f"Product {index} needs a line total.")
        items.append(
            ParsedReceiptItem(
                product_name=name,
                quantity=quantity,
                unit_price=_optional_decimal(
                    str(values["unit_price"]), f"Product {index} unit price"
                ),
                weight_kg=_optional_decimal(
                    str(values["weight_kg"]), f"Product {index} weight"
                ),
                price_per_kg=_optional_decimal(
                    str(values["price_per_kg"]), f"Product {index} price per kg"
                ),
                price=line_total,
            )
        )
    if not items:
        raise ValueError("Keep at least one product, or delete the entire receipt.")

    return ParsedReceipt(
        store_name=str(editor["store_name"]).strip() or None,
        receipt_date=purchased_at.strftime("%d/%m/%Y") if purchased_at else None,
        receipt_time=purchased_at.strftime("%H:%M:%S") if purchased_at else None,
        total=_optional_decimal(str(editor["total"]), "Receipt total"),
        items=items,
    )


def _default_receipt_image_dir(engine: Engine) -> Path:
    url = make_url(str(engine.url))
    if url.get_backend_name() == "sqlite" and url.database not in (None, ":memory:"):
        return Path(url.database).expanduser().resolve().parent / "raw"
    return PROJECT_ROOT / "data" / "raw"


def _default_llm_settings_path(engine: Engine) -> Path:
    url = make_url(str(engine.url))
    if url.get_backend_name() == "sqlite" and url.database not in (None, ":memory:"):
        return Path(url.database).expanduser().resolve().parent / "llm_settings.json"
    return PROJECT_ROOT / "data" / "llm_settings.json"


def _saved_upload_path(directory: Path, original_filename: str) -> Path:
    safe_name = secure_filename(original_filename)
    suffix = Path(safe_name).suffix.lower()
    stem = Path(safe_name).stem or "receipt"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    candidate = directory / f"{timestamp}-{stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{timestamp}-{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def _scan_upload(
    upload,
    image_directory: Path,
    *,
    save: bool,
    use_llm: bool,
    llm_settings,
    engine: Engine,
) -> dict[str, Any]:
    filename = secure_filename(upload.filename or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_TYPES:
        return {
            "filename": upload.filename or "Unnamed file",
            "error": "Use a JPG, PNG, WEBP, or TIFF image.",
        }

    image_path = _saved_upload_path(image_directory, filename)
    upload.save(image_path)
    scan_result = scan_receipt_result(
        image_path,
        use_llm=use_llm,
        llm_settings=llm_settings,
    )
    parsed = scan_result.receipt
    repository = ReceiptRepository(engine)
    duplicate_match = repository.find_by_date_and_total(parsed)
    saved = None
    if save and duplicate_match is not None:
        duplicate_match.was_duplicate = True
        saved = duplicate_match
    elif save:
        saved = repository.save_receipt(parsed)
        if getattr(saved, "was_duplicate", False):
            duplicate_match = saved
    return {
        "filename": filename,
        "archived_filename": image_path.name,
        "parsed": parsed,
        "saved": saved,
        "duplicate_match": duplicate_match,
        "llm": scan_result.llm,
        "error": None,
    }


def create_app(engine: Engine | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="gui/templates",
        static_folder="gui/static",
    )
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
    app.config["ENGINE"] = engine or create_db_engine()
    app.config["RECEIPT_IMAGE_DIR"] = _default_receipt_image_dir(app.config["ENGINE"])
    app.config["LLM_SETTINGS_PATH"] = _default_llm_settings_path(app.config["ENGINE"])

    def current_llm_settings():
        return load_llm_settings(app.config["LLM_SETTINGS_PATH"])

    def llm_control_state() -> dict[str, object]:
        settings = current_llm_settings()
        return {
            "configured": settings.configured,
            "enabled_by_default": settings.enabled_by_default and settings.configured,
            "model": settings.model,
            "base_url": settings.base_url,
            "timeout_seconds": settings.timeout_seconds,
        }

    @app.template_filter("currency")
    def format_currency(value: Decimal | float | None) -> str:
        return f"{value or 0:,.2f} €"

    @app.template_filter("quantity")
    def format_quantity(value: Decimal | float | None) -> str:
        if value is None:
            return "—"
        return f"{value:,.3f}".rstrip("0").rstrip(".")

    @app.template_filter("filesize")
    def format_filesize(value: int | None) -> str:
        if value is None:
            return "Not created yet"
        units = ("B", "KB", "MB", "GB")
        size = float(value)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    @app.get("/")
    def overview():
        stats = dashboard_stats(app.config["ENGINE"])
        peak = max((point.spend for point in stats.trend), default=Decimal("0"))
        return render_template("overview.html", stats=stats, trend_peak=peak)

    @app.get("/products")
    def products():
        stats = dashboard_stats(app.config["ENGINE"])
        query = request.args.get("q", "").strip()
        sort = request.args.get("sort", "spend")
        rows = stats.products
        if query:
            rows = [row for row in rows if query.casefold() in row.name.casefold()]
        sorters = {
            "spend": lambda row: row.spend,
            "purchases": lambda row: row.purchases,
            "quantity": lambda row: row.quantity,
            "recent": lambda row: row.latest_purchase or datetime.min,
            "name": lambda row: row.name.casefold(),
        }
        rows = sorted(rows, key=sorters.get(sort, sorters["spend"]), reverse=sort != "name")
        return render_template(
            "products.html", stats=stats, products=rows, query=query, sort=sort
        )

    @app.get("/receipts")
    def receipts():
        stats = dashboard_stats(app.config["ENGINE"])
        rows = ReceiptRepository(app.config["ENGINE"]).list_receipts(limit=1000)
        return render_template("receipts.html", stats=stats, receipts=rows)

    @app.get("/receipts/<int:receipt_id>")
    def receipt_detail(receipt_id: int):
        receipt = ReceiptRepository(app.config["ENGINE"]).get_receipt(receipt_id)
        if receipt is None:
            abort(404)
        return render_template(
            "receipt_detail.html",
            receipt=receipt,
            updated=request.args.get("updated") == "1",
        )

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "GET":
            saved = request.args.get("saved") == "1"
            current_settings = current_llm_settings()
            if not current_settings.configured:
                current_settings = llm_settings_from_form(
                    enabled_by_default=current_settings.enabled_by_default,
                    model=DEFAULT_MODEL,
                    base_url=current_settings.base_url or DEFAULT_BASE_URL,
                    timeout_seconds=str(current_settings.timeout_seconds),
                )
            return render_template(
                "settings.html",
                settings=current_settings,
                saved=saved,
            )

        try:
            updated_settings = llm_settings_from_form(
                enabled_by_default=request.form.get("llm_enabled") == "yes",
                model=request.form.get("llm_model", ""),
                base_url=request.form.get("llm_base_url", ""),
                timeout_seconds=request.form.get("llm_timeout_seconds", "20"),
            )
            save_llm_settings(app.config["LLM_SETTINGS_PATH"], updated_settings)
        except (OSError, ValueError) as error:
            return render_template(
                "settings.html",
                settings=current_llm_settings(),
                error=str(error),
            ), 400
        return redirect(url_for("settings", saved="1"))

    @app.route("/receipts/<int:receipt_id>/edit", methods=["GET", "POST"])
    def receipt_edit(receipt_id: int):
        repository = ReceiptRepository(app.config["ENGINE"])
        receipt = repository.get_receipt(receipt_id)
        if receipt is None:
            abort(404)

        if request.method == "GET":
            editor = {
                "store_name": receipt.store_name or "",
                "purchased_at": receipt.purchased_at.strftime("%Y-%m-%dT%H:%M")
                if receipt.purchased_at
                else "",
                "total": receipt.total if receipt.total is not None else "",
                "items": receipt.items,
            }
            return render_template("receipt_edit.html", receipt=receipt, editor=editor)

        editor = _editor_data_from_form()
        try:
            parsed = _parsed_receipt_from_form()
            if not repository.update_receipt(receipt_id, parsed):
                abort(404)
        except ValueError as error:
            return render_template(
                "receipt_edit.html", receipt=receipt, editor=editor, error=str(error)
            ), 400
        return redirect(url_for("receipt_detail", receipt_id=receipt_id, updated="1"))

    @app.post("/receipts/<int:receipt_id>/delete")
    def receipt_delete(receipt_id: int):
        if not ReceiptRepository(app.config["ENGINE"]).delete_receipt(receipt_id):
            abort(404)
        return redirect(url_for("receipts", deleted="1"))

    @app.post("/shutdown")
    def shutdown():
        if app.config.get("SHUTDOWN_ON_REQUEST", True):
            _schedule_process_exit()
        return render_template("shutdown.html")

    @app.route("/scan", methods=["GET", "POST"])
    def scan():
        if request.method == "GET":
            return render_template("scan.html", llm=llm_control_state())

        uploads = [
            upload
            for upload in request.files.getlist("receipt")
            if upload is not None and upload.filename
        ]
        if not uploads:
            return render_template(
                "scan.html",
                error="Choose at least one receipt image first.",
                llm=llm_control_state(),
            ), 400

        image_directory = Path(app.config["RECEIPT_IMAGE_DIR"])
        image_directory.mkdir(parents=True, exist_ok=True)
        save = request.form.get("save") == "yes"
        llm_settings = current_llm_settings()
        use_llm = request.form.get("use_llm") == "yes" and llm_settings.configured
        results = []
        all_unsupported = True
        try:
            for upload in uploads:
                try:
                    result = _scan_upload(
                        upload,
                        image_directory,
                        save=save,
                        use_llm=use_llm,
                        llm_settings=llm_settings,
                        engine=app.config["ENGINE"],
                    )
                    all_unsupported = all_unsupported and bool(result["error"])
                except (OSError, ValueError, RuntimeError) as error:
                    result = {
                        "filename": secure_filename(upload.filename or "") or "Unnamed file",
                        "error": str(error),
                    }
                    all_unsupported = False
                results.append(result)

            if len(results) == 1:
                result = results[0]
                if result["error"]:
                    status = 400 if all_unsupported else 422
                    return render_template("scan.html", error=result["error"]), status
                return render_template(
                    "scan_result.html",
                    parsed=result["parsed"],
                    saved=result["saved"],
                    duplicate_match=result["duplicate_match"],
                    filename=result["filename"],
                    archived_filename=result["archived_filename"],
                    llm=result["llm"],
                )

            return render_template("scan_bulk_result.html", results=results, save=save)
        except (OSError, ValueError, RuntimeError) as error:
            return render_template(
                "scan.html", error=str(error), llm=llm_control_state()
            ), 422

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    arguments = parser.parse_args()
    create_app().run(host=arguments.host, port=arguments.port, debug=False)


if __name__ == "__main__":
    main()
