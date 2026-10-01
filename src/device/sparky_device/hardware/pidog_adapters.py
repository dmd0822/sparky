"""Thin adapters that bind the hardware ports to the SunFounder libraries.

Nothing here imports ``pidog``, ``robot_hat``, ``vilib`` or ``cv2`` at module
scope, so this module is importable on a CI runner. Vendor imports happen
inside :func:`load_pidog` and :func:`load_vilib`, which raise
:class:`HardwareUnavailableError` with an actionable message when the packages
are missing.

Each adapter is deliberately shallow: translate arguments, call the vendor,
normalise the return value. Behaviour belongs in application code above the
ports, so a vendor API change is a single-file edit here.
"""

from __future__ import annotations

import threading
import time
import subprocess
import shutil
from typing import Any, Sequence

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
    validate_audio_format,
    validate_camera_resolution,
    validate_rgb_style,
    TouchState,
    validate_angles,
    validate_action_name,
    validate_speed,
)

__all__ = [
    "PIDOG_PROFILE",
    "PidogBoardAdapter",
    "PidogMicrophoneAdapter",
    "PidogMotionAdapter",
    "PidogSensorAdapter",
    "VilibCameraAdapter",
    "build_pidog_ports",
    "load_pidog",
    "load_vilib",
    "vendor_libraries_available",
]

PIDOG_PROFILE = "pidog"

#: ``read_distance()`` reports a negative sentinel when the echo is invalid.
_INVALID_DISTANCE = 0.0
_CAMERA_FIRST_FRAME_TIMEOUT_SECONDS = 2.0
_CAMERA_FRAME_POLL_INTERVAL_SECONDS = 0.05
_ARECORD_FIRST_READ_TIMEOUT_SECONDS = 0.05


def load_pidog() -> Any:
    """Import and construct ``pidog.Pidog``.

    Raises:
        HardwareUnavailableError: the package is missing or the board did not
            initialise (no I2C, no power, wrong Pi model).
    """

    try:
        from pidog import Pidog  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - requires a non-Pi host
        raise HardwareUnavailableError(
            "the 'pidog' package is not installed. Install the SunFounder "
            "libraries on the Raspberry Pi, or set SPARKY_HARDWARE=simulator "
            "to run against the simulators."
        ) from error
    try:
        return Pidog()
    except Exception as error:  # pragma: no cover - requires real hardware
        raise HardwareUnavailableError(
            f"could not initialise the PiDog board: {error}"
        ) from error


def load_vilib() -> Any:
    """Import ``vilib.Vilib``."""

    try:
        from vilib import Vilib  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - requires a non-Pi host
        raise HardwareUnavailableError(
            "the 'vilib' package is not installed. Install the SunFounder "
            "libraries on the Raspberry Pi, or set SPARKY_HARDWARE=simulator "
            "to run against the simulators."
        ) from error
    except Exception as error:  # pragma: no cover - requires camera hardware
        raise HardwareUnavailableError(
            "the 'vilib' package is installed but could not initialise the "
            "camera. Check the camera ribbon and run "
            "'rpicam-hello --list-cameras' on the Raspberry Pi."
        ) from error
    return Vilib


def vendor_libraries_available() -> bool:
    """Report whether ``pidog`` and ``vilib`` can be imported.

    This only checks importability; it does not touch the board, so it is safe
    to call during start-up probing.
    """

    from importlib.util import find_spec

    try:
        return all(find_spec(name) is not None for name in ("pidog", "vilib"))
    except (ImportError, ValueError):  # pragma: no cover - broken installs
        return False


