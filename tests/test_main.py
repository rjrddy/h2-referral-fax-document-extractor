import json
from main import extract, render, route


def test_clean_document_real_ocr():
    image, truth = render(0)
    fields, _ = extract(image)
    assert fields == truth


def test_failure_logging_never_includes_field_values():
    fields = {"referral": None, "patient": "SEED-PHI-DO-NOT-LOG", "specialty": "SECRET"}
    event = route(42, fields, 20)
    serialized = json.dumps(event)
    assert event["review_required"] and "patient" not in event["missing_fields"]
    assert "SEED-PHI" not in serialized and "SECRET" not in serialized
