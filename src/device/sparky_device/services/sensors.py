"""Normalised sensor readings for the device loop.

``SensorPort`` deliberately stays close to the hardware adapter: ultrasonic and
sound-direction reads can return ``None`` for ordinary "no value this tick"
conditions, while unhealthy hardware may raise. This service turns that mixed
boundary into a stable planner/logging contract. Every read returns a
timestamped value object with an explicit status, so behaviour code can record
or react to a failed sensor without crashing the device loop.

Semantics for value absence are intentionally narrow: ``ReadingStatus.OK`` with
``None`` distance means the ultrasonic echo timed out for this tick, and
``ReadingStatus.OK`` with ``None`` sound direction means no sound was detected.
``ReadingStatus.UNAVAILABLE`` is reserved for missing or failing hardware, and
``ReadingStatus.MALFORMED`` means the port returned a shape or type outside the
contract. No port exception escapes this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real
from threading import RLock
import time
from typing import Any

from ..hardware.ports import (
    HardwareError,
    HardwareUnavailableError,
    ImuReading as HardwareImuReading,
    SensorPort,
    TouchState,
)

__all__ = [
    "DistanceReading",
    "ImuSensorReading",
    "ReadingStatus",
    "SensorService",
    "SensorServiceState",
    "SensorSnapshot",
    "SoundDirectionReading",
    "TouchReading",
]


class ReadingStatus(Enum):
    """Closed set of sensor read outcomes."""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class DistanceReading:
    """Timestamped ultrasonic distance sample in centimetres."""

    timestamp: float
    status: ReadingStatus
    distance_cm: float | None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)
        _validate_status(self.status)
        if self.status is not ReadingStatus.OK and self.distance_cm is not None:
            raise ValueError("distance_cm must be None unless status is OK")
        if self.distance_cm is not None:
            _validate_distance(self.distance_cm)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "distance_cm": self.distance_cm,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TouchReading:
    """Timestamped dual-touch sample."""

    timestamp: float
    status: ReadingStatus
    touch: TouchState | None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)
        _validate_status(self.status)
        if self.status is ReadingStatus.OK:
            if not isinstance(self.touch, TouchState):
                raise ValueError("touch must be a TouchState when status is OK")
        elif self.touch is not None:
            raise ValueError("touch must be None unless status is OK")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "touch": None if self.touch is None else self.touch.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ImuSensorReading:
    """Timestamped accelerometer and gyroscope sample."""

    timestamp: float
    status: ReadingStatus
    imu: HardwareImuReading | None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)
        _validate_status(self.status)
        if self.status is ReadingStatus.OK:
            if not isinstance(self.imu, HardwareImuReading):
                raise ValueError("imu must be an ImuReading when status is OK")
        elif self.imu is not None:
            raise ValueError("imu must be None unless status is OK")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "acceleration": None if self.imu is None else self.imu.acceleration,
            "gyro": None if self.imu is None else self.imu.gyro,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SoundDirectionReading:
    """Timestamped sound bearing sample in degrees."""

    timestamp: float
    status: ReadingStatus
    direction_degrees: float | None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)
        _validate_status(self.status)
        if self.status is not ReadingStatus.OK and self.direction_degrees is not None:
            raise ValueError("direction_degrees must be None unless status is OK")
        if self.direction_degrees is not None:
            _validate_float(self.direction_degrees, "direction_degrees")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "direction_degrees": self.direction_degrees,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SensorSnapshot:
    """All sensor groups read during one device-loop tick."""

    timestamp: float
    distance: DistanceReading
    touch: TouchReading
    imu: ImuSensorReading
    sound_direction: SoundDirectionReading

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "timestamp": self.timestamp,
            "distance": self.distance.as_dict(),
            "touch": self.touch.as_dict(),
            "imu": self.imu.as_dict(),
            "sound_direction": self.sound_direction.as_dict(),
        }


@dataclass(frozen=True)
class SensorServiceState:
    """Observable service state for planners and tests."""

    closed: bool = False
    last_snapshot: SensorSnapshot | None = None


class SensorService:
    """Read and normalise an injected :class:`SensorPort`."""

    def __init__(
        self,
        sensors: SensorPort,
        *,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sensors = sensors
        # Monotonic time is the right default for a robot loop: elapsed ordering
        # matters more than wall-clock corrections from NTP or an operator.
        self._time_source = time_source
        self._lock = RLock()
        self._closed = False
        self._last_snapshot: SensorSnapshot | None = None

    @property
    def state(self) -> SensorServiceState:
        """Return a consistent immutable service snapshot."""

        with self._lock:
            return SensorServiceState(
                closed=self._closed,
                last_snapshot=self._last_snapshot,
            )

    def read_distance(self) -> DistanceReading:
        """Read ultrasonic distance without letting port errors escape."""

        with self._lock:
            if self._closed:
                return DistanceReading(
                    timestamp=self._timestamp(),
                    status=ReadingStatus.UNAVAILABLE,
                    distance_cm=None,
                    detail="sensor service is closed",
                )
            return self._read_distance_unlocked()

    def read_touch(self) -> TouchReading:
        """Read dual-touch state without letting port errors escape."""

        with self._lock:
            if self._closed:
                return TouchReading(
                    timestamp=self._timestamp(),
                    status=ReadingStatus.UNAVAILABLE,
                    touch=None,
                    detail="sensor service is closed",
                )
            return self._read_touch_unlocked()

    def read_imu(self) -> ImuSensorReading:
        """Read IMU state without letting port errors escape."""

        with self._lock:
            if self._closed:
                return ImuSensorReading(
                    timestamp=self._timestamp(),
                    status=ReadingStatus.UNAVAILABLE,
                    imu=None,
                    detail="sensor service is closed",
                )
            return self._read_imu_unlocked()

    def read_sound_direction(self) -> SoundDirectionReading:
        """Read sound direction without letting port errors escape."""

        with self._lock:
            if self._closed:
                return SoundDirectionReading(
                    timestamp=self._timestamp(),
                    status=ReadingStatus.UNAVAILABLE,
                    direction_degrees=None,
                    detail="sensor service is closed",
                )
            return self._read_sound_direction_unlocked()

    def read_snapshot(self) -> SensorSnapshot:
        """Read all sensor groups for one device-loop tick."""

        with self._lock:
            if self._closed:
                snapshot = self._closed_snapshot_unlocked()
            else:
                distance = self._read_distance_unlocked()
                touch = self._read_touch_unlocked()
                imu = self._read_imu_unlocked()
                sound_direction = self._read_sound_direction_unlocked()
                snapshot = SensorSnapshot(
                    timestamp=self._timestamp(),
                    distance=distance,
                    touch=touch,
                    imu=imu,
                    sound_direction=sound_direction,
                )
            self._last_snapshot = snapshot
            return snapshot

    def close(self) -> None:
        """Release service ownership. Idempotent."""

        with self._lock:
            self._closed = True

    def _closed_snapshot_unlocked(self) -> SensorSnapshot:
        timestamp = self._timestamp()
        return SensorSnapshot(
            timestamp=timestamp,
            distance=DistanceReading(
                timestamp=timestamp,
                status=ReadingStatus.UNAVAILABLE,
                distance_cm=None,
                detail="sensor service is closed",
            ),
            touch=TouchReading(
                timestamp=timestamp,
                status=ReadingStatus.UNAVAILABLE,
                touch=None,
                detail="sensor service is closed",
            ),
            imu=ImuSensorReading(
                timestamp=timestamp,
                status=ReadingStatus.UNAVAILABLE,
                imu=None,
                detail="sensor service is closed",
            ),
            sound_direction=SoundDirectionReading(
                timestamp=timestamp,
                status=ReadingStatus.UNAVAILABLE,
                direction_degrees=None,
                detail="sensor service is closed",
            ),
        )

    def _read_distance_unlocked(self) -> DistanceReading:
        timestamp = self._timestamp()
        try:
            raw = self._sensors.read_distance_cm()
            value = None if raw is None else _validate_distance(raw)
            detail = "no ultrasonic echo this tick" if value is None else None
            return DistanceReading(timestamp, ReadingStatus.OK, value, detail)
        except HardwareUnavailableError as error:
            return DistanceReading(
                timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error)
            )
        except (HardwareError, TypeError, ValueError) as error:
            return DistanceReading(timestamp, ReadingStatus.MALFORMED, None, _detail(error))
        except Exception as error:  # noqa: BLE001 - vendor faults become status values
            return DistanceReading(
                timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error)
            )

    def _read_touch_unlocked(self) -> TouchReading:
        timestamp = self._timestamp()
        try:
            value = self._sensors.read_touch()
            if not isinstance(value, TouchState):
                raise ValueError(f"touch must be TouchState, got {value!r}")
            return TouchReading(timestamp, ReadingStatus.OK, value)
        except HardwareUnavailableError as error:
            return TouchReading(timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error))
        except (HardwareError, TypeError, ValueError) as error:
            return TouchReading(timestamp, ReadingStatus.MALFORMED, None, _detail(error))
        except Exception as error:  # noqa: BLE001 - vendor faults become status values
            return TouchReading(timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error))

    def _read_imu_unlocked(self) -> ImuSensorReading:
        timestamp = self._timestamp()
        try:
            value = self._sensors.read_imu()
            if not isinstance(value, HardwareImuReading):
                raise ValueError(f"imu must be ImuReading, got {value!r}")
            return ImuSensorReading(timestamp, ReadingStatus.OK, value)
        except HardwareUnavailableError as error:
            return ImuSensorReading(
                timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error)
            )
        except (HardwareError, TypeError, ValueError) as error:
            return ImuSensorReading(timestamp, ReadingStatus.MALFORMED, None, _detail(error))
        except Exception as error:  # noqa: BLE001 - vendor faults become status values
            return ImuSensorReading(
                timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error)
            )

    def _read_sound_direction_unlocked(self) -> SoundDirectionReading:
        timestamp = self._timestamp()
        try:
            raw = self._sensors.read_sound_direction()
            value = None if raw is None else _validate_float(raw, "direction_degrees")
            detail = "no sound detected this tick" if value is None else None
            return SoundDirectionReading(timestamp, ReadingStatus.OK, value, detail)
        except HardwareUnavailableError as error:
            return SoundDirectionReading(
                timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error)
            )
        except (HardwareError, TypeError, ValueError) as error:
            return SoundDirectionReading(
                timestamp, ReadingStatus.MALFORMED, None, _detail(error)
            )
        except Exception as error:  # noqa: BLE001 - vendor faults become status values
            return SoundDirectionReading(
                timestamp, ReadingStatus.UNAVAILABLE, None, _detail(error)
            )

    def _timestamp(self) -> float:
        return _validate_float(self._time_source(), "timestamp")


def _detail(error: BaseException) -> str:
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _validate_status(status: ReadingStatus) -> None:
    if not isinstance(status, ReadingStatus):
        raise ValueError(f"status must be ReadingStatus, got {status!r}")


def _validate_timestamp(timestamp: float) -> None:
    value = _validate_float(timestamp, "timestamp")
    if value < 0:
        raise ValueError(f"timestamp must be non-negative, got {timestamp!r}")


def _validate_distance(value: Any) -> float:
    distance = _validate_float(value, "distance_cm")
    if distance < 0:
        raise ValueError(f"distance_cm must be non-negative, got {distance}")
    return distance


def _validate_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number, got {value!r}")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return number
