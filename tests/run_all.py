"""Run Evo's regression checks.

Development runs may skip private game captures, but ``--strict`` turns every
required skip into a release-blocking failure.
"""

import argparse
import importlib
import sys
import time
from pathlib import Path


TESTS = {
    "summary page": "test_summary_page", "public OCR smoke": "test_public_ocr",
    "lightweight": "test_light", "replay": "test_replay", "legends": "test_legends",
    "player name": "test_player_name", "accounts": "test_accounts", "teammates": "test_teammates",
    "screenshots": "test_screenshots", "ranks": "test_ranks", "source run": "test_source_run",
    "eliminated": "test_eliminated", "in match": "test_in_match", "recording reliability": "test_recording_reliability",
    "updater": "test_updater", "webview2": "test_webview2", "aspect": "test_aspect",
    "data move": "test_data_move", "legend icons": "test_legend_icons", "autostart": "test_autostart",
    "sounds": "test_sounds", "share": "test_share", "stats": "test_stats_page", "follow": "test_follow",
    "telemetry": "test_telemetry", "release gates": "test_release_gates",
}

ROOT = Path(__file__).resolve().parent.parent
# test_aspect predates MissingShots and checks these folders directly. Keep its
# absence structured here rather than inferring a skip from human output.
PRIVATE_CAPTURE_REQUIREMENTS = {
    "aspect": (("directory_nonempty", ROOT / "captures" / "aspect" / "16x10_20261020"),
               ("directory_nonempty", ROOT / "captures" / "aspect" / "4x3_20261020")),
    # test_replay can otherwise skip its private teammate-label comparison
    # while returning True after the screenshot assertions pass.
    "replay": (("file", ROOT / "tests" / "replay_20261016_teammates.csv"),),
}


def requirement_exists(kind, path):
    if kind == "file":
        return path.is_file()
    if kind == "directory_nonempty":
        return path.is_dir() and any(path.iterdir())
    raise ValueError(f"unknown private-fixture requirement kind: {kind}")


def run_tests(tests=TESTS, strict=False, importer=importlib.import_module, requirements=PRIVATE_CAPTURE_REQUIREMENTS):
    """Return ``(ok, counts)`` and print a pass/skip/fail report."""
    start, counts = time.perf_counter(), {"pass": 0, "skip": 0, "fail": 0}
    for name, module_name in tests.items():
        fake_game = sys.modules.get("fake_game")
        if fake_game is not None:
            fake_game.take_missing_shots()
        try:
            value = importer(module_name).main()
        except Exception as exc:  # a crashed check is never a pass
            counts["fail"] += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            continue
        fake_game = fake_game or sys.modules.get("fake_game")
        missing = fake_game.take_missing_shots() if fake_game is not None else ()
        missing += tuple(path for kind, path in requirements.get(name, ()) if not requirement_exists(kind, path))
        if missing and value is not False:
            value = None
            print(f"  evidence missing: {', '.join(str(path) for path in missing)}")
        if value is None:
            counts["skip"] += 1
            if strict:
                counts["fail"] += 1
                print(f"  FAIL  {name}: required evidence was skipped")
            else:
                print(f"  SKIP  {name}")
        elif value is False:
            counts["fail"] += 1
            print(f"  FAIL  {name}")
        else:
            counts["pass"] += 1
            print(f"  PASS  {name}")
    print(f"===== results ({time.perf_counter() - start:.0f}s): "
          f"pass={counts['pass']} skip={counts['skip']} fail={counts['fail']} =====")
    return counts["fail"] == 0, counts


def main(strict=False):
    return run_tests(strict=strict)[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="fail when required regression evidence is skipped")
    raise SystemExit(0 if main(parser.parse_args().strict) else 1)
