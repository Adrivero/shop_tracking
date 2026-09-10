import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Keep `python app/scan_one.py` working as well as `python -m app.scan_one`.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Receipt, ReceiptRepository, create_db_engine
from app.tools.llm import LlmCorrection, LlmSettings, correct_receipt_with_llm
from app.tools.ocr import extract_text_candidates, extract_text_from_image
from app.tools.parser import ParsedReceipt, ReceiptItem, parse_receipt_text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE_PATH = PROJECT_ROOT / "data" / "raw" / "receipt_mercadona_01.jpeg"


@dataclass(frozen=True)
class ScanReceiptResult:
    receipt: ParsedReceipt
    llm: LlmCorrection


def _money_cents(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 100)


def _item_key(item: ReceiptItem) -> str:
    return " ".join(item.product_name.upper().split())


def _receipt_score(receipt: ParsedReceipt) -> float:
    score = 0.0
    score += 10 if receipt.store_name else 0
    score += 8 if receipt.receipt_date else 0
    score += 4 if receipt.receipt_time else 0
    score += 12 if receipt.total is not None else 0
    score += len(receipt.items) * 3
    total = _money_cents(receipt.total)
    item_sum = sum(_money_cents(item.price) or 0 for item in receipt.items)
    if total is not None and receipt.items:
        difference = abs(total - item_sum)
        if difference <= 2:
            score += 25
        elif difference <= 100:
            score += 8
        else:
            score -= min(difference / 100, 25)
    return score


def _choose_item_options(
    ordered_keys: list[str],
    options_by_key: dict[str, list[ReceiptItem]],
    target_total: int,
) -> list[ReceiptItem] | None:
    states: dict[int, list[ReceiptItem]] = {0: []}
    for key in ordered_keys:
        next_states: dict[int, list[ReceiptItem]] = {}
        for running_total, chosen_items in states.items():
            for item in options_by_key[key]:
                item_total = _money_cents(item.price)
                if item_total is None:
                    continue
                candidate_total = running_total + item_total
                if candidate_total > target_total:
                    continue
                next_states.setdefault(candidate_total, chosen_items + [item])
        states = next_states
        if not states:
            return None
    return states.get(target_total)


def _merge_receipts(candidates: list[ParsedReceipt]) -> ParsedReceipt:
    best = max(candidates, key=_receipt_score)
    target_total = _money_cents(best.total)
    if target_total is None or not best.items:
        return best

    ordered_keys: list[str] = []
    options_by_key: dict[str, list[ReceiptItem]] = {}
    seen_options: set[tuple[str, int]] = set()

    for item in best.items:
        key = _item_key(item)
        if key not in ordered_keys:
            ordered_keys.append(key)
            options_by_key[key] = []

    for receipt in candidates:
        for item in receipt.items:
            key = _item_key(item)
            item_total = _money_cents(item.price)
            if key not in options_by_key or item_total is None:
                continue
            if item_total <= 0 or item_total > target_total:
                continue
            option_key = (key, item_total)
            if option_key in seen_options:
                continue
            seen_options.add(option_key)
            options_by_key[key].append(item)

    if any(not options_by_key[key] for key in ordered_keys):
        return best

    exact_items = _choose_item_options(ordered_keys, options_by_key, target_total)
    if exact_items is None:
        return best

    return ParsedReceipt(
        store_name=best.store_name,
        receipt_date=best.receipt_date,
        receipt_time=best.receipt_time,
        total=best.total,
        items=exact_items,
    )


def _validate_receipt_totals(receipt: ParsedReceipt) -> None:
    total = _money_cents(receipt.total)
    if total is None or not receipt.items:
        return
    item_sum = sum(_money_cents(item.price) or 0 for item in receipt.items)
    if item_sum - total > 2:
        raise ValueError(
            "Could not read receipt reliably: product lines add up to "
            f"{item_sum / 100:.2f}, but the printed total is {total / 100:.2f}. "
            "Please retake the photo with the receipt flat, well lit, and fully visible."
        )


def scan_receipt_result(
    image_path: str | Path,
    *,
    use_llm: bool = False,
    llm_settings: LlmSettings | None = None,
) -> ScanReceiptResult:
    """Run OCR on an image and return receipt data plus scan metadata."""
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    try:
        raw_texts = extract_text_candidates(image_path)
    except ValueError:
        raw_texts = []
    if not raw_texts:
        raw_texts = [extract_text_from_image(image_path)]
    candidates = [parse_receipt_text(raw_text) for raw_text in raw_texts]
    receipt = _merge_receipts(candidates)
    _validate_receipt_totals(receipt)

    if use_llm:
        llm = correct_receipt_with_llm(raw_texts, receipt, settings=llm_settings)
        if llm.status == "applied":
            _validate_receipt_totals(llm.receipt)
        return ScanReceiptResult(receipt=llm.receipt, llm=llm)

    return ScanReceiptResult(
        receipt=receipt,
        llm=LlmCorrection(
            receipt=receipt,
            status="off",
            message="Local correction was not requested.",
        ),
    )


def scan_receipt(
    image_path: str | Path,
    *,
    use_llm: bool = False,
    llm_settings: LlmSettings | None = None,
) -> ParsedReceipt:
    """Run OCR on an image and return its database-ready receipt data."""
    return scan_receipt_result(
        image_path,
        use_llm=use_llm,
        llm_settings=llm_settings,
    ).receipt


def scan_and_save_receipt(
    image_path: str | Path, repository: ReceiptRepository
) -> Receipt:
    """Run the complete image -> OCR -> parser -> database pipeline."""
    return repository.save_receipt(scan_receipt(image_path))


def print_receipt(receipt: ParsedReceipt) -> None:
    print("=== PARSED RECEIPT ===")
    print("Store:", receipt.store_name)
    print("Date:", receipt.receipt_date)
    print("Time:", receipt.receipt_time)
    print("Total:", f"{receipt.total:.2f}" if receipt.total is not None else "unknown")

    print("\nItems:")
    for item in receipt.items:
        details = [f"quantity={item.quantity:g}"]
        if item.weight_kg is not None:
            details.append(f"weight={item.weight_kg:g} kg")
            details.append(f"price/kg={item.price_per_kg:.2f}")
        elif item.unit_price is not None:
            details.append(f"unit price={item.unit_price:.2f}")
        details.append(f"line total={item.price:.2f}")
        print(f"- {item.product_name}: {', '.join(details)}")


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Scan one shopping receipt")
    argument_parser.add_argument(
        "image", type=Path, nargs="?", default=DEFAULT_IMAGE_PATH
    )
    argument_parser.add_argument(
        "--save", action="store_true", help="Store the parsed receipt in the database"
    )
    arguments = argument_parser.parse_args()

    receipt = scan_receipt(arguments.image)
    print_receipt(receipt)
    if arguments.save:
        stored = ReceiptRepository(create_db_engine()).save_receipt(receipt)
        if getattr(stored, "was_duplicate", False):
            print(f"\nReceipt already saved with database ID {stored.id}")
        else:
            print(f"\nSaved receipt with database ID {stored.id}")


if __name__ == "__main__":
    main()
