# Public synthetic OCR smoke fixtures

`summary_normal.png` and `summary_zero_two_digits.png` are generated locally by
`python tools/make_public_fixtures.py` from `config/summary.json` using Pillow.
They contain deliberately drawn numbers in the configured summary-field
regions and reuse the repository's small `config/templates/summary.png`
keyword reference crop. There is no full game capture, player name, player
ID, or other personal information. Their hand-written expected values are
in `labels.json`.

These are synthetic smoke samples only. They verify that the real crop and OCR
path can read a normal case plus zero/two-digit values. They do not replace
private real-game accuracy evidence or demonstrate real-game OCR accuracy.
