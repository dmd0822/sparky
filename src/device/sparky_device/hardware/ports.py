"""Hardware abstraction ports for the Sparky device runtime.

Application code depends on the :class:`~typing.Protocol` definitions in this
module, never on ``pidog``, ``robot_hat`` or ``vilib`` directly. That keeps the
vendor boundary thin enough that GitHub-hosted runners — which have no PiDog
attached — can exercise the same call sites the Raspberry Pi executes.

Two implementations satisfy every port:

``sparky_device.hardware.simulators``
    Recording fakes for unit tests and laptop development.
``sparky_device.hardware.pidog_adapters``
    Thin translations onto the SunFounder libraries, imported lazily so this
    package stays importable off-device.

The value objects below are deliberately vendor-neutral. If SunFounder changes
an argument name or a return encoding, only the adapter module changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Protocol, Sequence, runtime_checkable

__all__ = [
    "BoardPort",
    "CameraPort",
    "DEFAULT_LIMITS",
    "Frame",
    "HardwareError",
    "HardwareUnavailableError",
    "HEAD_JOINT_COUNT",
    "ImuReading",
    "LEG_JOINT_COUNT",
    "MotionLimits",
    "MotionPort",
    "RgbColor",
    "RGB_STYLES",
    "RobotPorts",
    "SensorPort",
    "ServoRange",
    "TouchState",
    "validate_angles",
    "validate_rgb_style",
    "validate_speed",
]


class HardwareError(RuntimeError):
    """A hardware port rejected or could not complete a request."""


class HardwareUnavailableError(HardwareError):
    """The vendor libraries or the physical robot are not present."""


#: The PiDog drives four legs with two servos each.
LEG_JOINT_COUNT = 8

#: The head is yaw, roll, pitch.
HEAD_JOINT_COUNT = 3


@dataclass(frozen=True)
class ServoRange:
    """An inclusive, validated range of permitted values."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError(
                f"minimum {self.minimum} must not exceed maximum {self.maximum}"
            )

    def contains(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum

    def clamp(self, value: float) -> float:
        return min(max(value, self.minimum), self.maximum)


@dataclass(frozen=True)
class MotionLimits:
    """Conservative servo envelopes enforced before anything reaches a servo.

    A persona or behaviour may tighten these further; nothing may widen them
    past what the adapter accepts.
    """

    leg: ServoRange = ServoRange(-90.0, 90.0)
    head: ServoRange = ServoRange(-90.0, 90.0)
    tail: ServoRange = ServoRange(-90.0, 90.0)
    speed: ServoRange = ServoRange(0.0, 100.0)


DEFAULT_LIMITS = MotionLimits()

RGB_STYLES: Final[tuple[str, ...]] = (
    "monochromatic",
    "breath",
    "boom",
    "bark",
    "speak",
    "listen",
)
_RGB_STYLE_SET: Final[frozenset[str]] = frozenset(RGB_STYLES)


def validate_rgb_style(style: str) -> str:
    """Return ``style`` unchanged, or raise :class:`HardwareError`."""

    if style not in _RGB_STYLE_SET:
        raise HardwareError(
            f"RGB style {style!r} is invalid; expected one of: "
            + ", ".join(RGB_STYLES)
        )
    return style


def validate_speed(speed: int, limits: MotionLimits = DEFAULT_LIMITS) -> int:
    """Return ``speed`` unchanged, or raise :class:`HardwareError`."""

    if not limits.speed.contains(speed):
        raise HardwareError(
            f"speed {speed} is outside the safe range "
            f"[{limits.speed.minimum}, {limits.speed.maximum}]"
        )
    return int(speed)


def validate_angles(
    values: Sequence[float],
    *,
    count: int,
    servo_range: ServoRange,
    group: str,
) -> tuple[float, ...]:
    """Validate a joint-group command and normalise it to a tuple."""

    angles = tuple(float(value) for value in values)
    if len(angles) != count:
        raise HardwareError(f"{group} expects {count} angle(s), received {len(angles)}")
    for index, angle in enumerate(angles):
        if not servo_range.contains(angle):
            raise HardwareError(
                f"{group} angle #{index} ({angle}) is outside the safe range "
                f"[{servo_range.minimum}, {servo_range.maximum}]"
            )
    return angles


@dataclass(frozen=True)
class RgbColor:
    """An 8-bit RGB colour."""

    red: int
    green: int
    blue: int

    def __post_init__(self) -> None:
        for name in ("red", "green", "blue"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an int, got {value!r}")
            if not 0 <= value <= 255:
                raise ValueError(f"{name} must be between 0 and 255, got {value}")

    @classmethod
    def from_hex(cls, value: str) -> "RgbColor":
        text = value.lstrip("#")
        if len(text) != 6:
            raise ValueError(f"expected a 6-digit hex colour, got {value!r}")
        return cls(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))

    def as_hex(self) -> str:
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.red, self.green, self.blue)


