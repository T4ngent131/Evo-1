"""Behavior tests for strict runner and release evidence; never build/release."""

import importlib.util
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import run_all  # noqa: E402


class ReleaseGateTests(unittest.TestCase):
    def test_development_reports_skip_without_failing(self):
        ok, counts = run_all.run_tests({"private": "private"}, importer=lambda _: SimpleNamespace(main=lambda: None))
        self.assertTrue(ok)
        self.assertEqual(counts, {"pass": 0, "skip": 1, "fail": 0})

    def test_strict_fails_required_skip_and_exception(self):
        modules = {"private": "private", "broken": "broken"}
        def importer(name):
            if name == "private":
                return SimpleNamespace(main=lambda: None)
            return SimpleNamespace(main=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        ok, counts = run_all.run_tests(modules, strict=True, importer=importer)
        self.assertFalse(ok)
        self.assertEqual(counts, {"pass": 0, "skip": 1, "fail": 2})

    def test_strict_rejects_legends_and_teammates_skip(self):
        modules = {"legends": "legends", "teammates": "teammates"}
        ok, counts = run_all.run_tests(modules, strict=True, importer=lambda _: SimpleNamespace(main=lambda: None))
        self.assertFalse(ok)
        self.assertEqual(counts, {"pass": 0, "skip": 2, "fail": 2})

    def test_strict_rejects_partial_missing_capture(self):
        class FakeGame:
            def take_missing_shots(self):
                return (Path("private.png"),)
        with mock.patch.dict(sys.modules, {"fake_game": FakeGame()}):
            ok, counts = run_all.run_tests({"summary page": "partial"}, strict=True,
                                            importer=lambda _: SimpleNamespace(main=lambda: True))
        self.assertFalse(ok)
        self.assertEqual(counts, {"pass": 0, "skip": 1, "fail": 1})

    def test_file_requirement_passes_when_present_and_fails_when_missing(self):
        with TemporaryDirectory() as directory:
            label = Path(directory) / "replay_teammates.csv"
            label.write_text("private label", encoding="utf-8")
            requirements = {"replay": (("file", label),)}
            ok, counts = run_all.run_tests({"replay": "replay"}, strict=True,
                                            importer=lambda _: SimpleNamespace(main=lambda: True), requirements=requirements)
            self.assertTrue(ok)
            self.assertEqual(counts, {"pass": 1, "skip": 0, "fail": 0})
            label.unlink()
            ok, counts = run_all.run_tests({"replay": "replay"}, strict=True,
                                            importer=lambda _: SimpleNamespace(main=lambda: True), requirements=requirements)
            self.assertFalse(ok)
            self.assertEqual(counts, {"pass": 0, "skip": 1, "fail": 1})

    def test_release_self_check_requires_image(self):
        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location("release_under_test", ROOT / "tools" / "release.py")
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        with mock.patch.object(release, "CHECK_IMAGE", ROOT / "missing-release-evidence.png"):
            with self.assertRaises(release.Stop):
                release.self_check()

    def test_missing_image_stops_before_tests_and_build(self):
        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location("release_order_under_test", ROOT / "tools" / "release.py")
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        with mock.patch.object(release, "CHECK_IMAGE", ROOT / "missing-release-evidence.png"), \
                mock.patch.object(release, "check_clean", return_value=False), \
                mock.patch.object(release, "git", return_value="abc"), \
                mock.patch.object(release, "run_tests") as tests, \
                mock.patch.object(release.subprocess, "run") as build, \
                mock.patch.object(sys, "argv", ["release.py", "--allow-dirty"]):
            self.assertEqual(release.main(), 1)
        tests.assert_not_called()
        build.assert_not_called()

    def test_release_prints_success_summary_and_failure_output(self):
        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location("release_output_under_test", ROOT / "tools" / "release.py")
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        success = SimpleNamespace(returncode=0, stdout="detail\n===== results (1s): pass=2 skip=0 fail=0 =====\n", stderr="")
        with mock.patch.object(release.subprocess, "run", return_value=success), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            release.run_tests()
        self.assertIn("===== results", out.getvalue())
        failed = SimpleNamespace(returncode=1, stdout="failed suite summary", stderr="")
        with mock.patch.object(release.subprocess, "run", return_value=failed), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            with self.assertRaises(release.Stop):
                release.run_tests()
        self.assertIn("failed suite summary", out.getvalue())


def main():
    result = unittest.main(module=__name__, argv=[__name__], exit=False, verbosity=0).result
    return result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
