"""Simulator implementations of every hardware port.

These run anywhere Python runs — a GitHub-hosted runner, a laptop, or a Pi with
the robot powered down. They record what an application asked the hardware to
do so tests can assert on intent rather than on servo side effects, and they
enforce the same safety envelope the real adapters do. A command that the
simulator rejects would also be rejected on the robot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from itertools import cycle
from typing import Iterable, Iterator, Sequence
import wave

from .ports import (
    AudioChunk,
    DEFAULT_LIMITS,
    HEAD_JOINT_COUNT,
    LEG_JOINT_COUNT,
    Frame,
    HardwareError,
    HardwareUnavailableError,
    ImuReading,
    MotionLimits,
    RgbColor,
    RobotPorts,
    TouchState,
    VILIB_CAPTURE_SIZE,
    validate_angles,
    validate_action_name,
    validate_audio_format,
    validate_camera_resolution,
    validate_rgb_style,
    validate_speed,
)

__all__ = [
    "MotionCommand",
    "PlaybackCommand",
    "RgbCommand",
    "SimulatedBoard",
    "SimulatedCamera",
    "SimulatedMicrophone",
    "SimulatedMotion",
    "SimulatedSensors",
    "SimulatedSpeaker",
    "SoundCommand",
    "build_simulated_ports",
    "load_wav_fixture",
    "load_frame_fixtures",
    "solid_frame",
]

SIMULATOR_PROFILE = "simulator"


@dataclass(frozen=True)
class MotionCommand:
    """One recorded motion request."""

    kind: str
    name: str
    angles: tuple[float, ...]
    speed: int
    steps: int = 1


@dataclass(frozen=True)
class SoundCommand:
    """One recorded audio request."""

    name: str
    volume: int


@dataclass(frozen=True)
class PlaybackCommand:
    """One recorded speaker playback request."""

    audio: bytes
    audio_format: str
    sample_rate: int
    channels: int
    sample_width: int
    volume: int


@dataclass(frozen=True)
class RgbCommand:
    """One recorded RGB request."""

    style: str
    color: RgbColor
    brightness: float
    speed: int


class SimulatedMotion:
    """Records motion requests and enforces :class:`MotionLimits`."""

    def __init__(
        self,
        limits: MotionLimits = DEFAULT_LIMITS,
        *,
        settle_after: float | None = 0.0,
    ) -> None:
        self.limits = limits
        self.commands: list[MotionCommand] = []
        self.stop_count = 0
        self.wait_count = 0
        self.closed = False
        self.settle_after = settle_after
        self._busy_until: float | None = 0.0

    def _record(self, command: MotionCommand) -> None:
        if self.closed:
            raise HardwareError("motion port is closed")
        self.commands.append(command)
        self._busy_until = (
            None
            if self.settle_after is None
            else time.monotonic() + self.settle_after
        )

    def do_action(self, action: str, *, steps: int = 1, speed: int = 50) -> None:
        action = validate_action_name(action)
        if steps < 1:
            raise HardwareError(f"steps must be at least 1, got {steps}")
        self._record(
            MotionCommand(
                kind="action",
                name=action,
                angles=(),
                speed=validate_speed(speed, self.limits),
                steps=steps,
            )
        )

    def move_legs(self, angles: Sequence[float], *, speed: int = 50) -> None:
        checked = validate_angles(
            angles,
            count=LEG_JOINT_COUNT,
            servo_range=self.limits.leg,
            group="legs",
        )
        self._record(
            MotionCommand(
                kind="legs",
                name="legs",
                angles=checked,
                speed=validate_speed(speed, self.limits),
            )
        )

    def move_head(
        self,
        *,
        yaw: float = 0.0,
        roll: float = 0.0,
        pitch: float = 0.0,
        speed: int = 50,
    ) -> None:
        checked = validate_angles(
            (yaw, roll, pitch),
            count=HEAD_JOINT_COUNT,
            servo_range=self.limits.head,
            group="head",
        )
        self._record(
            MotionCommand(
                kind="head",
                name="head",
                angles=checked,
                speed=validate_speed(speed, self.limits),
            )
        )

    def move_tail(self, angle: float, *, speed: int = 50) -> None:
        checked = validate_angles(
            (angle,),
            count=1,
            servo_range=self.limits.tail,
            group="tail",
        )
        self._record(
            MotionCommand(
                kind="tail",
                name="tail",
                angles=checked,
                speed=validate_speed(speed, self.limits),
            )
        )

    def wait_all_done(self, timeout: float | None = None) -> None:
        if timeout is not None and timeout < 0:
            raise HardwareError(f"timeout must be non-negative, got {timeout}")
        self.wait_count += 1
        deadline = None if timeout is None else time.monotonic() + timeout
        while self._busy_until is None or time.monotonic() < self._busy_until:
            if deadline is not None and time.monotonic() >= deadline:
                raise HardwareError(
                    f"timed out waiting for motion to finish after {timeout:g} seconds"
                )
            time.sleep(0.001)

    def stop(self) -> None:
        self.stop_count += 1
        self.commands.clear()
        self._busy_until = 0.0

    def close(self) -> None:
        self.closed = True

    def actions(self) -> list[str]:
        """Convenience accessor for the named actions requested so far."""

        return [c.name for c in self.commands if c.kind == "action"]


class SimulatedBoard:
    """Records audio and RGB output requests."""

    def __init__(self, volume: int = 100) -> None:
        self.sounds: list[SoundCommand] = []
        self.rgb_commands: list[RgbCommand] = []
        self.volume = self._check_volume(volume)
        self.rgb_cleared = 0
        self.closed = False

    @staticmethod
    def _check_volume(volume: int) -> int:
        if not 0 <= volume <= 100:
            raise HardwareError(f"volume must be between 0 and 100, got {volume}")
        return int(volume)

    def play_sound(self, name: str, *, volume: int = 100) -> None:
        if self.closed:
            raise HardwareError("board port is closed")
        if not name or not name.strip():
            raise HardwareError("sound name must not be empty")
        self.sounds.append(SoundCommand(name=name, volume=self._check_volume(volume)))

    def set_volume(self, volume: int) -> None:
        self.volume = self._check_volume(volume)

    def set_rgb(
        self,
        *,
        style: str,
        color: RgbColor,
        brightness: float = 1.0,
        speed: int = 50,
    ) -> None:
        if self.closed:
            raise HardwareError("board port is closed")
        style = validate_rgb_style(style)
        if not 0.0 <= brightness <= 1.0:
            raise HardwareError(
                f"brightness must be between 0.0 and 1.0, got {brightness}"
            )
        self.rgb_commands.append(
            RgbCommand(style=style, color=color, brightness=brightness, speed=speed)
        )

    def clear_rgb(self) -> None:
        self.rgb_cleared += 1

    def close(self) -> None:
        self.closed = True


def solid_frame(
    *,
    width: int = 8,
    height: int = 8,
    fill: int = 0x7F,
    sequence: int = 0,
) -> Frame:
    """Build a deterministic placeholder frame for fixtures."""

    return Frame(
        data=bytes([fill]) * (width * height),
        width=width,
        height=height,
        format="raw",
        sequence=sequence,
    )


class SimulatedCamera:
    """Replays a fixed set of frames instead of driving ``vilib``."""

    def __init__(
        self, frames: Iterable[Frame] | None = None, *, available: bool = True
    ) -> None:
        native_width, native_height = VILIB_CAPTURE_SIZE
        self._source: list[Frame] = (
            list(frames)
            if frames is not None
            else [solid_frame(width=native_width, height=native_height)]
        )
        if not self._source:
            raise ValueError("SimulatedCamera requires at least one frame")
        self._available = available
        self._cursor: Iterator[Frame] | None = None
        self._running = False
        self.width = 0
        self.height = 0
        self.start_count = 0
        self.stop_count = 0
        self.captured: list[Frame] = []

    @classmethod
    def from_fixture_directory(
        cls,
        fixture_dir: str | Path,
        *,
        width: int = VILIB_CAPTURE_SIZE[0],
        height: int = VILIB_CAPTURE_SIZE[1],
        available: bool = True,
    ) -> "SimulatedCamera":
        """Build a replay camera from encoded frame files on disk."""

        return cls(
            load_frame_fixtures(fixture_dir, width=width, height=height),
            available=available,
        )

    def start(self, *, width: int = 640, height: int = 480) -> None:
        width, height = validate_camera_resolution(width, height)
        if not self._available:
            raise HardwareUnavailableError("simulated camera is not available")
        if self._running:
            return
        self._running = True
        self.width = width
        self.height = height
        self.start_count += 1
        self._cursor = cycle(self._source)

    def capture(self) -> Frame:
        if not self._running or self._cursor is None:
            raise HardwareError("camera port is not running; call start() first")
        frame = next(self._cursor)
        self.captured.append(frame)
        return frame

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._cursor = None
        self.stop_count += 1

    def is_running(self) -> bool:
        return self._running

    def camera_available(self) -> bool:
        return self._available


class SimulatedMicrophone:
    """Replays scripted PCM chunks or WAV fixtures for microphone capture."""

    def __init__(
        self,
        chunks: Iterable[bytes] | None = None,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        available: bool = True,
        busy: bool = False,
        loop: bool = True,
    ) -> None:
        validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        self._source = list(chunks) if chunks is not None else []
        if not self._source:
            frame_width = channels * sample_width
            self._source = [b"\x00" * (max(1, sample_rate // 10) * frame_width)]
        if any(not chunk for chunk in self._source):
            raise ValueError("SimulatedMicrophone chunks must not be empty")
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self._available = available
        self._busy = busy
        self._loop = loop
        self._running = False
        self._cursor = 0
        self._requested_frames_per_chunk = 1600
        self._sequence = 0
        self.open_count = 0
        self.close_count = 0
        self.read_count = 0
        self.requested_formats: list[tuple[int, int, int, int]] = []

    @classmethod
    def from_wav(
        cls,
        fixture_path: str | Path,
        *,
        frames_per_chunk: int = 1600,
        available: bool = True,
        busy: bool = False,
        loop: bool = True,
    ) -> "SimulatedMicrophone":
        chunks, sample_rate, channels, sample_width = load_wav_fixture(
            fixture_path,
            frames_per_chunk=frames_per_chunk,
        )
        return cls(
            chunks,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
            available=available,
            busy=busy,
            loop=loop,
        )

    def set_available(self, available: bool) -> None:
        self._available = available

    def set_busy(self, busy: bool) -> None:
        self._busy = busy

    def open(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        frames_per_chunk: int = 1600,
    ) -> None:
        requested = validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        if frames_per_chunk <= 0:
            raise HardwareError(
                f"frames_per_chunk must be positive, got {frames_per_chunk}"
            )
        if not self._available:
            raise HardwareUnavailableError("simulated microphone is not available")
        if self._busy:
            raise HardwareError("simulated microphone is busy")
        if self._running:
            return
        self._running = True
        self.open_count += 1
        self._requested_frames_per_chunk = int(frames_per_chunk)
        self.requested_formats.append((*requested, int(frames_per_chunk)))

    def read_chunk(self) -> AudioChunk:
        if not self._running:
            raise HardwareError("microphone port is not open; call open() first")
        if not self._source:
            raise HardwareError("no simulated microphone chunks are configured")
        if self._cursor >= len(self._source):
            if not self._loop:
                raise HardwareError("no more simulated microphone chunks remain")
            self._cursor = 0
        data = self._source[self._cursor]
        self._cursor += 1
        self._sequence += 1
        self.read_count += 1
        return AudioChunk(
            data=data,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
            timestamp=time.monotonic(),
            sequence=self._sequence,
        )

    def close(self) -> None:
        if not self._running:
            return
        self._running = False
        self.close_count += 1

    def is_open(self) -> bool:
        return self._running

    def microphone_available(self) -> bool:
        return self._available


class SimulatedSpeaker:
    """Records PCM or encoded playback requests for assertions."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        available: bool = True,
        busy: bool = False,
    ) -> None:
        self.sample_rate, self.channels, self.sample_width = validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        self._available = available
        self._busy = busy
        self._open = False
        self.open_count = 0
        self.stop_count = 0
        self.close_count = 0
        self.playbacks: list[PlaybackCommand] = []
        self.requested_formats: list[tuple[int, int, int]] = []

    @staticmethod
    def _check_volume(volume: int) -> int:
        if not 0 <= volume <= 100:
            raise HardwareError(f"volume must be between 0 and 100, got {volume}")
        return int(volume)

    def set_available(self, available: bool) -> None:
        self._available = available

    def set_busy(self, busy: bool) -> None:
        self._busy = busy

    def open(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> None:
        requested = validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        if not self._available:
            raise HardwareUnavailableError("simulated speaker is not available")
        if self._busy:
            raise HardwareError("simulated speaker is busy")
        if self._open:
            return
        self.sample_rate, self.channels, self.sample_width = requested
        self.requested_formats.append(requested)
        self._open = True
        self.open_count += 1

    def play(
        self,
        audio: bytes,
        *,
        audio_format: str = "wav",
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        volume: int = 100,
    ) -> None:
        sample_rate, channels, sample_width = validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        if not self._open:
            raise HardwareError("speaker port is not open; call open() first")
        if self._busy:
            raise HardwareError("simulated speaker is busy")
        if not audio:
            raise HardwareError("speaker audio must not be empty")
        if not audio_format or not audio_format.strip():
            raise HardwareError("audio_format must not be empty")
        self.playbacks.append(
            PlaybackCommand(
                audio=bytes(audio),
                audio_format=audio_format.strip().lower(),
                sample_rate=sample_rate,
                channels=channels,
                sample_width=sample_width,
                volume=self._check_volume(volume),
            )
        )

    def stop(self) -> None:
        self.stop_count += 1

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self.close_count += 1

    def is_open(self) -> bool:
        return self._open

    def speaker_available(self) -> bool:
        return self._available


class SimulatedSensors:
    """Emits scripted sensor readings, holding the last value when exhausted."""

    def __init__(
        self,
        *,
        distances: Sequence[float | None] | None = None,
        touches: Sequence[TouchState] | None = None,
        imu_samples: Sequence[ImuReading] | None = None,
        sound_directions: Sequence[float | None] | None = None,
    ) -> None:
        self._distances = list(distances) if distances else [50.0]
        self._touches = list(touches) if touches else [TouchState.NONE]
        self._imu = list(imu_samples) if imu_samples else [
            ImuReading(acceleration=(0.0, 0.0, 1.0), gyro=(0.0, 0.0, 0.0))
        ]
        self._sound = list(sound_directions) if sound_directions else [None]
        self.reads: list[str] = []

    @staticmethod
    def _next(values: list, label: str):
        if not values:
            raise HardwareError(f"no scripted {label} readings remain")
        return values[0] if len(values) == 1 else values.pop(0)

    def read_distance_cm(self) -> float | None:
        self.reads.append("distance")
        return self._next(self._distances, "distance")

    def read_touch(self) -> TouchState:
        self.reads.append("touch")
        return self._next(self._touches, "touch")

    def read_imu(self) -> ImuReading:
        self.reads.append("imu")
        return self._next(self._imu, "imu")

    def read_sound_direction(self) -> float | None:
        self.reads.append("sound")
        return self._next(self._sound, "sound")

    def feed_distances(self, values: Sequence[float | None]) -> None:
        self._distances = list(values)

    def feed_touches(self, values: Sequence[TouchState]) -> None:
        self._touches = list(values)

    def feed_imu(self, values: Sequence[ImuReading]) -> None:
        self._imu = list(values)

    def feed_sound_directions(self, values: Sequence[float | None]) -> None:
        self._sound = list(values)


def build_simulated_ports(
    *,
    limits: MotionLimits = DEFAULT_LIMITS,
    frames: Iterable[Frame] | None = None,
    camera_fixture_dir: str | Path | None = None,
    microphone: SimulatedMicrophone | None = None,
    microphone_fixture_path: str | Path | None = None,
    speaker: SimulatedSpeaker | None = None,
) -> RobotPorts:
    """Assemble a fully simulated :class:`RobotPorts` bundle."""

    if frames is not None and camera_fixture_dir is not None:
        raise ValueError("pass either frames or camera_fixture_dir, not both")
    if microphone is not None and microphone_fixture_path is not None:
        raise ValueError("pass either microphone or microphone_fixture_path, not both")
    camera = (
        SimulatedCamera.from_fixture_directory(camera_fixture_dir)
        if camera_fixture_dir is not None
        else SimulatedCamera(frames=frames)
    )
    microphone_port = (
        SimulatedMicrophone.from_wav(microphone_fixture_path)
        if microphone_fixture_path is not None
        else (microphone if microphone is not None else SimulatedMicrophone())
    )

    return RobotPorts(
        motion=SimulatedMotion(limits=limits),
        board=SimulatedBoard(),
        camera=camera,
        microphone=microphone_port,
        speaker=speaker if speaker is not None else SimulatedSpeaker(),
        sensors=SimulatedSensors(),
        profile=SIMULATOR_PROFILE,
    )


def load_wav_fixture(
    fixture_path: str | Path,
    *,
    frames_per_chunk: int = 1600,
) -> tuple[list[bytes], int, int, int]:
    """Load a PCM WAV file into replay chunks."""

    if frames_per_chunk <= 0:
        raise ValueError(f"frames_per_chunk must be positive, got {frames_per_chunk}")
    path = Path(fixture_path)
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        chunks: list[bytes] = []
        while True:
            data = handle.readframes(frames_per_chunk)
            if not data:
                break
            chunks.append(data)
    if not chunks:
        raise ValueError(f"WAV fixture has no audio frames: {path}")
    return chunks, sample_rate, channels, sample_width


def load_frame_fixtures(
    fixture_dir: str | Path,
    *,
    width: int = VILIB_CAPTURE_SIZE[0],
    height: int = VILIB_CAPTURE_SIZE[1],
) -> list[Frame]:
    """Load sorted frame files from ``fixture_dir`` for replay.

    The simulator does not decode fixture bytes. Tests and off-robot runs often
    only need realistic encoded payloads to flow through capture and packaging,
    and CI intentionally has no image stack installed. Dimensions are therefore
    supplied by the caller and validated through the same ``Frame`` value object
    used by the real adapter.
    """

    directory = Path(fixture_dir)
    if not directory.is_dir():
        raise ValueError(f"camera fixture directory does not exist: {directory}")
    files = sorted(path for path in directory.iterdir() if path.is_file())
    if not files:
        raise ValueError(f"camera fixture directory has no files: {directory}")
    return [
        Frame(
            data=path.read_bytes(),
            width=width,
            height=height,
            format=_frame_format_from_suffix(path),
            sequence=index,
        )
        for index, path in enumerate(files, start=1)
    ]


def _frame_format_from_suffix(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"jpg", "jpeg"}:
        return "jpeg"
    return suffix or "jpeg"
