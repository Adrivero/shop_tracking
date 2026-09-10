from app.tools import llm
from app.tools.llm import LlmSettings, correct_receipt_with_llm
from app.tools.parser import ParsedReceipt, ReceiptItem


def sample_receipt() -> ParsedReceipt:
    return ParsedReceipt(
        store_name="MERCADONA",
        receipt_date="17/07/2026",
        receipt_time="19:03",
        total=1.50,
        items=[
            ReceiptItem(
                product_name="C0CA C0LA",
                quantity=1,
                unit_price=1.50,
                price=1.50,
            )
        ],
    )


def configured_settings() -> LlmSettings:
    return LlmSettings(
        enabled_by_default=False,
        model="llama3.2:1b",
        base_url="http://example.test",
        timeout_seconds=1,
    )


def test_llm_correction_is_unavailable_without_a_model():
    correction = correct_receipt_with_llm(
        ["COCA COLA 1,50"],
        sample_receipt(),
        settings=LlmSettings(False, None, "http://example.test", 1),
    )

    assert correction.status == "unavailable"
    assert correction.receipt == sample_receipt()


def test_llm_correction_accepts_grounded_json(monkeypatch):
    def fake_generate(_settings, _payload):
        return """
        {
          "store_name": "MERCADONA",
          "receipt_date": "17/07/2026",
          "receipt_time": "19:03",
          "total": 1.50,
          "items": [
            {
              "product_name": "COCA COLA",
              "quantity": 1,
              "unit_price": 1.50,
              "weight_kg": null,
              "price_per_kg": null,
              "price": 1.50
            }
          ]
        }
        """

    monkeypatch.setattr(llm, "_ollama_generate", fake_generate)

    correction = correct_receipt_with_llm(
        ["MERCADONA\n17/07/2026 19:03\nCOCA COLA 1,50\nTOTAL 1,50"],
        sample_receipt(),
        settings=configured_settings(),
    )

    assert correction.status == "applied"
    assert correction.receipt.items[0].product_name == "COCA COLA"


def test_llm_correction_rejects_unsupported_products(monkeypatch):
    def fake_generate(_settings, _payload):
        return """
        {
          "store_name": "MERCADONA",
          "receipt_date": "17/07/2026",
          "receipt_time": "19:03",
          "total": 9.99,
          "items": [
            {
              "product_name": "SAFFRON",
              "quantity": 1,
              "unit_price": 9.99,
              "weight_kg": null,
              "price_per_kg": null,
              "price": 9.99
            }
          ]
        }
        """

    monkeypatch.setattr(llm, "_ollama_generate", fake_generate)

    correction = correct_receipt_with_llm(
        ["MERCADONA\n17/07/2026 19:03\nCOCA COLA 1,50\nTOTAL 1,50"],
        sample_receipt(),
        settings=configured_settings(),
    )

    assert correction.status == "rejected"
    assert correction.receipt == sample_receipt()
