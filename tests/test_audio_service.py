"""Unit tests for microphone capture, replay, normalization, and buffering."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from src.device.sparky_device.hardware import (
    AudioChunk,
    HardwareError,
    HardwareUnavailableError,
    MicrophonePort,
    SimulatedMicrophone,
    build_simulated_ports,
    load_wav_fixture,
)
from src.device.sparky_device.services import (
    AudioService,
    AudioStatus,
)


ROOT = Path(__file__).parents[1]
AUDIO_FIXTURES = ROOT / "tests" / "fixtures" / "audio"


class IncrementingClock:
    def __init__(self, start: float = 200.0, step: float = 0.1) -> None:
        self.current = start
        self.step = step

    def __call__(self) -> float:
        value = self.current
        self.current += self.step
        return value


class MissingMicrophone:
    def open(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        frames_per_chunk: int = 1600,
    ) -> None:
        raise HardwareUnavailableError("microphone missing")

    def read_chunk(self) -> AudioChunk:
        raise HardwareUnavailableError("microphone missing")

    def close(self) -> None:
        return None

    def is_open(self) -> bool:
        return False

    def microphone_available(self) -> bool:
        return False


class FaultingReadMicrophone(SimulatedMicrophone):
    def read_chunk(self) -> AudioChunk:
        raise HardwareError("microphone device is busy")


class MalformedReadMicrophone(SimulatedMicrophone):
    def read_chunk(self):  # noqa: ANN201 - deliberately violates the port contract
        return "not audio"


class AudioServiceHappyPathTests(unittest.TestCase):
    def test_simulated_microphone_satisfies_port(self) -> None:
        self.assertIsInstance(SimulatedMicrophone(), MicrophonePort)

    def test_start_capture_flush_stop_orchestrates_microphone(self) -> None:
        microphone = SimulatedMicrophone(
            [b"\x01\x00" * 1600],
            sample_rate=16000,
            channels=1,
            sample_width=2,
        )
        service = AudioService(microphone, source_id="front-mic", time_source=IncrementingClock())

        start = service.start()
        capture = service.capture_chunk()
        flushed = service.flush()
        stop = service.stop()

        self.assertIs(start.status, AudioStatus.OK)
        self.assertEqual(microphone.open_count, 1)
        self.assertIs(capture.status, AudioStatus.OK)
        self.assertIsNotNone(capture.chunk)
        assert capture.chunk is not None
        self.assertEqual(capture.chunk.sample_rate, 16000)
        self.assertEqual(capture.chunk.channels, 1)
        self.assertEqual(capture.chunk.sample_width, 2)
        self.assertEqual(capture.chunk.timestamp, 200.0)
        self.assertEqual(capture.buffered_chunks, 1)
        self.assertEqual(capture.buffered_bytes, service.chunk_size_bytes)
        self.assertIs(flushed.status, AudioStatus.OK)
        self.assertIsNotNone(flushed.audio)
        assert flushed.audio is not None
        self.assertEqual(flushed.audio.source_id, "front-mic")
        self.assertEqual(flushed.audio.chunk_count, 1)
        self.assertEqual(len(flushed.audio.audio_bytes), service.chunk_size_bytes)
        self.assertEqual(service.state.buffered_chunks, 0)
        self.assertIs(stop.status, AudioStatus.OK)
        self.assertEqual(microphone.close_count, 1)

    def test_buffer_is_bounded_by_whole_chunks_and_flushable(self) -> None:
        chunks = [
            bytes([value]) * 3200
            for value in (1, 2, 3)
        ]
        service = AudioService(
            SimulatedMicrophone(chunks, sample_rate=16000),
            chunk_seconds=0.1,
            max_buffer_seconds=0.2,
            time_source=IncrementingClock(),
        )

        service.start()
        for _ in range(3):
            self.assertIs(service.capture_chunk().status, AudioStatus.OK)
        flushed = service.flush()

        self.assertIsNotNone(flushed.audio)
        assert flushed.audio is not None
        self.assertEqual(flushed.audio.chunk_count, 2)
        self.assertEqual(flushed.audio.audio_bytes, chunks[1] + chunks[2])
        self.assertEqual(flushed.audio.duration_seconds, 0.2)
        self.assertEqual(service.state.buffered_bytes, 0)

    def test_flush_of_empty_buffer_is_ok_and_json_friendly(self) -> None:
        service = AudioService(SimulatedMicrophone(), time_source=IncrementingClock())

        flushed = service.flush()
        data = flushed.as_dict()

        self.assertIs(flushed.status, AudioStatus.OK)
        self.assertIsNotNone(flushed.audio)
        assert flushed.audio is not None
        self.assertEqual(flushed.audio.audio_bytes, b"")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["audio"]["audio_base64"], "")


class AudioFixtureReplayTests(unittest.TestCase):
    def test_loads_wav_fixture_for_replay(self) -> None:
        fixture = AUDIO_FIXTURES / "tone-16khz.wav"

        chunks, sample_rate, channels, sample_width = load_wav_fixture(fixture)
        microphone = SimulatedMicrophone.from_wav(fixture)
        microphone.open()
        chunk = microphone.read_chunk()

        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(sample_rate, 16000)
        self.assertEqual(channels, 1)
        self.assertEqual(sample_width, 2)
        self.assertEqual(chunk.sample_rate, 16000)
        self.assertEqual(chunk.channels, 1)
        self.assertEqual(chunk.sample_width, 2)
        self.assertEqual(len(chunk.data), 3200)

    def test_fixture_replay_through_service_produces_canonical_format(self) -> None:
        service = AudioService(
            SimulatedMicrophone.from_wav(AUDIO_FIXTURES / "tone-16khz.wav"),
            time_source=IncrementingClock(),
        )

        self.assertIs(service.start().status, AudioStatus.OK)
        capture = service.capture_chunk()

        self.assertIs(capture.status, AudioStatus.OK)
        self.assertIsNotNone(capture.chunk)
        assert capture.chunk is not None
        self.assertEqual(capture.chunk.sample_rate, 16000)
        self.assertEqual(capture.chunk.channels, 1)
        self.assertEqual(capture.chunk.sample_width, 2)
        self.assertEqual(len(capture.chunk.data), 3200)

    def test_non_canonical_fixture_is_resampled_to_canonical_format(self) -> None:
        service = AudioService(
            SimulatedMicrophone.from_wav(AUDIO_FIXTURES / "tone-8khz.wav"),
            time_source=IncrementingClock(),
        )

        self.assertIs(service.start().status, AudioStatus.OK)
        capture = service.capture_chunk()

        self.assertIs(capture.status, AudioStatus.OK)
        self.assertIsNotNone(capture.chunk)
        assert capture.chunk is not None
        self.assertEqual(capture.chunk.sample_rate, 16000)
        self.assertEqual(capture.chunk.channels, 1)
        self.assertEqual(capture.chunk.sample_width, 2)
        self.assertGreater(len(capture.chunk.data), 3200)

    def test_build_simulated_ports_accepts_microphone_fixture(self) -> None:
        ports = build_simulated_ports(
            microphone_fixture_path=AUDIO_FIXTURES / "tone-16khz.wav"
        )

        ports.microphone.open()
        chunk = ports.microphone.read_chunk()

        self.assertEqual(chunk.sample_rate, 16000)
        ports.close()

    def test_robot_ports_close_closes_microphone(self) -> None:
        microphone = SimulatedMicrophone()
        ports = build_simulated_ports(microphone=microphone)
        microphone.open()

        ports.close()

        self.assertFalse(microphone.is_open())
        self.assertEqual(microphone.close_count, 1)


class AudioServiceErrorPathTests(unittest.TestCase):
    def test_missing_microphone_is_unavailable_status(self) -> None:
        service = AudioService(MissingMicrophone(), time_source=IncrementingClock())

        start = service.start()
        capture = service.capture_chunk()

        self.assertIs(start.status, AudioStatus.UNAVAILABLE)
        self.assertIn("not available", start.detail or "")
        self.assertIs(capture.status, AudioStatus.UNAVAILABLE)
        self.assertIsNone(capture.chunk)

    def test_busy_microphone_open_is_malformed_status_not_exception(self) -> None:
        service = AudioService(
            SimulatedMicrophone(busy=True),
            time_source=IncrementingClock(),
        )

        start = service.start()

        self.assertIs(start.status, AudioStatus.MALFORMED)
        self.assertIn("busy", start.detail or "")

    def test_busy_microphone_read_is_malformed_status_not_exception(self) -> None:
        service = AudioService(FaultingReadMicrophone(), time_source=IncrementingClock())

        self.assertIs(service.start().status, AudioStatus.OK)
        capture = service.capture_chunk()

        self.assertIs(capture.status, AudioStatus.MALFORMED)
        self.assertIn("busy", capture.detail or "")

    def test_malformed_microphone_return_is_status_not_exception(self) -> None:
        service = AudioService(MalformedReadMicrophone(), time_source=IncrementingClock())

        self.assertIs(service.start().status, AudioStatus.OK)
        capture = service.capture_chunk()

        self.assertIs(capture.status, AudioStatus.MALFORMED)
        self.assertIn("non-AudioChunk", capture.detail or "")

    def test_close_stops_capture_and_later_capture_is_unavailable(self) -> None:
        microphone = SimulatedMicrophone()
        service = AudioService(microphone, time_source=IncrementingClock())

        service.start()
        closed = service.close()
        capture = service.capture_chunk()

        self.assertTrue(closed.closed)
        self.assertFalse(microphone.is_open())
        self.assertIs(capture.status, AudioStatus.UNAVAILABLE)
        self.assertIn("closed", capture.detail or "")


class AudioServiceImportTests(unittest.TestCase):
    def test_audio_service_does_not_import_vendor_libraries(self) -> None:
        source = (
            ROOT
            / "src"
            / "device"
            / "sparky_device"
            / "services"
            / "audio.py"
        ).read_text()
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

        self.assertTrue(
            {"pidog", "robot_hat", "vilib", "cv2", "sounddevice", "pyaudio"}.isdisjoint(
                imported_roots
            )
        )


if __name__ == "__main__":
    unittest.main()
