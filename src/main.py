"""OCR synthetic referral documents and log only non-identifying routing evidence."""

import json
import re
from pathlib import Path
import matplotlib
import pytesseract
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def render(index: int) -> tuple[Image.Image, dict]:
    truth = {
        "referral": f"REF-{index:04d}",
        "patient": f"Synthetic Person {index}",
        "specialty": ["Cardiology", "Neurology", "Dermatology"][index % 3],
    }
    image = Image.new("RGB", (1000, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(
        str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 24
    )
    for j, line in enumerate(
        [
            "SYNTHETIC REFERRAL",
            f"Referral: {truth['referral']}",
            f"Patient: {truth['patient']}",
            f"Specialty: {truth['specialty']}",
            "Phone: 555-010-1234",
        ]
    ):
        draw.text((35, 25 + j * 75), line, font=font, fill="black")
    if index % 3 == 1:
        image = image.rotate(2, fillcolor="white")
    if index % 3 == 2:
        image = image.resize((500, 250)).resize((1000, 500)).filter(ImageFilter.GaussianBlur(1))
    return image, truth


def extract(image: Image.Image) -> tuple[dict, float]:
    data = pytesseract.image_to_data(image, config="--psm 6", output_type=pytesseract.Output.DICT)
    text = " ".join(data["text"])
    result = {}
    for key, pattern in {
        "referral": r"Referral:\s*(REF-\d{4})",
        "patient": r"Patient:\s*(Synthetic Person \d+)",
        "specialty": r"Specialty:\s*(Cardiology|Neurology|Dermatology)",
    }.items():
        match = re.search(pattern, text, re.I)
        result[key] = match.group(1) if match else None
    confidence = [
        float(c) for t, c in zip(data["text"], data["conf"]) if t.strip() and float(c) >= 0
    ]
    return result, sum(confidence) / len(confidence) if confidence else 0


def route(doc_id: int, fields: dict, confidence: float) -> dict:
    missing = [k for k, v in fields.items() if v is None]
    # Never log text or field values, including on parse failures.
    return {
        "document_id": doc_id,
        "missing_fields": missing,
        "confidence": confidence,
        "review_required": bool(missing) or confidence < 96,
    }


def benchmark() -> dict:
    rows = []
    logs = []
    folder = Path("evidence/documents")
    folder.mkdir(exist_ok=True)
    for i in range(24):
        image, truth = render(i)
        image.save(folder / f"{i}.png")
        fields, confidence = extract(image)
        rows.append({"id": i, "truth": truth, "extracted": fields})
        logs.append(route(i, fields, confidence))
    accuracies = {
        key: sum(r["truth"][key] == r["extracted"][key] for r in rows) / len(rows)
        for key in ["referral", "patient", "specialty"]
    }
    serialized = "".join(json.dumps(row) + "\n" for row in logs)
    Path("evidence/audit.jsonl").write_text(serialized)
    leak_count = sum(
        marker in serialized
        for marker in ["Synthetic Person", "555-010-1234", "REF-000", "Patient:"]
    )
    assert leak_count == 0
    Path("evidence/exception-queue.json").write_text(
        json.dumps([r for r in logs if r["review_required"]], indent=2)
    )
    Path("evidence/field-accuracy.json").write_text(json.dumps(accuracies, indent=2))
    Path("evidence/field-table.md").write_text(
        "| Field | Exact accuracy |\n|---|---|\n"
        + "".join(f"| {k} | {v} |\n" for k, v in accuracies.items())
    )
    return {
        "synthetic_referrals": len(rows),
        "referral_id_accuracy": accuracies["referral"],
        "patient_accuracy": accuracies["patient"],
        "specialty_accuracy": accuracies["specialty"],
        "exception_queue": sum(r["review_required"] for r in logs),
        "seeded_identifier_leaks_in_logs": leak_count,
    }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
