"""Unit tests for service-level camera capture and frame packaging."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from src.device.sparky_device.hardware import (
    Frame,
    HardwareError,
    HardwareUnavailableError,
    SimulatedCamera,
    VILIB_CAPTURE_SIZE,
    build_simulated_ports,
    load_frame_fixtures,
    solid_frame,
)
from src.device.sparky_device.services import (
    CameraService,
    CameraStatus,
    PackagedFrame,
)


ROOT = Path(__file__).parents[1]


class IncrementingClock:
    def __init__(self, start: float = 100.0, step: float = 0.25) -> None:
        self.current = start
        self.step = step

    def __call__(self) -> float:
        value = self.current
        self.current += self.step
        return value


class UnavailableCamera:
    def start(self, *, width: int = 640, height: int = 480) -> None:
        raise HardwareUnavailableError("camera missing")

    def capture(self) -> Frame:
        raise HardwareUnavailableError("camera missing")

    def stop(self) -> None:
        return None

    def is_running(self) -> bool:
        return False

    def camera_available(self) -> bool:
        return False


class MalformedCaptureCamera(SimulatedCamera):
    def capture(self):  # noqa: ANN201 - deliberately violates the port contract
        return "not a frame"


class FaultingCaptureCamera(SimulatedCamera):
    def capture(self) -> Frame:
        raise HardwareError("encoded frame was malformed")


class CameraServiceHappyPathTests(unittest.TestCase):
    def test_start_capture_stop_orchestrates_the_port(self) -> None:
        camera = SimulatedCamera([solid_frame(width=640, height=480, sequence=7)])
        service = CameraService(
            camera,
            source_id="front-camera",
            time_source=IncrementingClock(),
        )

        start = service.start()
        capture = service.capture_frame()
        stop = service.stop()

        self.assertIs(start.status, CameraStatus.OK)
        self.assertEqual(camera.start_count, 1)
        self.assertIs(capture.status, CameraStatus.OK)
        self.assertIsNotNone(capture.frame)
        assert capture.frame is not None
        self.assertEqual(capture.frame.image_bytes, camera.captured[0].data)
        self.assertEqual(capture.frame.source_width, 640)
        self.assertEqual(capture.frame.source_height, 480)
        self.assertEqual(capture.frame.packaged_width, 640)
        self.assertEqual(capture.frame.packaged_height, 480)
        self.assertEqual(capture.frame.sequence, 7)
        self.assertEqual(capture.frame.timestamp, 100.0)
        self.assertEqual(capture.frame.source_id, "front-camera")
        self.assertFalse(capture.frame.resized)
        self.assertIs(stop.status, CameraStatus.OK)
        self.assertEqual(camera.stop_count, 1)
        self.assertFalse(service.state.running)

    def test_start_and_stop_are_idempotent(self) -> None:
        camera = SimulatedCamera()
        service = CameraService(camera, time_source=IncrementingClock())

        first_start = service.start()
        second_start = service.start()
        first_stop = service.stop()
        second_stop = service.stop()

        self.assertIs(first_start.status, CameraStatus.OK)
        self.assertIs(second_start.status, CameraStatus.OK)
        self.assertEqual(camera.start_count, 1)
        self.assertIs(first_stop.status, CameraStatus.OK)
        self.assertIs(second_stop.status, CameraStatus.OK)
        self.assertEqual(camera.stop_count, 1)

    def test_capture_before_start_returns_unavailable_status(self) -> None:
        service = CameraService(SimulatedCamera(), time_source=IncrementingClock())

        capture = service.capture_frame()

        self.assertIs(capture.status, CameraStatus.UNAVAILABLE)
        self.assertIsNone(capture.frame)
        self.assertIn("start", capture.detail or "")

    def test_packaged_frame_as_dict_is_json_friendly(self) -> None:
        frame = PackagedFrame(
            image_bytes=b"abc",
            source_width=640,
            source_height=480,
            packaged_width=640,
            packaged_height=480,
            format="jpeg",
            sequence=3,
            timestamp=12.5,
            source_id="front-camera",
        )

        data = frame.as_dict()

        self.assertEqual(data["image_base64"], "YWJj")
        self.assertEqual(data["byte_length"], 3)
        self.assertEqual(data["source_id"], "front-camera")

    def test_optional_resize_degrades_to_original_bytes_without_hard_dependency(self) -> None:
        camera = SimulatedCamera([solid_frame(width=640, height=480, sequence=2)])
        service = CameraService(
            camera,
            target_width=320,
            target_height=240,
            time_source=IncrementingClock(),
        )

        service.start()
        capture = service.capture_frame()

        self.assertIs(capture.status, CameraStatus.OK)
        self.assertIsNotNone(capture.frame)
        assert capture.frame is not None
        self.assertEqual(capture.frame.source_width, 640)
        self.assertEqual(capture.frame.source_height, 480)
        self.assertEqual(capture.frame.packaged_width, 640)
        self.assertEqual(capture.frame.packaged_height, 480)
        self.assertFalse(capture.frame.resized)
        self.assertIn("original frame", capture.frame.detail or "")


class CameraServiceErrorPathTests(unittest.TestCase):
    def test_unavailable_camera_is_returned_as_status(self) -> None:
        service = CameraService(UnavailableCamera(), time_source=IncrementingClock())

        start = service.start()
        capture = service.capture_frame()

        self.assertIs(start.status, CameraStatus.UNAVAILABLE)
        self.assertFalse(start.running)
        self.assertIn("not available", start.detail or "")
        self.assertIs(capture.status, CameraStatus.UNAVAILABLE)
        self.assertIsNone(capture.frame)

    def test_malformed_non_frame_return_is_returned_as_status(self) -> None:
        camera = MalformedCaptureCamera()
        service = CameraService(camera, time_source=IncrementingClock())

        service.start()
        capture = service.capture_frame()

        self.assertIs(capture.status, CameraStatus.MALFORMED)
        self.assertIsNone(capture.frame)
        self.assertIn("non-Frame", capture.detail or "")

    def test_hardware_error_during_capture_is_malformed_status(self) -> None:
        camera = FaultingCaptureCamera()
        service = CameraService(camera, time_source=IncrementingClock())

        service.start()
        capture = service.capture_frame()

        self.assertIs(capture.status, CameraStatus.MALFORMED)
        self.assertIn("malformed", capture.detail or "")

    def test_close_stops_camera_and_later_capture_is_unavailable(self) -> None:
        camera = SimulatedCamera()
        service = CameraService(camera, time_source=IncrementingClock())

        service.start()
        closed = service.close()
        capture = service.capture_frame()

        self.assertTrue(closed.closed)
        self.assertFalse(camera.is_running())
        self.assertIs(capture.status, CameraStatus.UNAVAILABLE)
        self.assertIn("closed", capture.detail or "")


class CameraFixtureReplayTests(unittest.TestCase):
    def test_loads_sorted_fixture_files_for_replay(self) -> None:
        fixture_dir = ROOT / "tests" / "fixtures" / "camera"

        frames = load_frame_fixtures(fixture_dir)
        camera = SimulatedCamera.from_fixture_directory(fixture_dir)
        camera.start()
        frame = camera.capture()

        self.assertEqual(len(frames), 1)
        self.assertEqual(frame.data.strip(), b"sparky-fixture-frame-001")
        self.assertEqual((frame.width, frame.height), VILIB_CAPTURE_SIZE)
        self.assertEqual(frame.format, "jpeg")
        self.assertEqual(frame.sequence, 1)

    def test_build_simulated_ports_accepts_fixture_directory(self) -> None:
        fixture_dir = ROOT / "tests" / "fixtures" / "camera"
        ports = build_simulated_ports(camera_fixture_dir=fixture_dir)

        ports.camera.start()
        frame = ports.camera.capture()

        self.assertEqual(frame.data.strip(), b"sparky-fixture-frame-001")

    def test_rejects_missing_fixture_directory(self) -> None:
        with self.assertRaises(ValueError):
            load_frame_fixtures(ROOT / "tests" / "fixtures" / "missing-camera")


class CameraServiceImportTests(unittest.TestCase):
    def test_camera_service_does_not_import_vendor_libraries(self) -> None:
        source = (
            ROOT
            / "src"
            / "device"
            / "sparky_device"
            / "services"
            / "camera.py"
        ).read_text()
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

        self.assertTrue({"pidog", "robot_hat", "vilib", "cv2", "numpy"}.isdisjoint(imported_roots))


if __name__ == "__main__":
    unittest.main()
