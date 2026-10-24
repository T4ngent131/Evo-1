"""Rebuild the public, synthetic summary-page OCR smoke fixtures.

The images contain no player names, player IDs, or full game captures. They
reuse the repository's small summary-keyword reference template. Number
positions come from config/summary.json so a
config layout change also requires regenerating and reviewing these fixtures.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "summary.json"
SUMMARY_TEMPLATE = ROOT / "config" / "templates" / "summary.png"
OUT = ROOT / "tests" / "fixtures" / "public"
FONT = Path(r"C:\Windows\Fonts\arial.ttf")

SAMPLES = {
    "summary_normal.png": {"placement": "8", "squad_kills": "13", "kda": "3/0/3", "damage": "688",
                           "survival_time": "16:03", "revives": "2", "respawns": "0"},
    "summary_zero_two_digits.png": {"placement": "20", "squad_kills": "0", "kda": "0/10/0", "damage": "0",
                                     "survival_time": "09:05", "revives": "0", "respawns": "12"},
}


def font(size):
    if not FONT.is_file():
        raise RuntimeError(f"Arial is required to rebuild fixtures: {FONT}")
    return ImageFont.truetype(str(FONT), size=size)


def draw_value(draw, roi, value):
    x, y, width, height = roi
    size = max(24, int(height * 0.78))
    face = font(size)
    box = draw.textbbox((0, 0), value, font=face)
    text_w, text_h = box[2] - box[0], box[3] - box[1]
    draw.text((x + (width - text_w) // 2, y + (height - text_h) // 2 - box[1]), value, fill="black", font=face)


def make_image(fields, values):
    image = Image.new("RGB", (1920, 1080), "white")
    draw = ImageDraw.Draw(image)
    # Reuse the existing non-personal keyword crop; all numeric content is
    # drawn below. This is not a real-game accuracy fixture.
    title = Image.open(SUMMARY_TEMPLATE).convert("RGB")
    image.paste(title, ((image.width - title.width) // 2, 158))
    # Minimal non-game frame: light boxes make crop boundaries reviewable.
    for name, spec in fields.items():
        x, y, width, height = spec["roi"]
        draw.rectangle((x, y, x + width, y + height), outline="#b5b5b5", width=2)
        draw_value(draw, spec["roi"], values[name])
    return image


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for name, values in SAMPLES.items():
        make_image(cfg["fields"], values).save(OUT / name)
        print(f"wrote {OUT / name}")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
