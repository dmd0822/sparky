"""Unit tests for service-level motion intents."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from src.device.sparky_device.hardware import HardwareError, SimulatedMotion
from src.device.sparky_device.services import MotionService, Posture


ROOT = Path(__file__).parents[1]


class MotionServiceTranslationTests(unittest.TestCase):
    def test_service_operations_translate_to_expected_motion_actions(self) -> None:
        cases = (
            ("stand", {}, "stand", 1, 50),
            ("sit", {"speed": 40}, "sit", 1, 40),
            ("lie", {}, "lie", 1, 50),
            ("trot", {"steps": 2, "speed": 60}, "trot", 2, 60),
            ("forward", {"steps": 3, "speed": 30}, "forward", 3, 30),
            ("backward", {"steps": 4, "speed": 35}, "backward", 4, 35),
            ("turn_left", {"steps": 5, "speed": 45}, "turn_left", 5, 45),
            ("turn_right", {"steps": 6, "speed": 55}, "turn_right", 6, 55),
        )
        for method_name, kwargs, action, steps, speed in cases:
            with self.subTest(method=method_name):
                motion = SimulatedMotion()
                service = MotionService(motion)

                getattr(service, method_name)(**kwargs)

                self.assertEqual(len(motion.commands), 1)
                command = motion.commands[0]
                self.assertEqual(command.kind, "action")
                self.assertEqual(command.name, action)
                self.assertEqual(command.steps, steps)
                self.assertEqual(command.speed, speed)

    def test_invalid_speed_is_rejected_before_adapter_call(self) -> None:
        motion = SimulatedMotion()
        service = MotionService(motion)

        with self.assertRaises(HardwareError):
            service.forward(speed=101)

        self.assertEqual(motion.commands, [])

    def test_bad_step_count_is_rejected_before_adapter_call(self) -> None:
        motion = SimulatedMotion()
        service = MotionService(motion)

        with self.assertRaises(HardwareError):
            service.forward(steps=0)

        self.assertEqual(motion.commands, [])


class MotionServiceSafetyTests(unittest.TestCase):
    def test_conflicting_command_is_rejected_while_motion_is_in_flight(self) -> None:
        motion = SimulatedMotion()
        service = MotionService(motion)
        service.forward(steps=2)
        before = list(motion.commands)

        with self.assertRaisesRegex(HardwareError, "in flight"):
            service.turn_left()

        self.assertEqual(motion.commands, before)
        self.assertTrue(service.state.in_flight)
        self.assertEqual(service.state.active_action, "forward")

    def test_wait_until_idle_allows_next_command(self) -> None:
        motion = SimulatedMotion()
        service = MotionService(motion)

        service.forward()
        service.wait_until_idle(timeout=0.1)
        service.turn_right()

        self.assertEqual([command.name for command in motion.commands], ["forward", "turn_right"])
        self.assertTrue(service.state.in_flight)
        self.assertEqual(service.state.active_action, "turn_right")

    def test_stop_preempts_motion_and_is_idempotent(self) -> None:
        motion = SimulatedMotion()
        service = MotionService(motion)
        service.forward(steps=5)

        first_state = service.stop()
        second_state = service.stop()

        self.assertEqual(motion.commands, [])
        self.assertEqual(motion.stop_count, 2)
        self.assertFalse(first_state.in_flight)
        self.assertFalse(second_state.in_flight)
        self.assertIsNone(service.state.active_action)

    def test_posture_transition_requires_stand_before_locomotion(self) -> None:
        motion = SimulatedMotion()
        service = MotionService(motion)

        service.sit()
        service.wait_until_idle(timeout=0.1)
        self.assertIs(service.state.posture, Posture.SITTING)
        before = list(motion.commands)

        with self.assertRaisesRegex(HardwareError, "requires posture STANDING"):
            service.trot()

        self.assertEqual(motion.commands, before)

        service.stand()
        service.wait_until_idle(timeout=0.1)
        service.trot()
        self.assertEqual([command.name for command in motion.commands], ["sit", "stand", "trot"])
        self.assertIs(service.state.posture, Posture.STANDING)

    def test_commands_after_close_are_rejected_but_stop_is_safe(self) -> None:
        motion = SimulatedMotion()
        service = MotionService(motion)

        service.close()
        service.stop()

        self.assertEqual(motion.stop_count, 1)
        self.assertTrue(service.state.closed)
        with self.assertRaisesRegex(HardwareError, "closed"):
            service.stand()


class MotionServiceImportTests(unittest.TestCase):
    def test_motion_service_does_not_import_vendor_libraries(self) -> None:
        source = (ROOT / "src" / "device" / "sparky_device" / "services" / "motion.py").read_text()
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

        self.assertTrue({"pidog", "robot_hat", "vilib", "cv2"}.isdisjoint(imported_roots))


if __name__ == "__main__":
    unittest.main()