class TouchState(Enum):
    """Normalised dual-touch reading."""

    NONE = "none"
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"

    @classmethod
    def from_vendor(cls, value: object) -> "TouchState":
        """Map a ``pidog`` ``dual_touch.read()`` code onto a port value.

        SunFounder reports ``'N'`` for no contact, ``'L'``/``'R'`` for a single
        pad, and ``'LS'``/``'RS'`` for a slide that ends on that pad. A slide is
        still contact on that side, so both collapse to the same state.
        """

        if value is None:
            return cls.NONE
        code = str(value).strip().upper()
        return {
            "": cls.NONE,
            "N": cls.NONE,
            "L": cls.LEFT,
            "LS": cls.LEFT,
            "R": cls.RIGHT,
            "RS": cls.RIGHT,
            "B": cls.BOTH,
            "LR": cls.BOTH,
        }.get(code, cls.NONE)


@dataclass(frozen=True)
class ImuReading:
    """A single inertial measurement sample."""

    acceleration: tuple[float, float, float]
    gyro: tuple[float, float, float]

    def __post_init__(self) -> None:
        for name in ("acceleration", "gyro"):
            values = getattr(self, name)
            if len(values) != 3:
                raise ValueError(f"{name} must have three axes, got {len(values)}")


@dataclass(frozen=True)
class Frame:
    """An encoded camera frame."""

    data: bytes
    width: int
    height: int
    format: str = "jpeg"
    sequence: int = 0

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                f"frame dimensions must be positive, got {self.width}x{self.height}"
            )
        if not self.data:
            raise ValueError("frame data must not be empty")


@runtime_checkable
class MotionPort(Protocol):
    """Motion and posture control. Wraps ``pidog.Pidog``."""

    def do_action(self, action: str, *, steps: int = 1, speed: int = 50) -> None:
        """Queue a named vendor gait or posture, e.g. ``"forward"``."""

    def move_legs(self, angles: Sequence[float], *, speed: int = 50) -> None:
        """Move the eight leg servos to ``angles`` in degrees."""

    def move_head(
        self,
        *,
        yaw: float = 0.0,
        roll: float = 0.0,
        pitch: float = 0.0,
        speed: int = 50,
    ) -> None:
        """Move the head servos to an absolute orientation in degrees."""

    def move_tail(self, angle: float, *, speed: int = 50) -> None:
        """Move the tail servo to an absolute angle in degrees."""

    def wait_all_done(self, timeout: float | None = None) -> None:
        """Block until queued motion drains, or ``timeout`` seconds elapse."""

    def stop(self) -> None:
        """Safe-stop: drop queued motion and hold the current pose."""

    def close(self) -> None:
        """Release the motion resources. Must be idempotent."""


@runtime_checkable
class BoardPort(Protocol):
    """Board-level audio and RGB output. Wraps ``robot_hat`` features."""

    def play_sound(self, name: str, *, volume: int = 100) -> None:
        """Play a bundled or user-supplied sound asset."""

    def set_volume(self, volume: int) -> None:
        """Set the output volume as a percentage in ``[0, 100]``."""

    def set_rgb(
        self,
        *,
        style: str,
        color: RgbColor,
        brightness: float = 1.0,
        speed: int = 50,
    ) -> None:
        """Drive the RGB strip with one of: monochromatic, breath, boom, bark, speak, listen."""

    def clear_rgb(self) -> None:
        """Turn the RGB strip off."""

    def close(self) -> None:
        """Release the board resources. Must be idempotent."""


@runtime_checkable
class CameraPort(Protocol):
    """Camera capture. Wraps ``vilib``."""

    def start(self, *, width: int = 640, height: int = 480) -> None:
        """Start the capture pipeline. Must be idempotent."""

    def capture(self) -> Frame:
        """Return the most recent frame, encoded."""

    def stop(self) -> None:
        """Stop the capture pipeline. Must be idempotent."""

    def is_running(self) -> bool:
        """Report whether capture is currently active."""


@runtime_checkable
class SensorPort(Protocol):
    """Ultrasonic, touch, IMU, and sound-direction reads."""

    def read_distance_cm(self) -> float | None:
        """Distance ahead in centimetres, or ``None`` for an invalid echo."""

    def read_touch(self) -> TouchState:
        """Current dual-touch state."""

    def read_imu(self) -> ImuReading:
        """Latest accelerometer and gyroscope sample."""

    def read_sound_direction(self) -> float | None:
        """Bearing in degrees of the last detected sound, or ``None``."""


@dataclass
class RobotPorts:
    """The full hardware surface a behaviour needs, resolved together."""

    motion: MotionPort
    board: BoardPort
    camera: CameraPort
    sensors: SensorPort
    profile: str = "unknown"
    closed: bool = field(default=False, repr=False)

    def close(self) -> None:
        """Safe-stop motion and release every port. Idempotent.

        Every shutdown step runs even if an earlier one raises, so a failing
        camera cannot leave servos energised. Failures are reported together
        once the robot is safe.
        """

        if self.closed:
            return
        self.closed = True
        errors: list[BaseException] = []
        for shutdown in (
            self.motion.stop,
            self.camera.stop,
            self.board.clear_rgb,
            self.motion.close,
            self.board.close,
        ):
            try:
                shutdown()
            except Exception as error:  # noqa: BLE001 - aggregated and re-raised
                errors.append(error)
        if errors:
            raise HardwareError(
                "errors while closing hardware ports: "
                + "; ".join(f"{type(e).__name__}: {e}" for e in errors)
            )

    def __enter__(self) -> "RobotPorts":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
