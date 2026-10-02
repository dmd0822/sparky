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
from math import isfinite
from numbers import Real
from typing import Final, Protocol, Sequence, runtime_checkable

__all__ = [
    "AUDIO_MAX_CHANNELS",
    "AUDIO_SAMPLE_WIDTHS",
    "AudioChunk",
    "BoardPort",
    "CameraPort",
    "DEFAULT_LIMITS",
    "Frame",
    "HardwareError",
    "HardwareUnavailableError",
    "HEAD_JOINT_COUNT",
    "ImuReading",
    "LEG_JOINT_COUNT",
    "MicrophonePort",
    "MOTION_ACTIONS",
    "MotionLimits",
    "MotionPort",
    "RgbColor",
    "RGB_STYLES",
    "RobotPorts",
    "SensorPort",
    "ServoRange",
    "SpeakerPort",
    "TouchState",
    "VILIB_CAPTURE_SIZE",
    "validate_angles",
    "validate_action_name",
    "validate_audio_format",
    "validate_camera_resolution",
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

AUDIO_SAMPLE_WIDTHS: Final[tuple[int, ...]] = (1, 2, 4)
_AUDIO_SAMPLE_WIDTH_SET: Final[frozenset[int]] = frozenset(AUDIO_SAMPLE_WIDTHS)
AUDIO_MAX_CHANNELS: Final[int] = 8


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

VILIB_CAPTURE_SIZE: Final[tuple[int, int]] = (640, 480)
_VILIB_CAPTURE_SIZE_SET: Final[frozenset[tuple[int, int]]] = frozenset(
    (VILIB_CAPTURE_SIZE,)
)

MOTION_ACTIONS: Final[tuple[str, ...]] = (
    "stand",
    "sit",
    "lie",
    "lie_with_hands_out",
    "half_sit",
    "forward",
    "backward",
    "turn_left",
    "turn_right",
    "trot",
    "stretch",
    "push_up",
    "doze_off",
    "nod_lethargy",
    "shake_head",
    "tilting_head_left",
    "tilting_head_right",
    "tilting_head",
    "head_bark",
    "wag_tail",
    "head_up_down",
)
_MOTION_ACTION_SET: Final[frozenset[str]] = frozenset(MOTION_ACTIONS)
_MOTION_ACTION_CASEFOLD: Final[dict[str, str]] = {
    action.casefold(): action for action in MOTION_ACTIONS
}


def validate_rgb_style(style: str) -> str:
    """Return ``style`` unchanged, or raise :class:`HardwareError`."""

    if style not in _RGB_STYLE_SET:
        raise HardwareError(
            f"RGB style {style!r} is invalid; expected one of: "
            + ", ".join(RGB_STYLES)
        )
    return style


def validate_action_name(action: str) -> str:
    """Return the normalised vendor motion action, or raise :class:`HardwareError`."""

    if not action or not action.strip():
        raise HardwareError("action name must not be empty")
    normalised = action.replace(" ", "_")
    if normalised not in _MOTION_ACTION_SET:
        suggestion = _MOTION_ACTION_CASEFOLD.get(normalised.casefold())
        message = (
            f"motion action {action!r} is invalid; expected one of: "
            + ", ".join(MOTION_ACTIONS)
        )
        if suggestion is not None:
            message += f"; did you mean {suggestion!r}?"
        raise HardwareError(message)
    return normalised


def validate_camera_resolution(width: int, height: int) -> tuple[int, int]:
    """Return the native camera resolution, or raise :class:`HardwareError`."""

    if width <= 0 or height <= 0:
        raise HardwareError(
            f"capture dimensions must be positive, got {width}x{height}"
        )
    resolution = (width, height)
    if resolution not in _VILIB_CAPTURE_SIZE_SET:
        native_width, native_height = VILIB_CAPTURE_SIZE
        # A wrong resolution is a code defect, unlike an absent camera
        # environment condition, so fail loudly before any side effect.
        raise HardwareError(
            "vilib fixes capture at "
            f"{native_width}x{native_height}; requested {width}x{height} "
            "cannot be honoured"
        )
    return (int(width), int(height))


def validate_speed(speed: int, limits: MotionLimits = DEFAULT_LIMITS) -> int:
    """Return ``speed`` unchanged, or raise :class:`HardwareError`."""

    if not limits.speed.contains(speed):
        raise HardwareError(
            f"speed {speed} is outside the safe range "
            f"[{limits.speed.minimum}, {limits.speed.maximum}]"
        )
    return int(speed)


def validate_audio_format(
    *,
    sample_rate: int,
    channels: int,
    sample_width: int,
) -> tuple[int, int, int]:
    """Validate PCM audio shape shared by microphone adapters and simulators."""

    for name, value in (
        ("sample_rate", sample_rate),
        ("channels", channels),
        ("sample_width", sample_width),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise HardwareError(f"{name} must be an int, got {value!r}")
    if sample_rate <= 0:
        raise HardwareError(f"sample_rate must be positive, got {sample_rate}")
    if not 1 <= channels <= AUDIO_MAX_CHANNELS:
        raise HardwareError(
            f"channels must be between 1 and {AUDIO_MAX_CHANNELS}, got {channels}"
        )
    if sample_width not in _AUDIO_SAMPLE_WIDTH_SET:
        raise HardwareError(
            f"sample_width must be one of {AUDIO_SAMPLE_WIDTHS}, got {sample_width}"
        )
    return (sample_rate, channels, sample_width)


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
    # The current SunFounder DualTouch implementation does not emit a
    # simultaneous-contact code; keep BOTH as a stable port value for simulators
    # and forward-compatible vendor firmware that might add one later.
    BOTH = "both"

    @classmethod
    def from_vendor(cls, value: object) -> "TouchState":
        """Map a ``pidog`` ``dual_touch.read()`` code onto a port value.

        SunFounder reports ``'N'`` for no contact, ``'L'``/``'R'`` for a single
        pad, and ``'LS'``/``'RS'`` for a slide that ends on that pad. A slide is
        still contact on that side, so both collapse to the same state. The
        current vendor source does not return a simultaneous-touch code; ``'B'``
        and ``'LR'`` are accepted only for forward-compatible firmware or tests.
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


@dataclass(frozen=True)
class AudioChunk:
    """A chunk of interleaved PCM microphone audio."""

    data: bytes
    sample_rate: int
    channels: int = 1
    sample_width: int = 2
    timestamp: float = 0.0
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError("audio chunk data must not be empty")
        validate_audio_format(
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )
        frame_width = self.channels * self.sample_width
        if len(self.data) % frame_width != 0:
            raise ValueError(
                "audio chunk data length must align to complete frames "
                f"({frame_width} bytes), got {len(self.data)}"
            )
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, Real):
            raise ValueError(f"timestamp must be a finite number, got {self.timestamp!r}")
        if not isfinite(float(self.timestamp)) or float(self.timestamp) < 0:
            raise ValueError(f"timestamp must be a finite non-negative number, got {self.timestamp!r}")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError(f"sequence must be an int, got {self.sequence!r}")
        if self.sequence < 0:
            raise ValueError(f"sequence must be non-negative, got {self.sequence}")


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
        """Start the capture pipeline at vilib's fixed 640x480 resolution."""

    def capture(self) -> Frame:
        """Return the most recent frame, encoded."""

    def stop(self) -> None:
        """Stop the capture pipeline. Must be idempotent."""

    def is_running(self) -> bool:
        """Report whether capture is currently active."""

    def camera_available(self) -> bool:
        """Report whether a usable camera appears to be present."""


@runtime_checkable
class MicrophonePort(Protocol):
    """Microphone capture. Produces interleaved PCM chunks."""

    def open(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        frames_per_chunk: int = 1600,
    ) -> None:
        """Open capture for the requested PCM shape and chunk size."""

    def read_chunk(self) -> AudioChunk:
        """Return the next microphone PCM chunk."""

    def close(self) -> None:
        """Release microphone capture resources. Must be idempotent."""

    def is_open(self) -> bool:
        """Report whether microphone capture is currently open."""

    def microphone_available(self) -> bool:
        """Report whether a microphone appears to be present."""


@runtime_checkable
class SpeakerPort(Protocol):
    """Speaker playback. Accepts raw PCM or encoded audio bytes."""

    def open(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> None:
        """Open playback for the requested PCM shape."""

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
        """Play PCM or encoded audio bytes with explicit format metadata."""

    def stop(self) -> None:
        """Stop any active playback. Must be idempotent."""

    def close(self) -> None:
        """Release speaker playback resources. Must be idempotent."""

    def is_open(self) -> bool:
        """Report whether speaker playback is currently open."""

    def speaker_available(self) -> bool:
        """Report whether a speaker appears to be present."""


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
    microphone: MicrophonePort | None = None
    speaker: SpeakerPort | None = None
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
        shutdown_steps = [
            self.motion.stop,
            self.camera.stop,
            self.board.clear_rgb,
            self.motion.close,
            self.board.close,
        ]
        if self.microphone is not None:
            shutdown_steps.insert(2, self.microphone.close)
        if self.speaker is not None:
            shutdown_steps.insert(3, self.speaker.close)
        for shutdown in shutdown_steps:
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
