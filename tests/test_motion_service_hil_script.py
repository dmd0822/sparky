"""Tests for the runnable full HIL checklist script."""

from __future__ import annotations

import ast
import importlib.util
from io import StringIO
from pathlib import Path
import sys
import unittest

<<<<<<< HEAD
from src.device.sparky_device.hardware import HardwareError
=======
from src.device.sparky_device.hardware import HardwareError, TouchState
>>>>>>> main
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
        self.seen_head_moves: list[tuple[float, float, float, int]] = []

    def do_action(self, action: str, *, steps: int = 1, speed: int = 50) -> None:
        self.seen_actions.append((action, steps, speed))
        super().do_action(action, steps=steps, speed=speed)

    def move_head(
        self,
        *,
        yaw: float = 0.0,
        roll: float = 0.0,
        pitch: float = 0.0,
        speed: int = 50,
    ) -> None:
        self.seen_head_moves.append((yaw, roll, pitch, speed))
        super().move_head(yaw=yaw, roll=roll, pitch=pitch, speed=speed)


class MotionServiceHilScriptTests(unittest.TestCase):
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

        self.assertFalse({"pidog", "robot_hat", "vilib", "cv2"} & imported)

    def test_simulate_yes_main_runs_end_to_end(self) -> None:
        module = load_script_module()
        output = StringIO()

        exit_code = module.main(["--ci"], out=output)

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertIn("Sparky HIL checklist PASS", output.getvalue())
        self.assertIn("Step 1 SKIP", output.getvalue())
        self.assertIn("Step 12 PASS", output.getvalue())
        self.assertIn("Step 17 PASS", output.getvalue())
        self.assertIn("Step 18 PASS", output.getvalue())

    def test_full_simulated_run_touches_motion_sensors_board_and_camera(self) -> None:
        module = load_script_module()
        robot = build_simulated_ports()
        module._prime_simulated_inputs(robot)
        recorder = RecordingSimulatedMotion()
        robot.motion = recorder

        result = module.run_check(robot, simulate=True, assume_yes=True, out=StringIO())
        shutdown = module.safe_shutdown(robot, out=StringIO())

        self.assertTrue(result.ok, result.message)
        self.assertTrue(shutdown.ok, shutdown.message)
        self.assertEqual(
            recorder.seen_actions,
            [
                ("sit", 1, 50),
                ("forward", 5, 95),
                ("sit", 1, 50),
                ("stand", 1, 50),
                ("forward", 5, 95),
            ],
        )
        self.assertEqual(recorder.seen_head_moves, [(30, 0.0, 0.0, 75)])
        self.assertIn("distance", robot.sensors.reads)
<<<<<<< HEAD
        self.assertEqual(robot.sensors.reads.count("touch"), 2)
=======
        self.assertEqual(robot.sensors.reads.count("touch"), 3)
>>>>>>> main
        self.assertEqual(robot.sensors.reads.count("imu"), 2)
        self.assertEqual(robot.sensors.reads.count("sound"), 1)
        self.assertEqual(robot.board.sounds[0].name, "single_bark_1")
        self.assertEqual(robot.board.rgb_commands[0].style, "monochromatic")
        self.assertEqual(len(robot.camera.captured), 1)
        self.assertEqual(robot.camera.start_count, 1)
        self.assertEqual(robot.camera.stop_count, 1)
        self.assertTrue(recorder.closed)
        self.assertTrue(robot.board.closed)

<<<<<<< HEAD
    def test_step_7_asserts_only_hardware_reachable_touch_states(self) -> None:
        module = load_script_module()
        robot = build_simulated_ports()
        robot.sensors.feed_touches(
            [module.TouchState.LEFT, module.TouchState.RIGHT, module.TouchState.BOTH]
        )

        result = module.run_check(
            robot,
            simulate=True,
            assume_yes=True,
            steps=(7,),
            out=StringIO(),
        )

        self.assertTrue(result.ok, result.message)
        self.assertEqual(robot.sensors.reads, ["touch", "touch"])
        self.assertIn("observed LEFT, RIGHT", result.results[0].message)

=======
>>>>>>> main
    def test_optional_camera_import_failure_skips_step_11_without_failing(self) -> None:
        module = load_script_module()
        robot = build_simulated_ports()

        def fake_import(name: str):
            if name == "vilib":
                raise RuntimeError("camera ribbon missing")
            return object()

        result = module.run_check(
            robot,
            simulate=False,
            assume_yes=True,
            steps=(1, 11),
            out=StringIO(),
            import_func=fake_import,
        )

        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.results[0].status, module.Status.PASS)
        self.assertEqual(result.results[1].status, module.Status.SKIP)
        self.assertIn("camera ribbon missing", result.results[1].message)
        self.assertEqual(robot.camera.start_count, 0)

    def test_safe_stop_close_camera_and_rgb_fire_on_injected_exception(self) -> None:
        module = load_script_module()
        robot = build_simulated_ports()
        module._prime_simulated_inputs(robot)
        output = StringIO()

        def fail_after_camera(step: int, _robot):
            if step == 11:
                raise HardwareError("injected failure")

        with self.assertRaisesRegex(HardwareError, "injected failure"):
            try:
                module.run_check(
                    robot,
                    simulate=True,
                    assume_yes=True,
                    out=output,
                    after_step=fail_after_camera,
                )
            finally:
                module.safe_shutdown(robot, out=output)

        self.assertGreaterEqual(robot.motion.stop_count, 1)
        self.assertTrue(robot.motion.closed)
        self.assertGreaterEqual(robot.board.rgb_cleared, 1)
        self.assertEqual(robot.camera.stop_count, 1)

    def test_steps_selector_runs_only_requested_range(self) -> None:
        module = load_script_module()
        output = StringIO()

        exit_code = module.main(["--ci", "--steps", "13-17"], out=output)

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertNotIn("Step 1 ", output.getvalue())
        self.assertNotIn("Step 11 ", output.getvalue())
        self.assertIn("Step 13 PASS", output.getvalue())
        self.assertIn("Step 17 PASS", output.getvalue())

    def test_parse_steps_accepts_alias_shape(self) -> None:
        module = load_script_module()

        self.assertEqual(module.parse_steps("11,13-15,15,18"), (11, 13, 14, 15, 18))


if __name__ == "__main__":
    unittest.main()
