import unittest
from pathlib import Path
from unittest.mock import patch

from src.hardware_adapter import PiAdapter, SimulatorAdapter
from src.import_guards import find_banned_imports
from src import pidog_connectivity


class StubBackend:
    def speak_block(self, sound: str, volume: int) -> dict[str, object]:
        return {"ok": True, "sound": sound, "volume": volume}

    def get_battery_voltage(self) -> float:
        return 7.4


class MilestoneOneTests(unittest.TestCase):
    def test_simulator_adapter_supports_semantic_operations(self) -> None:
        adapter = SimulatorAdapter()
        adapter.arm()
        adapter.set_posture("happy")
        adapter.set_head("searching")
        adapter.set_tail(1.25)
        adapter.play_gesture("wave")

        state = adapter.describe()
        self.assertEqual(state["posture"], "happy")
        self.assertEqual(state["head"], "searching")
        self.assertEqual(state["tail"], 1.0)
        self.assertEqual(state["gestures"], ["wave"])

    def test_pi_adapter_refuses_version_mismatch(self) -> None:
        adapter = PiAdapter(
            backend=StubBackend(),
            pinned_versions={"pidog": "9.9.9", "robot_hat": "9.9.9"},
            resolved_versions={"pidog": "9.9.8", "robot_hat": "9.9.8"},
        )

        with self.assertRaisesRegex(RuntimeError, "version mismatch"):
            adapter.arm()

    def test_import_guard_blocks_banned_modules_outside_adapter(self) -> None:
        root = Path(__file__).resolve().parents[1]
        violations = find_banned_imports(root)
        self.assertEqual(violations, [])

    def test_connectivity_smoke_script_returns_zero_off_pi_when_runtime_is_missing(self) -> None:
        with patch.object(pidog_connectivity, "build_report", return_value={"imports": {"pidog": {"ok": False}, "robot_hat": {"ok": False}}}):
            with patch.object(pidog_connectivity, "can_instantiate_hardware", return_value=False):
                with patch("sys.argv", ["pidog_connectivity.py"]):
                    self.assertEqual(pidog_connectivity.main(), 0)

    def test_connectivity_smoke_script_returns_one_on_pi_like_hosts_when_runtime_is_missing(self) -> None:
        with patch.object(pidog_connectivity, "build_report", return_value={"imports": {"pidog": {"ok": False}, "robot_hat": {"ok": False}}}):
            with patch.object(pidog_connectivity, "can_instantiate_hardware", return_value=True):
                with patch("sys.argv", ["pidog_connectivity.py"]):
                    self.assertEqual(pidog_connectivity.main(), 1)


if __name__ == "__main__":
    unittest.main()
