"""Tests for the runnable microphone capture HIL script."""

from __future__ import annotations

import ast
import importlib.util
from io import StringIO
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts" / "audio_service_hil.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("audio_service_hil", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AudioServiceHilScriptTests(unittest.TestCase):
    def test_script_imports_cleanly_without_vendor_libraries(self) -> None:
        module = load_script_module()

        self.assertTrue(hasattr(module, "main"))

    def test_script_has_no_vendor_imports_at_module_scope(self) -> None:
        tree = ast.parse(SCRIPT_PATH.read_text())
        imported: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        self.assertFalse({"pidog", "robot_hat", "vilib", "cv2", "sounddevice", "pyaudio"} & imported)

    def test_ci_main_runs_end_to_end_against_wav_fixture(self) -> None:
        module = load_script_module()
        output = StringIO()

        exit_code = module.main(["--ci"], out=output)

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertIn("Sparky audio HIL PASS", output.getvalue())
        self.assertIn("Step 1 PASS", output.getvalue())
        self.assertIn("Step 2 PASS", output.getvalue())
        self.assertIn("Step 3 PASS", output.getvalue())
        self.assertIn("Step 4 PASS", output.getvalue())
        self.assertIn("Step 5 PASS", output.getvalue())
        self.assertIn("Step 6 PASS", output.getvalue())
        self.assertIn("sample_rate=16000", output.getvalue())
        self.assertIn("channels=1", output.getvalue())
        self.assertIn("sample_width=2", output.getvalue())
        self.assertIn("chunk_count=3", output.getvalue())

    def test_simulated_run_reads_and_closes_microphone(self) -> None:
        module = load_script_module()
        robot = module.make_robot(simulate=True)

        result = module.run_check(robot, simulate=True, chunks=3, out=StringIO())
        shutdown = module.safe_shutdown(result.robot, result.service, out=StringIO())

        self.assertTrue(result.ok, result.message)
        self.assertTrue(shutdown.ok, shutdown.message)
        self.assertIsNotNone(robot.microphone)
        assert robot.microphone is not None
        self.assertEqual(robot.microphone.read_count, 3)
        self.assertFalse(robot.microphone.is_open())
        self.assertTrue(robot.closed)

    def test_missing_microphone_reports_failure_without_traceback(self) -> None:
        module = load_script_module()
        robot = module.make_robot(simulate=True)
        robot.microphone = None
        output = StringIO()

        result = module.run_check(robot, simulate=True, out=output)
        shutdown = module.safe_shutdown(result.robot, result.service, out=StringIO())

        self.assertFalse(result.ok)
        self.assertTrue(shutdown.ok, shutdown.message)
        self.assertIn("RuntimeError: robot ports do not include a microphone", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())


if __name__ == "__main__":
    unittest.main()
