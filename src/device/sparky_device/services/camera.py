"""Planner-facing camera capture and frame packaging.

The camera port intentionally mirrors the hardware: ``vilib`` can only deliver
native 640x480 frames, and it may be absent on a perfectly valid PiDog bench.
The relay, however, needs a stable submission shape that records where an image
came from, when it was captured, what dimensions the hardware produced, and what
dimensions were actually packaged for upload.

This service is that boundary. It owns the camera lifecycle for application
code, converts hardware faults into explicit status values, and packages frames
without asking the port to pretend it can resize. When a caller requests a
smaller upload image the service lazily tries Pillow if it is available; CI and
off-robot development do not install Pillow, OpenCV, NumPy, or ``vilib``, so a
missing or unusable image stack simply preserves the original bytes and records
the actual packaged dimensions honestly.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from math import isfinite
from numbers import Real
from threading import RLock
import time
from typing import Any

from ..hardware.ports import (
    CameraPort,
    Frame,
    HardwareError,
    HardwareUnavailableError,
    VILIB_CAPTURE_SIZE,
)

__all__ = [
    "CameraCapture",
    "CameraService",
    "CameraServiceState",
    "CameraStatus",
    "PackagedFrame",
]


class CameraStatus(Enum):
    """Closed set of camera service outcomes."""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class PackagedFrame:
    """A captured frame ready for JSON relay submission or structured logs."""

    image_bytes: bytes
    source_width: int
    source_height: int
    packaged_width: int
    packaged_height: int
    format: str
    sequence: int
    timestamp: float
    source_id: str
    resized: bool = False
    detail: str | None = None

    def __post_init__(self) -> None:
        if not self.image_bytes:
            raise ValueError("image_bytes must not be empty")
        _validate_dimensions(self.source_width, self.source_height, "source")
        _validate_dimensions(self.packaged_width, self.packaged_height, "packaged")
        if not self.format or not self.format.strip():
            raise ValueError("format must not be empty")
        if self.sequence < 0:
            raise ValueError(f"sequence must be non-negative, got {self.sequence}")
        _validate_timestamp(self.timestamp)
        if not self.source_id or not self.source_id.strip():
            raise ValueError("source_id must not be empty")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for relay submission."""

        return {
            "image_base64": base64.b64encode(self.image_bytes).decode("ascii"),
            "byte_length": len(self.image_bytes),
            "source_width": self.source_width,
            "source_height": self.source_height,
            "packaged_width": self.packaged_width,
            "packaged_height": self.packaged_height,
            "format": self.format,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "source_id": self.source_id,
            "resized": self.resized,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CameraCapture:
    """Result of one service-level capture attempt."""

    timestamp: float
    status: CameraStatus
    frame: PackagedFrame | None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)
        _validate_status(self.status)
        if self.status is CameraStatus.OK:
            if not isinstance(self.frame, PackagedFrame):
                raise ValueError("frame must be PackagedFrame when status is OK")
        elif self.frame is not None:
            raise ValueError("frame must be None unless status is OK")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs and relay callers."""

        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "frame": None if self.frame is None else self.frame.as_dict(),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CameraServiceState:
    """Observable lifecycle state for tests and device planners."""

    running: bool = False
    closed: bool = False
    status: CameraStatus = CameraStatus.OK
    detail: str | None = None
    last_capture: CameraCapture | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "running": self.running,
            "closed": self.closed,
            "status": self.status.value,
            "detail": self.detail,
            "last_capture": None
            if self.last_capture is None
            else self.last_capture.as_dict(),
        }


class CameraService:
    """Own camera lifecycle and package captured frames above ``CameraPort``."""

    def __init__(
        self,
        camera: CameraPort,
        *,
        source_id: str = "sparky-camera",
        target_width: int | None = None,
        target_height: int | None = None,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._camera = camera
        self._source_id = _validate_source_id(source_id)
        self._target_width, self._target_height = _normalise_target_dimensions(
            target_width,
            target_height,
        )
        self._time_source = time_source
        self._lock = RLock()
        self._closed = False
        self._last_capture: CameraCapture | None = None
        self._last_status = CameraStatus.OK
        self._last_detail: str | None = None

    @property
    def state(self) -> CameraServiceState:
        """Return a consistent immutable service snapshot."""

        with self._lock:
            return CameraServiceState(
                running=self._is_running_unlocked(),
                closed=self._closed,
                status=self._last_status,
                detail=self._last_detail,
                last_capture=self._last_capture,
            )

    def start(self) -> CameraServiceState:
        """Start capture when a camera is available; never raise port errors."""

        with self._lock:
            if self._closed:
                return self._state_unlocked(
                    CameraStatus.UNAVAILABLE,
                    "camera service is closed",
                )
            try:
                if self._camera.is_running():
                    return self._state_unlocked(CameraStatus.OK, None)
                if not self._camera.camera_available():
                    return self._state_unlocked(
                        CameraStatus.UNAVAILABLE,
                        "camera is not available",
                    )
                width, height = VILIB_CAPTURE_SIZE
                try:
                    self._camera.start(width=width, height=height)
                except Exception:
                    self._stop_after_failed_start_unlocked()
                    raise
                return self._state_unlocked(CameraStatus.OK, None)
            except HardwareUnavailableError as error:
                return self._state_unlocked(
                    CameraStatus.UNAVAILABLE,
                    _detail(error),
                )
            except (HardwareError, TypeError, ValueError) as error:
                return self._state_unlocked(CameraStatus.MALFORMED, _detail(error))
            except Exception as error:  # noqa: BLE001 - vendor faults become status values
                return self._state_unlocked(
                    CameraStatus.UNAVAILABLE,
                    _detail(error),
                )

    def capture_frame(self) -> CameraCapture:
        """Capture and package one frame without letting port errors escape."""

        with self._lock:
            timestamp = self._timestamp()
            if self._closed:
                return self._record_capture_unlocked(
                    CameraCapture(
                        timestamp,
                        CameraStatus.UNAVAILABLE,
                        None,
                        "camera service is closed",
                    )
                )
            if not self._is_running_unlocked():
                return self._record_capture_unlocked(
                    CameraCapture(
                        timestamp,
                        CameraStatus.UNAVAILABLE,
                        None,
                        "camera port is not running; call start() first",
                    )
                )
            try:
                frame = self._camera.capture()
                if not isinstance(frame, Frame):
                    raise ValueError(f"camera port returned non-Frame {frame!r}")
                packaged = self._package_frame(frame, timestamp=timestamp)
                return self._record_capture_unlocked(
                    CameraCapture(timestamp, CameraStatus.OK, packaged, packaged.detail)
                )
            except HardwareUnavailableError as error:
                return self._record_capture_unlocked(
                    CameraCapture(
                        timestamp,
                        CameraStatus.UNAVAILABLE,
                        None,
                        _detail(error),
                    )
                )
            except (HardwareError, TypeError, ValueError) as error:
                return self._record_capture_unlocked(
                    CameraCapture(timestamp, CameraStatus.MALFORMED, None, _detail(error))
                )
            except Exception as error:  # noqa: BLE001 - vendor faults become status values
                return self._record_capture_unlocked(
                    CameraCapture(
                        timestamp,
                        CameraStatus.UNAVAILABLE,
                        None,
                        _detail(error),
                    )
                )

    def stop(self) -> CameraServiceState:
        """Stop capture; repeated calls are safe and port errors become status."""

        with self._lock:
            try:
                self._camera.stop()
                return self._state_unlocked(CameraStatus.OK, None)
            except HardwareUnavailableError as error:
                return self._state_unlocked(
                    CameraStatus.UNAVAILABLE,
                    _detail(error),
                )
            except (HardwareError, TypeError, ValueError) as error:
                return self._state_unlocked(CameraStatus.MALFORMED, _detail(error))
            except Exception as error:  # noqa: BLE001 - vendor faults become status values
                return self._state_unlocked(
                    CameraStatus.UNAVAILABLE,
                    _detail(error),
                )

    def close(self) -> CameraServiceState:
        """Stop capture and release service ownership. Idempotent."""

        with self._lock:
            state = self.stop()
            self._closed = True
            return CameraServiceState(
                running=False,
                closed=True,
                status=state.status,
                detail=state.detail,
                last_capture=self._last_capture,
            )

    def _package_frame(self, frame: Frame, *, timestamp: float) -> PackagedFrame:
        target_width = self._target_width or frame.width
        target_height = self._target_height or frame.height
        if (target_width, target_height) == (frame.width, frame.height):
            return PackagedFrame(
                image_bytes=frame.data,
                source_width=frame.width,
                source_height=frame.height,
                packaged_width=frame.width,
                packaged_height=frame.height,
                format=frame.format,
                sequence=frame.sequence,
                timestamp=timestamp,
                source_id=self._source_id,
            )
        resized = _try_resize_frame(frame, target_width, target_height)
        return PackagedFrame(
            image_bytes=resized.data,
            source_width=frame.width,
            source_height=frame.height,
            packaged_width=resized.width,
            packaged_height=resized.height,
            format=resized.format,
            sequence=frame.sequence,
            timestamp=timestamp,
            source_id=self._source_id,
            resized=resized.resized,
            detail=resized.detail,
        )

    def _record_capture_unlocked(self, capture: CameraCapture) -> CameraCapture:
        self._last_capture = capture
        self._last_status = capture.status
        self._last_detail = capture.detail
        return capture

    def _state_unlocked(
        self,
        status: CameraStatus,
        detail: str | None,
    ) -> CameraServiceState:
        self._last_status = status
        self._last_detail = detail
        return CameraServiceState(
            running=self._is_running_unlocked(),
            closed=self._closed,
            status=status,
            detail=detail,
            last_capture=self._last_capture,
        )

    def _is_running_unlocked(self) -> bool:
        try:
            return bool(self._camera.is_running())
        except Exception:
            return False

    def _stop_after_failed_start_unlocked(self) -> None:
        try:
            self._camera.stop()
        except Exception:
            return

    def _timestamp(self) -> float:
        return _validate_float(self._time_source(), "timestamp")


@dataclass(frozen=True)
class _ResizeResult:
    data: bytes
    width: int
    height: int
    format: str
    resized: bool
    detail: str | None = None


def _try_resize_frame(frame: Frame, target_width: int, target_height: int) -> _ResizeResult:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception as error:  # noqa: BLE001 - optional image stack is best-effort
        return _ResizeResult(
            frame.data,
            frame.width,
            frame.height,
            frame.format,
            False,
            f"optional resize unavailable; packaged original frame: {_detail(error)}",
        )

    try:
        with Image.open(BytesIO(frame.data)) as image:
            image = image.resize((target_width, target_height))
            output = BytesIO()
            image_format = (
                "JPEG"
                if frame.format.lower() in {"jpg", "jpeg"}
                else frame.format.upper()
            )
            image.save(output, format=image_format)
        return _ResizeResult(
            output.getvalue(),
            target_width,
            target_height,
            frame.format,
            True,
        )
    except Exception as error:  # noqa: BLE001 - optional image stack may reject fixtures
        return _ResizeResult(
            frame.data,
            frame.width,
            frame.height,
            frame.format,
            False,
            f"optional resize failed; packaged original frame: {_detail(error)}",
        )


def _detail(error: BaseException) -> str:
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _normalise_target_dimensions(
    width: int | None,
    height: int | None,
) -> tuple[int | None, int | None]:
    if width is None and height is None:
        return (None, None)
    if width is None or height is None:
        raise ValueError("target_width and target_height must be supplied together")
    _validate_dimensions(width, height, "target")
    return (int(width), int(height))


def _validate_dimensions(width: int, height: int, label: str) -> None:
    if isinstance(width, bool) or isinstance(height, bool):
        raise ValueError(f"{label} dimensions must be ints, got {width!r}x{height!r}")
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError(f"{label} dimensions must be ints, got {width!r}x{height!r}")
    if width <= 0 or height <= 0:
        raise ValueError(f"{label} dimensions must be positive, got {width}x{height}")


def _validate_source_id(source_id: str) -> str:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must not be empty")
    return source_id


def _validate_status(status: CameraStatus) -> None:
    if not isinstance(status, CameraStatus):
        raise ValueError(f"status must be CameraStatus, got {status!r}")


def _validate_timestamp(timestamp: float) -> None:
    value = _validate_float(timestamp, "timestamp")
    if value < 0:
        raise ValueError(f"timestamp must be non-negative, got {timestamp!r}")


def _validate_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number, got {value!r}")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return number
