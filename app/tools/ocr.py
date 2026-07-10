from pathlib import Path

import cv2
import pytesseract


PAYMENT_MARKERS = ("total", "tarjeta", "bancaria", "bancarta", "importe")
OCR_CONFIG = "--psm 6 -c preserve_interword_spaces=1"


def preprocess_image(image_path: str | Path):
    image = cv2.imread(str(image_path))

    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    thresholded = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )[1]

    denoised = cv2.medianBlur(thresholded, 3)

    return denoised


def _receipt_crop(gray_image):
    height, width = gray_image.shape
    if height < 600 or width < 400:
        return gray_image
    return gray_image[
        int(height * 0.12) : int(height * 0.92),
        int(width * 0.12) : int(width * 0.88),
    ]


def _ocr_text(image, *, config: str = OCR_CONFIG) -> str:
    return pytesseract.image_to_string(image, config=config)


def _score_text(text: str) -> tuple[int, int]:
    upper_text = text.upper()
    score = 0
    score += 10 if "MERCADONA" in upper_text or "ALIMERKA" in upper_text else 0
    score += 8 if "TOTAL" in upper_text else 0
    score += 5 if "TARJETA" in upper_text or "BANCARIA" in upper_text else 0
    score += 2 * len([line for line in text.splitlines() if any(char.isdigit() for char in line)])
    score += upper_text.count(" EMPANADA ")
    score += upper_text.count(" COLA ")
    score += upper_text.count(" STICK ")
    return score, len(text)


def _unique_texts(texts: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for text in texts:
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(text)
    return unique


def extract_text_candidates(image_path: str | Path) -> list[str]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    processed_image = preprocess_image(image_path)
    crop = _receipt_crop(gray)
    crop_upscaled = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    crop_otsu = cv2.threshold(
        crop_upscaled,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )[1]

    texts = [
        _ocr_text(processed_image),
        _ocr_text(gray),
        _ocr_text(crop, config="--psm 4 -c preserve_interword_spaces=1"),
        _ocr_text(crop),
        _ocr_text(crop_otsu),
    ]

    # Bold totals can lose digits under global thresholding. A second grayscale
    # pass over the lower payment area preserves those heavy characters. Only
    # payment-related lines are appended, avoiding duplicate product rows.
    height = image.shape[0]
    payment_area = image[int(height * 0.68) : int(height * 0.88)]
    payment_gray = cv2.cvtColor(payment_area, cv2.COLOR_BGR2GRAY)
    payment_text = pytesseract.image_to_string(payment_gray, config="--psm 6")
    payment_lines = [
        line.strip()
        for line in payment_text.splitlines()
        if any(marker in line.lower() for marker in PAYMENT_MARKERS)
    ]

    if payment_lines:
        texts = [f"{text}\n" + "\n".join(payment_lines) for text in texts]

    return _unique_texts(texts)


def extract_text_from_image(image_path: str | Path) -> str:
    candidates = extract_text_candidates(image_path)
    if not candidates:
        return ""

    return max(candidates, key=_score_text)
