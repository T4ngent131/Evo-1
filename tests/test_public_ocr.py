"""Public synthetic summary-page smoke test using the production OCR path."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

from ocr import SMALL_CROP_PARAMS, create_engine, load_config, load_image  # noqa: E402
from summary_page import read_summary  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "public"


def main():
    labels = json.loads((FIXTURES / "labels.json").read_text(encoding="utf-8"))
    missing = [name for name in labels if not (FIXTURES / name).is_file()]
    if missing:
        print(f"  FAIL  public fixture files missing: {', '.join(missing)}")
        return False
    engine, cfg = create_engine(SMALL_CROP_PARAMS), load_config("summary.json")
    checks = {}
    for name, expected in labels.items():
        results, problems = read_summary(engine, load_image(FIXTURES / name), cfg)
        actual = {field: result["value"] for field, result in results.items()}
        expected = {field: tuple(value) if field == "kda" else value for field, value in expected.items()}
        checks[name] = actual == expected and not problems
        print(f"  {'PASS' if checks[name] else 'FAIL'}  {name}: {actual}")
    # The production parser must not turn an empty canvas into valid values.
    blank, blank_problems = read_summary(engine, np.full((1080, 1920, 3), 255, np.uint8), cfg)
    blank_values = [result["value"] for result in blank.values()]
    checks["blank rejects values"] = not any(value is not None for value in blank_values) and bool(blank_problems)
    print(f"  {'PASS' if checks['blank rejects values'] else 'FAIL'}  blank rejects values")
    return all(checks.values())


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
