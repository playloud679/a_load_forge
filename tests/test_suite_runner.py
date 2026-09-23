"""Regression checks for test selection and bounded, lossless output."""

import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from suite_output import run_logged


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "tests/test_all.py"


def listed(*args):
    result = subprocess.run(
        [sys.executable, str(SUITE), "--list", *args],
        capture_output=True, text=True, cwd=ROOT,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return {line.strip() for line in result.stdout.splitlines() if line.startswith("  - ")}


class SuiteSelection(unittest.TestCase):
    def test_local_groups_partition_suite_and_include_misnamed_ui_tests(self):
        core, ui, all_local = listed("--fast"), listed("--ui"), listed()
        self.assertTrue(core)
        self.assertTrue(ui)
        self.assertFalse(core & ui)
        self.assertEqual(core | ui, all_local)
        for label in (
            "DCCAV FRD/ZMA exports", "Public project page renders",
            "Public project embed mode", "Admin can save Box Design",
            "Bass Match candidate pool starts open",
        ):
            self.assertTrue(any(label in item for item in ui), label)
            self.assertFalse(any(label in item for item in core), label)
        self.assertFalse(any("[CRAWLER]" in item for item in all_local))
        self.assertFalse(any("Heritage importer" in item for item in all_local))

    def test_apptests_and_external_imports_have_explicit_groups(self):
        tree = ast.parse(SUITE.read_text())
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "test"):
                continue
            function = functions.get(getattr(call.args[1], "id", ""))
            if function is None:
                continue
            group = next((kw.value.value for kw in call.keywords if kw.arg == "group"), "core")
            for node in ast.walk(function):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if (node.module or "").startswith("streamlit.testing"):
                    self.assertEqual(group, "ui", function.name)
                if node.module == "tools" and any(
                    not (ROOT / "tools" / f"{alias.name}.py").is_file() for alias in node.names
                ):
                    self.assertEqual(group, "crawler", function.name)
                if (node.module or "").startswith("services.crawler_agent"):
                    self.assertEqual(group, "crawler", function.name)

    def test_smoke_selection_covers_every_family(self):
        smoke = listed("--smoke")
        for family in ("DCCAV", "Bass reflex", "Passive radiator", "Sealed", "Infinite baffle",
                       "Bandpass 4th", "Bandpass 6th", "Bandpass 8th", "Transmission line",
                       "MLTL", "Quarter-wave", "Back-loaded horn", "Tapped horn"):
            self.assertTrue(any(family in item for item in smoke), family)

    def test_empty_selection_is_an_error(self):
        result = subprocess.run(
            [sys.executable, str(SUITE), "--list", "-m", "no-such-test-123456"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)

    def test_match_narrows_smoke_instead_of_adding_unrelated_tests(self):
        smoke = listed("--smoke", "-m", "DCCAV")
        self.assertEqual(len(smoke), 1)
        self.assertIn("Acoustic-load smoke: DCCAV", next(iter(smoke)))

    def test_conflicting_groups_are_rejected(self):
        result = subprocess.run(
            [sys.executable, str(SUITE), "--list", "--fast", "--ui"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)


class SuiteOutput(unittest.TestCase):
    def test_noisy_failure_keeps_log_and_exit_status_but_bounds_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            code = (
                "import sys; print('warning\\n' * 2000); "
                "print('  FAIL synthetic regression'); "
                "print('traceback detail', file=sys.stderr); "
                "print('  PASS: 0   FAIL: 1   SKIP: 0'); sys.exit(7)"
            )
            with redirect_stdout(output):
                status = run_logged([sys.executable, "-u", "-c", code], Path(directory))
            self.assertEqual(status, 7)
            self.assertLess(len(output.getvalue().splitlines()), 50)
            self.assertIn("FAIL synthetic regression", output.getvalue())
            self.assertIn("traceback detail", output.getvalue())
            log = next(Path(directory).glob("*.log")).read_text()
            self.assertEqual(log.count("warning"), 2000)
            self.assertIn("traceback detail", log)

    def test_success_reports_summary_and_uses_unique_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                output = io.StringIO()
                with redirect_stdout(output):
                    status = run_logged(
                        [sys.executable, "-c", "print('  PASS: 1   FAIL: 0   SKIP: 0')"],
                        Path(directory),
                    )
                self.assertEqual(status, 0)
                self.assertIn("PASS: 1", output.getvalue())
                self.assertEqual(len(output.getvalue().splitlines()), 3)
            self.assertEqual(len(list(Path(directory).glob("*.log"))), 2)


if __name__ == "__main__":
    unittest.main()