class PidogMotionAdapter:
    """Binds :class:`~sparky_device.hardware.ports.MotionPort` to ``Pidog``."""

    def __init__(self, dog: Any, limits: MotionLimits = DEFAULT_LIMITS) -> None:
        self._dog = dog
        self.limits = limits
        self._closed = False

    def do_action(self, action: str, *, steps: int = 1, speed: int = 50) -> None:
        action = validate_action_name(action)
        if steps < 1:
            raise HardwareError(f"steps must be at least 1, got {steps}")
        self._dog.do_action(
            action, step_count=steps, speed=validate_speed(speed, self.limits)
        )

    def move_legs(self, angles: Sequence[float], *, speed: int = 50) -> None:
        checked = validate_angles(
            angles, count=LEG_JOINT_COUNT, servo_range=self.limits.leg, group="legs"
        )
        self._dog.legs_move([list(checked)], speed=validate_speed(speed, self.limits))

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
        self._dog.head_move([list(checked)], speed=validate_speed(speed, self.limits))

    def move_tail(self, angle: float, *, speed: int = 50) -> None:
        checked = validate_angles(
            (angle,), count=1, servo_range=self.limits.tail, group="tail"
        )
        self._dog.tail_move([list(checked)], speed=validate_speed(speed, self.limits))

    def wait_all_done(self, timeout: float | None = None) -> None:
        if timeout is None:
            self._dog.wait_all_done()
            return
        if timeout < 0:
            raise HardwareError(f"timeout must be non-negative, got {timeout}")

        errors: list[BaseException] = []

        def wait_for_vendor() -> None:
            try:
                self._dog.wait_all_done()
            except BaseException as error:  # pragma: no cover - defensive handoff
                errors.append(error)

        worker = threading.Thread(target=wait_for_vendor, daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            self._dog.body_stop()
            raise HardwareError(
                f"timed out waiting for motion to finish after {timeout:g} seconds"
            )
        if errors:
            raise errors[0]

    def stop(self) -> None:
        self._dog.body_stop()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._dog.close()


class PidogBoardAdapter:
    """Binds the board port to ``robot_hat`` features exposed through ``Pidog``."""

    def __init__(self, dog: Any) -> None:
        self._dog = dog
        self._volume = 100
        self._closed = False

    @staticmethod
    def _check_volume(volume: int) -> int:
        if not 0 <= volume <= 100:
            raise HardwareError(f"volume must be between 0 and 100, got {volume}")
        return int(volume)

    def play_sound(self, name: str, *, volume: int = 100) -> None:
        if not name or not name.strip():
            raise HardwareError("sound name must not be empty")
        self._dog.speak(name, self._check_volume(volume))

    def set_volume(self, volume: int) -> None:
        self._volume = self._check_volume(volume)
        music = getattr(self._dog, "music", None)
        setter = getattr(music, "music_set_volume", None)
        if setter is not None:
            setter(self._volume)

    def set_rgb(
        self,
        *,
        style: str,
        color: RgbColor,
        brightness: float = 1.0,
        speed: int = 50,
    ) -> None:
        style = validate_rgb_style(style)
        if not 0.0 <= brightness <= 1.0:
            raise HardwareError(
                f"brightness must be between 0.0 and 1.0, got {brightness}"
            )
        if style == "monochromatic":
            # Vendor monochromatic() omits the int cast used by other styles;
            # pre-scale so float brightness never reaches the LED driver.
            scaled_color = [
                max(0, min(255, int(channel * brightness)))
                for channel in color.as_tuple()
            ]
            self._dog.rgb_strip.set_mode(
                style=style,
                color=scaled_color,
                bps=max(speed, 1) / 50.0,
                brightness=1,
            )
            return
        self._dog.rgb_strip.set_mode(
            style=style,
            color=color.as_hex(),
            bps=max(speed, 1) / 50.0,
            brightness=brightness,
        )

    def clear_rgb(self) -> None:
        self._dog.rgb_strip.close()

    def close(self) -> None:
        self._closed = True


class PidogSensorAdapter:
    """Binds the sensor port to the PiDog ultrasonic, touch, IMU, and ears."""

    def __init__(self, dog: Any) -> None:
        self._dog = dog

    def read_distance_cm(self) -> float | None:
        raw = self._dog.read_distance()
        if raw is None:
            return None
        distance = float(raw)
        # SunFounder returns a negative sentinel for a timed-out echo.
        return distance if distance > _INVALID_DISTANCE else None

    def read_touch(self) -> TouchState:
        return TouchState.from_vendor(self._dog.dual_touch.read())

    def read_imu(self) -> ImuReading:
        acceleration = tuple(float(v) for v in self._dog.accData)
        gyro = tuple(float(v) for v in self._dog.gyroData)
        if len(acceleration) != 3 or len(gyro) != 3:
            raise HardwareError(
                "IMU returned an unexpected shape: "
                f"acc={acceleration!r} gyro={gyro!r}"
            )
        return ImuReading(acceleration=acceleration, gyro=gyro)

    def read_sound_direction(self) -> float | None:
        ears = self._dog.ears
        if not ears.isdetected():
            return None
        return float(ears.read())


class VilibCameraAdapter:
    """Binds the camera port to ``vilib``, encoding frames as JPEG."""

    def __init__(
        self,
        vilib: Any | None = None,
        *,
        vflip: bool = False,
        hflip: bool = False,
        first_frame_timeout: float = _CAMERA_FIRST_FRAME_TIMEOUT_SECONDS,
        frame_poll_interval: float = _CAMERA_FRAME_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._vilib = vilib
        self._vilib_injected = vilib is not None
        self._vflip = vflip
        self._hflip = hflip
        self._first_frame_timeout = first_frame_timeout
        self._frame_poll_interval = frame_poll_interval
        self._running = False
        self._sequence = 0
        self.width = 0
        self.height = 0

    def _library(self) -> Any:
        if self._vilib is None:
            self._vilib = load_vilib()
        return self._vilib

    def start(self, *, width: int = 640, height: int = 480) -> None:
        width, height = validate_camera_resolution(width, height)
        if self._running:
            return
        library = self._library()
        try:
            library.camera_start(vflip=self._vflip, hflip=self._hflip)
        except Exception:
            # camera_start may spawn vendor work before surfacing an error, so
            # always ask vilib to tear down even though this adapter is not running.
            try:
                library.camera_close()
            except Exception:
                pass
            raise
        self._running = True
        self.width = width
        self.height = height

    def capture(self) -> Frame:
        if not self._running:
            raise HardwareError("camera port is not running; call start() first")
        image = self._wait_for_frame()
        data, width, height = _encode_jpeg(image)
        self._sequence += 1
        return Frame(
            data=data,
            width=width,
            height=height,
            format="jpeg",
            sequence=self._sequence,
        )

    def _wait_for_frame(self) -> Any:
        deadline = time.monotonic() + self._first_frame_timeout
        while True:
            image = getattr(self._library(), "img", None)
            if image is not None:
                return image
            if time.monotonic() >= deadline:
                raise HardwareError(
                    "vilib has not produced a frame yet. Vilib starts the camera "
                    "asynchronously; this usually means no camera is attached or "
                    "the ribbon cable is loose. Run "
                    "'rpicam-hello --list-cameras' on the Raspberry Pi to confirm."
                )
            time.sleep(self._frame_poll_interval)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._library().camera_close()

    def is_running(self) -> bool:
        return self._running

    def camera_available(self) -> bool:
        probe = _rpicam_detects_camera()
        if probe is not None:
            return probe
        try:
            self._library()
        except HardwareUnavailableError:
            return False
        # camera_start() fails asynchronously, so a clean import alone cannot
        # prove physical availability unless a test double was injected.
        return self._vilib_injected


class PidogMicrophoneAdapter:
    """Binds the microphone port to ALSA ``arecord`` raw PCM capture."""

    def __init__(
        self,
        *,
        executable: str = "arecord",
        first_read_timeout: float = _ARECORD_FIRST_READ_TIMEOUT_SECONDS,
    ) -> None:
        self._executable = executable
        self._first_read_timeout = first_read_timeout
        self._process: subprocess.Popen[bytes] | None = None
        self._bytes_per_chunk = 0
        self._sample_rate = 0
        self._channels = 0
        self._sample_width = 0
        self._sequence = 0

    def open(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        frames_per_chunk: int = 1600,
    ) -> None:
        sample_rate, channels, sample_width = validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        if frames_per_chunk <= 0:
            raise HardwareError(
                f"frames_per_chunk must be positive, got {frames_per_chunk}"
            )
        if self._process is not None and self._process.poll() is None:
            return
        if shutil.which(self._executable) is None:
            raise HardwareUnavailableError(
                "ALSA 'arecord' is not installed or not on PATH. Install ALSA "
                "utilities on the Raspberry Pi, or set SPARKY_HARDWARE=simulator."
            )
        command = [
            self._executable,
            "-q",
            "-t",
            "raw",
            "-f",
            _arecord_format(sample_width),
            "-r",
            str(sample_rate),
            "-c",
            str(channels),
            "-",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as error:  # pragma: no cover - depends on host PATH
            raise HardwareUnavailableError(
                "ALSA 'arecord' is not installed or not on PATH."
            ) from error
        except OSError as error:  # pragma: no cover - requires host audio state
            raise HardwareUnavailableError(f"could not start microphone capture: {error}") from error
        time.sleep(self._first_read_timeout)
        if process.poll() is not None:
            _, stderr = process.communicate(timeout=1)
            _raise_arecord_failure(stderr.decode("utf-8", errors="replace"))
        self._process = process
        self._bytes_per_chunk = int(frames_per_chunk) * channels * sample_width
        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width = sample_width
        self._sequence = 0

    def read_chunk(self) -> AudioChunk:
        process = self._process
        if process is None or process.stdout is None or process.poll() is not None:
            raise HardwareError("microphone port is not open; call open() first")
        data = process.stdout.read(self._bytes_per_chunk)
        if not data:
            stderr = b""
            if process.stderr is not None:
                try:
                    stderr = process.stderr.read()
                except Exception:
                    stderr = b""
            _raise_arecord_failure(stderr.decode("utf-8", errors="replace"))
        self._sequence += 1
        return AudioChunk(
            data=data,
            sample_rate=self._sample_rate,
            channels=self._channels,
            sample_width=self._sample_width,
            timestamp=time.monotonic(),
            sequence=self._sequence,
        )

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    def is_open(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def microphone_available(self) -> bool:
        if shutil.which(self._executable) is None:
            return False
        try:
            completed = subprocess.run(
                [self._executable, "-l"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return False
        output = f"{completed.stdout}\n{completed.stderr}".lower()
        if "no soundcards" in output or "no hardware devices" in output:
            return False
        return completed.returncode == 0


def _rpicam_detects_camera() -> bool | None:
    """Probe camera presence without starting vilib's asynchronous pipeline."""

    try:
        completed = subprocess.run(
            ["rpicam-hello", "--list-cameras"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    output = f"{completed.stdout}\n{completed.stderr}".lower()
    if "no cameras available" in output:
        return False
    if completed.returncode == 0 and output.strip():
        return True
    return None


def _arecord_format(sample_width: int) -> str:
    if sample_width == 1:
        return "U8"
    if sample_width == 2:
        return "S16_LE"
    if sample_width == 4:
        return "S32_LE"
    raise HardwareError(f"unsupported sample_width for arecord: {sample_width}")


def _raise_arecord_failure(stderr: str) -> None:
    message = stderr.strip() or "arecord produced no microphone audio"
    lowered = message.lower()
    if "device or resource busy" in lowered or "busy" in lowered:
        raise HardwareError(f"microphone device is busy: {message}")
    if (
        "no such file" in lowered
        or "no soundcards" in lowered
        or "cannot find card" in lowered
        or "not found" in lowered
    ):
        raise HardwareUnavailableError(f"microphone device is unavailable: {message}")
    raise HardwareError(f"microphone capture failed: {message}")


def _encode_jpeg(image: Any) -> tuple[bytes, int, int]:
    """Encode a ``vilib`` BGR frame to JPEG bytes."""

    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - requires a non-Pi host
        raise HardwareUnavailableError(
            "OpenCV ('cv2') is required to encode camera frames; it ships with "
            "the SunFounder vilib install."
        ) from error
    ok, buffer = cv2.imencode(".jpg", image)
    if not ok:
        raise HardwareError("failed to encode the camera frame as JPEG")
    height, width = image.shape[0], image.shape[1]
    return bytes(buffer), int(width), int(height)


def build_pidog_ports(
    *,
    dog: Any | None = None,
    vilib: Any | None = None,
    limits: MotionLimits = DEFAULT_LIMITS,
) -> RobotPorts:
    """Assemble a :class:`RobotPorts` bundle backed by real hardware.

    ``dog`` and ``vilib`` are injectable so adapter contract tests can run
    against recording doubles without importing the vendor packages.
    """

    robot = dog if dog is not None else load_pidog()
    return RobotPorts(
        motion=PidogMotionAdapter(robot, limits=limits),
        board=PidogBoardAdapter(robot),
        camera=VilibCameraAdapter(vilib),
        microphone=PidogMicrophoneAdapter(),
        sensors=PidogSensorAdapter(robot),
        profile=PIDOG_PROFILE,
    )
