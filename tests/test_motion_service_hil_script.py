"""Tests for the runnable motion-service HIL smoke-check script."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
import sys
import unittest

from src.device.sparky_device.hardware import HardwareError
from src.device.sparky_device.hardware.simulators import (
    SimulatedMotion,
    build_simulated_ports,
)


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts" / "motion_service_hil.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("motion_service_hil", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingSimulatedMotion(SimulatedMotion):
    def __init__(self) -> None:
        super().__init__()
        self.seen_actions: list[tuple[str, int, int]] = []

    def do_action(self, action: str, *, steps: int = 1, speed: int = 50) -> None:
        self.seen_actions.append((action, steps, speed))
        super().do_action(action, steps=steps, speed=speed)


class MotionServiceHilScriptTests(unittest.TestCase):
    def test_script_imports_cleanly_without_vendor_libraries(self) -> None:
        module = load_script_module()

        self.assertTrue(hasattr(module, "main"))

    def test_simulate_yes_main_runs_end_to_end(self) -> None:
        module = load_script_module()
        output = StringIO()

        exit_code = module.main(["--simulate", "--yes"], out=output)

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertIn("Motion service HIL smoke check PASS", output.getvalue())

    def test_expected_command_sequence_reaches_simulated_motion(self) -> None:
        module = load_script_module()
        robot = build_simulated_ports()
        recorder = RecordingSimulatedMotion()
        robot.motion = recorder

        result = module.run_check(robot, assume_yes=True, out=StringIO())
        module.safe_shutdown(robot, out=StringIO())

        self.assertTrue(result.ok, result.message)
        self.assertEqual(
            recorder.seen_actions,
            [("sit", 1, 50), ("stand", 1, 50), ("forward", 5, 30)],
        )
        self.assertEqual(recorder.stop_count, 3)
        self.assertTrue(recorder.closed)

    def test_safe_stop_and_close_fire_on_injected_exception(self) -> None:
        module = load_script_module()
        robot = build_simulated_ports()
        output = StringIO()

        def fail_after_stand(name, _motion, _robot):
            if name == "stand":
                raise HardwareError("injected failure")

        with self.assertRaisesRegex(HardwareError, "injected failure"):
            try:
                module.run_check(
                    robot,
                    assume_yes=True,
                    out=output,
                    after_step=fail_after_stand,
                )
            finally:
                module.safe_shutdown(robot, out=output)

        self.assertGreaterEqual(robot.motion.stop_count, 1)
        self.assertTrue(robot.motion.closed)


if __name__ == "__main__":
    unittest.main()
