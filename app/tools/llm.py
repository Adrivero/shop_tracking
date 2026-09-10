import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.tools.parser import ParsedReceipt, ReceiptItem


DEFAULT_BASE_URL = "http://host.docker.internal:11434"
DEFAULT_MODEL = "llama3.1:8b"


@dataclass(frozen=True)
class LlmSettings:
    enabled_by_default: bool
    model: str | None
    base_url: str
    timeout_seconds: float

    @property
    def configured(self) -> bool:
        return bool(self.model)


@dataclass(frozen=True)
class LlmCorrection:
    receipt: ParsedReceipt
    status: str
    message: str


def llm_settings_from_env() -> LlmSettings:
    timeout_text = os.environ.get("OCR_LLM_TIMEOUT_SECONDS", "20")
    try:
        timeout_seconds = float(timeout_text)
    except ValueError:
        timeout_seconds = 20.0

    return LlmSettings(
        enabled_by_default=os.environ.get("OCR_LLM_ENABLED", "").lower()
        in {"1", "true", "yes", "on"},
        model=(os.environ.get("OCR_LLM_MODEL") or "").strip() or None,
        base_url=(os.environ.get("OCR_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        timeout_seconds=max(1.0, timeout_seconds),
    )


def load_llm_settings(path: str | Path | None = None) -> LlmSettings:
    settings = llm_settings_from_env()
    if path is None:
        return settings

    settings_path = Path(path)
    if not settings_path.exists():
        return settings

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings

    return _settings_from_mapping(data, defaults=settings)


def save_llm_settings(path: str | Path, settings: LlmSettings) -> None:
    _validate_settings(settings)
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "enabled_by_default": settings.enabled_by_default,
                "model": settings.model,
                "base_url": settings.base_url,
                "timeout_seconds": settings.timeout_seconds,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def llm_settings_from_form(
    *,
    enabled_by_default: bool,
    model: str,
    base_url: str,
    timeout_seconds: str,
) -> LlmSettings:
    model_value = model.strip() or None
    base_url_value = (base_url.strip() or DEFAULT_BASE_URL).rstrip("/")
    try:
        timeout_value = float(timeout_seconds)
    except ValueError as error:
        raise ValueError("Timeout must be a valid number of seconds.") from error

    settings = LlmSettings(
        enabled_by_default=enabled_by_default,
        model=model_value,
        base_url=base_url_value,
        timeout_seconds=timeout_value,
    )
    _validate_settings(settings)
    return settings


def _settings_from_mapping(data: dict[str, Any], *, defaults: LlmSettings) -> LlmSettings:
    return LlmSettings(
        enabled_by_default=bool(
            data.get("enabled_by_default", defaults.enabled_by_default)
        ),
        model=_optional_string(data.get("model", defaults.model)),
        base_url=_optional_string(data.get("base_url", defaults.base_url))
        or DEFAULT_BASE_URL,
        timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
    )


def _validate_settings(settings: LlmSettings) -> None:
    parsed_url = urlparse(settings.base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("Base URL must be a valid HTTP or HTTPS URL.")
    if settings.timeout_seconds < 1 or settings.timeout_seconds > 120:
        raise ValueError("Timeout must be between 1 and 120 seconds.")


def correct_receipt_with_llm(
    raw_texts: list[str],
    parsed: ParsedReceipt,
    *,
    settings: LlmSettings | None = None,
) -> LlmCorrection:
    settings = settings or llm_settings_from_env()
    if not settings.configured:
        return LlmCorrection(
            receipt=parsed,
            status="unavailable",
            message="Set OCR_LLM_MODEL to enable local corrections.",
        )

    prompt = _build_prompt(raw_texts, parsed)
    payload = {
        "model": settings.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    try:
        response_text = _ollama_generate(settings, payload)
        candidate = _parsed_receipt_from_json(response_text)
        _validate_candidate(candidate, raw_texts)
    except (OSError, ValueError, urllib.error.URLError) as error:
        return LlmCorrection(
            receipt=parsed,
            status="rejected",
            message=f"Local correction was not applied: {error}",
        )

    return LlmCorrection(
        receipt=candidate,
        status="applied",
        message=f"Corrected with {settings.model}.",
    )


def _build_prompt(raw_texts: list[str], parsed: ParsedReceipt) -> str:
    candidates = "\n\n--- OCR CANDIDATE ---\n\n".join(
        text[:5000] for text in raw_texts[:5]
    )
    return (
        "You correct OCR output from Spanish supermarket receipts.\n"
        "Return only JSON with this schema: "
        '{"store_name": string|null, "receipt_date": "DD/MM/YYYY"|null, '
        '"receipt_time": "HH:MM"|"HH:MM:SS"|null, "total": number|null, '
        '"items": [{"product_name": string, "quantity": number, '
        '"unit_price": number|null, "weight_kg": number|null, '
        '"price_per_kg": number|null, "price": number}]}.\n'
        "Use only values supported by the OCR text. Do not add products that are "
        "not visible. Preserve the printed total when it is clear. Product line "
        "prices must add up to the receipt total when the receipt is complete.\n\n"
        f"DETERMINISTIC_PARSE:\n{json.dumps(asdict(parsed), ensure_ascii=False)}\n\n"
        f"OCR_TEXTS:\n{candidates}"
    )


def _ollama_generate(settings: LlmSettings, payload: dict[str, Any]) -> str:
    request = urllib.request.Request(
        f"{settings.base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8"))
    response_text = body.get("response")
    if not isinstance(response_text, str):
        raise ValueError("Ollama response did not include JSON text.")
    return response_text


def _parsed_receipt_from_json(value: str) -> ParsedReceipt:
    data = _json_object(value)
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("corrected receipt did not include item rows")

    parsed_items = [
        _receipt_item_from_dict(item, index) for index, item in enumerate(items, 1)
    ]
    return ParsedReceipt(
        store_name=_optional_string(data.get("store_name")),
        receipt_date=_optional_string(data.get("receipt_date")),
        receipt_time=_optional_string(data.get("receipt_time")),
        total=_optional_float(data.get("total")),
        items=parsed_items,
    )


def _json_object(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if match is None:
            raise ValueError("model did not return JSON") from None
        data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("model returned JSON that is not an object")
    return data


def _receipt_item_from_dict(data: Any, index: int) -> ReceiptItem:
    if not isinstance(data, dict):
        raise ValueError(f"item {index} is not an object")
    name = _optional_string(data.get("product_name"))
    if not name:
        raise ValueError(f"item {index} did not include a product name")
    quantity = _required_float(data.get("quantity"), f"item {index} quantity")
    price = _required_float(data.get("price"), f"item {index} price")
    return ReceiptItem(
        product_name=name,
        quantity=quantity,
        unit_price=_optional_float(data.get("unit_price")),
        weight_kg=_optional_float(data.get("weight_kg")),
        price_per_kg=_optional_float(data.get("price_per_kg")),
        price=price,
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _required_float(value, "numeric value")


def _required_float(value: Any, label: str) -> float:
    try:
        number = Decimal(str(value).replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    return float(number)


def _validate_candidate(receipt: ParsedReceipt, raw_texts: list[str]) -> None:
    if receipt.receipt_date:
        _validate_date(receipt.receipt_date)
    if receipt.receipt_time:
        _validate_time(receipt.receipt_time)
    if receipt.total is not None and receipt.total < 0:
        raise ValueError("receipt total cannot be negative")
    if not receipt.items:
        raise ValueError("corrected receipt has no products")

    ocr_words = _normalized_words("\n".join(raw_texts))
    for item in receipt.items:
        if item.quantity <= 0:
            raise ValueError(f"{item.product_name} has an invalid quantity")
        if item.price < 0:
            raise ValueError(f"{item.product_name} has a negative price")
        if not _has_ocr_overlap(item.product_name, ocr_words):
            raise ValueError(f"{item.product_name} is not supported by the OCR text")

    if receipt.total is not None:
        item_sum = sum(item.price for item in receipt.items)
        if abs(item_sum - receipt.total) > 0.05:
            raise ValueError("corrected item total does not match the receipt total")


def _validate_date(value: str) -> None:
    for date_format in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            datetime.strptime(value, date_format)
            return
        except ValueError:
            continue
    raise ValueError("corrected date is not valid")


def _validate_time(value: str) -> None:
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            datetime.strptime(value, time_format)
            return
        except ValueError:
            continue
    raise ValueError("corrected time is not valid")


def _normalized_words(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[A-Z0-9]{3,}", value.upper())
        if len(word) >= 3
    }


def _has_ocr_overlap(product_name: str, ocr_words: set[str]) -> bool:
    words = _normalized_words(product_name)
    if not words:
        return False
    return bool(words & ocr_words)
