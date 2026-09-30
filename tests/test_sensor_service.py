"""Unit tests for service-level sensor normalisation."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from src.device.sparky_device.hardware import (
    HardwareError,
    HardwareUnavailableError,
    ImuReading,
    SimulatedSensors,
    TouchState,
)
from src.device.sparky_device.services import (
    ReadingStatus,
    SensorService,
)


ROOT = Path(__file__).parents[1]


class IncrementingClock:
    def __init__(self, start: float = 10.0, step: float = 0.5) -> None:
        self.current = start
        self.step = step

    def __call__(self) -> float:
        value = self.current
        self.current += self.step
        return value


class UnavailableSensors:
    def read_distance_cm(self) -> float | None:
        raise HardwareUnavailableError("ultrasonic missing")

    def read_touch(self) -> TouchState:
        raise HardwareUnavailableError("touch board missing")

    def read_imu(self) -> ImuReading:
        raise HardwareUnavailableError("imu missing")

    def read_sound_direction(self) -> float | None:
        raise HardwareUnavailableError("ears missing")


class MalformedSensors:
    def read_distance_cm(self):
        return "near"

    def read_touch(self):
        return "left"

    def read_imu(self):
        raise HardwareError("IMU returned an unexpected shape")

    def read_sound_direction(self):
        return object()


class VendorFaultSensors:
    def read_distance_cm(self) -> float | None:
        raise RuntimeError("ultrasonic driver crashed")

    def read_touch(self) -> TouchState:
        raise RuntimeError("touch driver crashed")

    def read_imu(self) -> ImuReading:
        raise RuntimeError("imu driver crashed")

    def read_sound_direction(self) -> float | None:
        raise RuntimeError("ears driver crashed")


class SensorServiceHappyPathTests(unittest.TestCase):
    def test_snapshot_normalises_all_sensor_groups(self) -> None:
        sensors = SimulatedSensors(
            distances=[21.5],
            touches=[TouchState.LEFT],
            imu_samples=[
                ImuReading(acceleration=(0.1, 0.2, 0.9), gyro=(1.0, 2.0, 3.0))
            ],
            sound_directions=[135.0],
        )
        service = SensorService(sensors, time_source=IncrementingClock())

        snapshot = service.read_snapshot()

        self.assertEqual(sensors.reads, ["distance", "touch", "imu", "sound"])
        self.assertIs(snapshot.distance.status, ReadingStatus.OK)
        self.assertEqual(snapshot.distance.distance_cm, 21.5)
        self.assertIs(snapshot.touch.status, ReadingStatus.OK)
        self.assertIs(snapshot.touch.touch, TouchState.LEFT)
        self.assertIs(snapshot.imu.status, ReadingStatus.OK)
        self.assertEqual(snapshot.imu.imu.acceleration, (0.1, 0.2, 0.9))
        self.assertIs(snapshot.sound_direction.status, ReadingStatus.OK)
        self.assertEqual(snapshot.sound_direction.direction_degrees, 135.0)
        self.assertEqual(service.state.last_snapshot, snapshot)

    def test_none_distance_and_sound_are_valid_ok_readings(self) -> None:
        service = SensorService(
            SimulatedSensors(distances=[None], sound_directions=[None]),
            time_source=IncrementingClock(),
        )

        snapshot = service.read_snapshot()

        self.assertIs(snapshot.distance.status, ReadingStatus.OK)
        self.assertIsNone(snapshot.distance.distance_cm)
        self.assertIn("no ultrasonic echo", snapshot.distance.detail or "")
        self.assertIs(snapshot.sound_direction.status, ReadingStatus.OK)
        self.assertIsNone(snapshot.sound_direction.direction_degrees)
        self.assertIn("no sound detected", snapshot.sound_direction.detail or "")

    def test_timestamps_are_present_and_monotonic(self) -> None:
        service = SensorService(SimulatedSensors(), time_source=IncrementingClock())

        snapshot = service.read_snapshot()

        timestamps = [
            snapshot.distance.timestamp,
            snapshot.touch.timestamp,
            snapshot.imu.timestamp,
            snapshot.sound_direction.timestamp,
            snapshot.timestamp,
        ]
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertTrue(all(timestamp > 0 for timestamp in timestamps))

    def test_readings_are_log_friendly_dicts(self) -> None:
        service = SensorService(SimulatedSensors(), time_source=IncrementingClock())

        data = service.read_snapshot().as_dict()

        self.assertEqual(data["distance"]["status"], "ok")
        self.assertIn("touch", data)
        self.assertIn("imu", data)
        self.assertIn("sound_direction", data)


class SensorServiceErrorPathTests(unittest.TestCase):
    def test_unavailable_hardware_is_returned_as_status_for_all_groups(self) -> None:
        service = SensorService(UnavailableSensors(), time_source=IncrementingClock())

        snapshot = service.read_snapshot()

        self.assertIs(snapshot.distance.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.touch.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.imu.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.sound_direction.status, ReadingStatus.UNAVAILABLE)
        self.assertIsNone(snapshot.distance.distance_cm)
        self.assertIsNone(snapshot.touch.touch)
        self.assertIsNone(snapshot.imu.imu)
        self.assertIsNone(snapshot.sound_direction.direction_degrees)

    def test_malformed_data_is_returned_as_status_for_all_groups(self) -> None:
        service = SensorService(MalformedSensors(), time_source=IncrementingClock())

        snapshot = service.read_snapshot()

        self.assertIs(snapshot.distance.status, ReadingStatus.MALFORMED)
        self.assertIs(snapshot.touch.status, ReadingStatus.MALFORMED)
        self.assertIs(snapshot.imu.status, ReadingStatus.MALFORMED)
        self.assertIs(snapshot.sound_direction.status, ReadingStatus.MALFORMED)
        self.assertIn("distance_cm", snapshot.distance.detail or "")
        self.assertIn("TouchState", snapshot.touch.detail or "")
        self.assertIn("IMU", snapshot.imu.detail or "")
        self.assertIn("direction_degrees", snapshot.sound_direction.detail or "")

    def test_arbitrary_vendor_exceptions_do_not_escape(self) -> None:
        service = SensorService(VendorFaultSensors(), time_source=IncrementingClock())

        snapshot = service.read_snapshot()

        self.assertIs(snapshot.distance.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.touch.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.imu.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.sound_direction.status, ReadingStatus.UNAVAILABLE)
        self.assertIn("RuntimeError", snapshot.distance.detail or "")

    def test_reads_after_close_report_unavailable_without_calling_port(self) -> None:
        service = SensorService(SimulatedSensors(), time_source=IncrementingClock())

        service.close()
        service.close()
        snapshot = service.read_snapshot()

        self.assertTrue(service.state.closed)
        self.assertIs(snapshot.distance.status, ReadingStatus.UNAVAILABLE)
        self.assertIn("closed", snapshot.distance.detail or "")
        self.assertIs(snapshot.touch.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.imu.status, ReadingStatus.UNAVAILABLE)
        self.assertIs(snapshot.sound_direction.status, ReadingStatus.UNAVAILABLE)


class SensorServiceImportTests(unittest.TestCase):
    def test_sensor_service_does_not_import_vendor_libraries(self) -> None:
        source = (
            ROOT
            / "src"
            / "device"
            / "sparky_device"
            / "services"
            / "sensors.py"
        ).read_text()
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
