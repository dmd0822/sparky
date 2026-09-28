"""Simulator implementations of every hardware port.

These run anywhere Python runs — a GitHub-hosted runner, a laptop, or a Pi with
the robot powered down. They record what an application asked the hardware to
do so tests can assert on intent rather than on servo side effects, and they
enforce the same safety envelope the real adapters do. A command that the
simulator rejects would also be rejected on the robot.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from itertools import cycle
from typing import Iterable, Iterator, Sequence

from .ports import (
    DEFAULT_LIMITS,
    HEAD_JOINT_COUNT,
    LEG_JOINT_COUNT,
    Frame,
    HardwareError,
    ImuReading,
    MotionLimits,
    RgbColor,
    RobotPorts,
    TouchState,
    validate_angles,
    validate_rgb_style,
    validate_speed,
)

__all__ = [
    "MotionCommand",
    "RgbCommand",
    "SimulatedBoard",
    "SimulatedCamera",
    "SimulatedMotion",
    "SimulatedSensors",
    "SoundCommand",
    "build_simulated_ports",
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
        if not action or not action.strip():
            raise HardwareError("action name must not be empty")
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

    def __init__(self, frames: Iterable[Frame] | None = None) -> None:
        self._source: list[Frame] = list(frames) if frames is not None else [solid_frame()]
        if not self._source:
            raise ValueError("SimulatedCamera requires at least one frame")
        self._cursor: Iterator[Frame] | None = None
        self._running = False
        self.width = 0
        self.height = 0
        self.start_count = 0
        self.stop_count = 0
        self.captured: list[Frame] = []

    def start(self, *, width: int = 640, height: int = 480) -> None:
        if width <= 0 or height <= 0:
            raise HardwareError(
                f"capture dimensions must be positive, got {width}x{height}"
            )
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
) -> RobotPorts:
    """Assemble a fully simulated :class:`RobotPorts` bundle."""

    return RobotPorts(
        motion=SimulatedMotion(limits=limits),
        board=SimulatedBoard(),
        camera=SimulatedCamera(frames=frames),
        sensors=SimulatedSensors(),
        profile=SIMULATOR_PROFILE,
    )
