"""Planner-facing microphone capture and bounded audio buffering."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from math import ceil, isfinite
from numbers import Real
from threading import RLock
import time
from typing import Any

from ..hardware.ports import (
    AudioChunk,
    HardwareError,
    HardwareUnavailableError,
    MicrophonePort,
    validate_audio_format,
)

__all__ = [
    "AudioBuffer",
    "AudioCapture",
    "AudioFlush",
    "AudioService",
    "AudioServiceState",
    "AudioStatus",
    "CANONICAL_AUDIO_CHANNELS",
    "CANONICAL_AUDIO_SAMPLE_RATE",
    "CANONICAL_AUDIO_SAMPLE_WIDTH",
]

CANONICAL_AUDIO_SAMPLE_RATE = 16000
CANONICAL_AUDIO_CHANNELS = 1
CANONICAL_AUDIO_SAMPLE_WIDTH = 2
DEFAULT_CHUNK_SECONDS = 0.1
DEFAULT_MAX_BUFFER_SECONDS = 5.0


class AudioStatus(Enum):
    """Closed set of audio service outcomes."""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class AudioBuffer:
    """A flushable chunk of normalized PCM ready for an STT request."""

    audio_bytes: bytes
    sample_rate: int
    channels: int
    sample_width: int
    chunk_count: int
    duration_seconds: float
    timestamp: float
    source_id: str
    detail: str | None = None

    def __post_init__(self) -> None:
        validate_audio_format(
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )
        if isinstance(self.chunk_count, bool) or not isinstance(self.chunk_count, int):
            raise ValueError(f"chunk_count must be an int, got {self.chunk_count!r}")
        if self.chunk_count < 0:
            raise ValueError(f"chunk_count must be non-negative, got {self.chunk_count}")
        _validate_non_negative_float(self.duration_seconds, "duration_seconds")
        _validate_timestamp(self.timestamp)
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must not be empty")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs and relay callers."""

        return {
            "audio_base64": base64.b64encode(self.audio_bytes).decode("ascii"),
            "byte_length": len(self.audio_bytes),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width": self.sample_width,
            "chunk_count": self.chunk_count,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "source_id": self.source_id,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AudioCapture:
    """Result of one service-level microphone read."""

    timestamp: float
    status: AudioStatus
    chunk: AudioChunk | None
    buffered_chunks: int = 0
    buffered_bytes: int = 0
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)
        _validate_status(self.status)
        if self.status is AudioStatus.OK:
            if not isinstance(self.chunk, AudioChunk):
                raise ValueError("chunk must be AudioChunk when status is OK")
        elif self.chunk is not None:
            raise ValueError("chunk must be None unless status is OK")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "chunk": None if self.chunk is None else _chunk_as_dict(self.chunk),
            "buffered_chunks": self.buffered_chunks,
            "buffered_bytes": self.buffered_bytes,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AudioFlush:
    """Result of a service buffer flush."""

    timestamp: float
    status: AudioStatus
    audio: AudioBuffer | None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp)
        _validate_status(self.status)
        if self.status is AudioStatus.OK:
            if not isinstance(self.audio, AudioBuffer):
                raise ValueError("audio must be AudioBuffer when status is OK")
        elif self.audio is not None:
            raise ValueError("audio must be None unless status is OK")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation for logs."""

        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "audio": None if self.audio is None else self.audio.as_dict(),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AudioServiceState:
    """Observable lifecycle state for tests and device planners."""

    running: bool = False
    closed: bool = False
    status: AudioStatus = AudioStatus.OK
    detail: str | None = None
    last_capture: AudioCapture | None = None
    buffered_chunks: int = 0
    buffered_bytes: int = 0

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
            "buffered_chunks": self.buffered_chunks,
            "buffered_bytes": self.buffered_bytes,
        }


class AudioService:
    """Own microphone lifecycle, normalize PCM, and keep a bounded buffer."""

    def __init__(
        self,
        microphone: MicrophonePort,
        *,
        source_id: str = "sparky-microphone",
        sample_rate: int = CANONICAL_AUDIO_SAMPLE_RATE,
        channels: int = CANONICAL_AUDIO_CHANNELS,
        sample_width: int = CANONICAL_AUDIO_SAMPLE_WIDTH,
        chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
        max_buffer_seconds: float = DEFAULT_MAX_BUFFER_SECONDS,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._microphone = microphone
        self._source_id = _validate_source_id(source_id)
        self._sample_rate, self._channels, self._sample_width = validate_audio_format(
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        self._chunk_seconds = _validate_positive_float(chunk_seconds, "chunk_seconds")
        self._max_buffer_seconds = _validate_positive_float(
            max_buffer_seconds,
            "max_buffer_seconds",
        )
        self._frames_per_chunk = max(1, int(round(self._sample_rate * self._chunk_seconds)))
        self._chunk_size_bytes = self._frames_per_chunk * self._channels * self._sample_width
        self._max_buffer_chunks = max(
            1,
            int(ceil(self._max_buffer_seconds / self._chunk_seconds)),
        )
        self._time_source = time_source
        self._lock = RLock()
        self._closed = False
        self._buffer: list[bytes] = []
        self._last_capture: AudioCapture | None = None
        self._last_status = AudioStatus.OK
        self._last_detail: str | None = None

    @property
    def state(self) -> AudioServiceState:
        """Return a consistent immutable service snapshot."""

        with self._lock:
            return self._state_unlocked(self._last_status, self._last_detail)

    @property
    def chunk_size_bytes(self) -> int:
        """Canonical bytes requested per microphone chunk."""

        return self._chunk_size_bytes

    def start(self) -> AudioServiceState:
        """Start microphone capture; never raise port errors."""

        with self._lock:
            if self._closed:
                return self._state_unlocked(
                    AudioStatus.UNAVAILABLE,
                    "audio service is closed",
                )
            try:
                if self._microphone.is_open():
                    return self._state_unlocked(AudioStatus.OK, None)
                if not self._microphone.microphone_available():
                    return self._state_unlocked(
                        AudioStatus.UNAVAILABLE,
                        "microphone is not available",
                    )
                self._microphone.open(
                    sample_rate=self._sample_rate,
                    channels=self._channels,
                    sample_width=self._sample_width,
                    frames_per_chunk=self._frames_per_chunk,
                )
                return self._state_unlocked(AudioStatus.OK, None)
            except HardwareUnavailableError as error:
                return self._state_unlocked(AudioStatus.UNAVAILABLE, _detail(error))
            except (HardwareError, TypeError, ValueError) as error:
                return self._state_unlocked(AudioStatus.MALFORMED, _detail(error))
            except Exception as error:  # noqa: BLE001 - vendor faults become status values
                return self._state_unlocked(AudioStatus.UNAVAILABLE, _detail(error))

    def capture_chunk(self) -> AudioCapture:
        """Read, normalize, and buffer one chunk without raising port errors."""

        with self._lock:
            timestamp = self._timestamp()
            if self._closed:
                return self._record_capture_unlocked(
                    AudioCapture(
                        timestamp,
                        AudioStatus.UNAVAILABLE,
                        None,
                        detail="audio service is closed",
                    )
                )
            if not self._is_open_unlocked():
                return self._record_capture_unlocked(
                    AudioCapture(
                        timestamp,
                        AudioStatus.UNAVAILABLE,
                        None,
                        detail="microphone port is not open; call start() first",
                    )
                )
            try:
                raw = self._microphone.read_chunk()
                if not isinstance(raw, AudioChunk):
                    raise ValueError(f"microphone port returned non-AudioChunk {raw!r}")
                normalized = self._normalize_chunk(raw, timestamp=timestamp)
                self._append_buffer_unlocked(normalized.data)
                return self._record_capture_unlocked(
                    AudioCapture(
                        timestamp,
                        AudioStatus.OK,
                        normalized,
                        buffered_chunks=len(self._buffer),
                        buffered_bytes=self._buffered_bytes_unlocked(),
                    )
                )
            except HardwareUnavailableError as error:
                return self._record_capture_unlocked(
                    AudioCapture(timestamp, AudioStatus.UNAVAILABLE, None, detail=_detail(error))
                )
            except (HardwareError, TypeError, ValueError) as error:
                return self._record_capture_unlocked(
                    AudioCapture(timestamp, AudioStatus.MALFORMED, None, detail=_detail(error))
                )
            except Exception as error:  # noqa: BLE001 - vendor faults become status values
                return self._record_capture_unlocked(
                    AudioCapture(timestamp, AudioStatus.UNAVAILABLE, None, detail=_detail(error))
                )

    def flush(self) -> AudioFlush:
        """Return and clear the buffered normalized audio."""

        with self._lock:
            timestamp = self._timestamp()
            audio_bytes = b"".join(self._buffer)
            chunk_count = len(self._buffer)
            self._buffer.clear()
            buffer = AudioBuffer(
                audio_bytes=audio_bytes,
                sample_rate=self._sample_rate,
                channels=self._channels,
                sample_width=self._sample_width,
                chunk_count=chunk_count,
                duration_seconds=_duration_seconds(
                    len(audio_bytes),
                    self._sample_rate,
                    self._channels,
                    self._sample_width,
                ),
                timestamp=timestamp,
                source_id=self._source_id,
            )
            self._last_status = AudioStatus.OK
            self._last_detail = None
            return AudioFlush(timestamp, AudioStatus.OK, buffer)

    def stop(self) -> AudioServiceState:
        """Stop capture; repeated calls are safe and port errors become status."""

        with self._lock:
            try:
                self._microphone.close()
                return self._state_unlocked(AudioStatus.OK, None)
            except HardwareUnavailableError as error:
                return self._state_unlocked(AudioStatus.UNAVAILABLE, _detail(error))
            except (HardwareError, TypeError, ValueError) as error:
                return self._state_unlocked(AudioStatus.MALFORMED, _detail(error))
            except Exception as error:  # noqa: BLE001 - vendor faults become status values
                return self._state_unlocked(AudioStatus.UNAVAILABLE, _detail(error))

    def close(self) -> AudioServiceState:
        """Stop capture and release service ownership. Idempotent."""

        with self._lock:
            state = self.stop()
            self._closed = True
            return AudioServiceState(
                running=False,
                closed=True,
                status=state.status,
                detail=state.detail,
                last_capture=self._last_capture,
                buffered_chunks=len(self._buffer),
                buffered_bytes=self._buffered_bytes_unlocked(),
            )

    def _normalize_chunk(self, chunk: AudioChunk, *, timestamp: float) -> AudioChunk:
        frames = _decode_pcm(chunk.data, chunk.sample_width, chunk.channels)
        frames = _convert_channels(frames, self._channels)
        frames = _resample_frames(frames, chunk.sample_rate, self._sample_rate)
        data = _encode_pcm(frames, self._sample_width)
        return AudioChunk(
            data=data,
            sample_rate=self._sample_rate,
            channels=self._channels,
            sample_width=self._sample_width,
            timestamp=timestamp,
            sequence=chunk.sequence,
        )

    def _append_buffer_unlocked(self, data: bytes) -> None:
        self._buffer.append(data)
        while len(self._buffer) > self._max_buffer_chunks:
            self._buffer.pop(0)

    def _record_capture_unlocked(self, capture: AudioCapture) -> AudioCapture:
        self._last_capture = capture
        self._last_status = capture.status
        self._last_detail = capture.detail
        return capture

    def _state_unlocked(
        self,
        status: AudioStatus,
        detail: str | None,
    ) -> AudioServiceState:
        self._last_status = status
        self._last_detail = detail
        return AudioServiceState(
            running=self._is_open_unlocked(),
            closed=self._closed,
            status=status,
            detail=detail,
            last_capture=self._last_capture,
            buffered_chunks=len(self._buffer),
            buffered_bytes=self._buffered_bytes_unlocked(),
        )

    def _is_open_unlocked(self) -> bool:
        try:
            return bool(self._microphone.is_open())
        except Exception:
            return False

    def _buffered_bytes_unlocked(self) -> int:
        return sum(len(chunk) for chunk in self._buffer)

    def _timestamp(self) -> float:
        return _validate_timestamp(self._time_source())


def _chunk_as_dict(chunk: AudioChunk) -> dict[str, object]:
    return {
        "audio_base64": base64.b64encode(chunk.data).decode("ascii"),
        "byte_length": len(chunk.data),
        "sample_rate": chunk.sample_rate,
        "channels": chunk.channels,
        "sample_width": chunk.sample_width,
        "timestamp": chunk.timestamp,
        "sequence": chunk.sequence,
    }


def _decode_pcm(data: bytes, sample_width: int, channels: int) -> list[list[float]]:
    frame_width = sample_width * channels
    if len(data) % frame_width != 0:
        raise ValueError("audio length does not align to complete frames")
    frames: list[list[float]] = []
    signed_max = float((1 << (sample_width * 8 - 1)) - 1)
    for offset in range(0, len(data), frame_width):
        frame: list[float] = []
        for channel in range(channels):
            start = offset + channel * sample_width
            sample = data[start : start + sample_width]
            if sample_width == 1:
                value = sample[0] - 128
                frame.append(max(-1.0, min(1.0, value / 128.0)))
            else:
                value = int.from_bytes(sample, "little", signed=True)
                frame.append(max(-1.0, min(1.0, value / signed_max)))
        frames.append(frame)
    return frames


def _convert_channels(frames: list[list[float]], channels: int) -> list[list[float]]:
    converted: list[list[float]] = []
    for frame in frames:
        if len(frame) == channels:
            converted.append(frame)
            continue
        mono = sum(frame) / len(frame)
        converted.append([mono] * channels)
    return converted


def _resample_frames(
    frames: list[list[float]],
    sample_rate: int,
    target_rate: int,
) -> list[list[float]]:
    if sample_rate == target_rate or not frames:
        return frames
    target_count = max(1, int(round(len(frames) * target_rate / sample_rate)))
    if len(frames) == 1:
        return [frames[0] for _ in range(target_count)]
    channels = len(frames[0])
    resampled: list[list[float]] = []
    for index in range(target_count):
        position = index * (len(frames) - 1) / max(1, target_count - 1)
        left = int(position)
        right = min(left + 1, len(frames) - 1)
        fraction = position - left
        resampled.append(
            [
                frames[left][channel] * (1.0 - fraction)
                + frames[right][channel] * fraction
                for channel in range(channels)
            ]
        )
    return resampled


def _encode_pcm(frames: list[list[float]], sample_width: int) -> bytes:
    output = bytearray()
    signed_max = (1 << (sample_width * 8 - 1)) - 1
    signed_min = -(1 << (sample_width * 8 - 1))
    for frame in frames:
        for value in frame:
            clamped = max(-1.0, min(1.0, value))
            if sample_width == 1:
                output.append(max(0, min(255, int(round(clamped * 127 + 128)))))
            else:
                sample = max(signed_min, min(signed_max, int(round(clamped * signed_max))))
                output.extend(sample.to_bytes(sample_width, "little", signed=True))
    return bytes(output)


def _duration_seconds(
    byte_length: int,
    sample_rate: int,
    channels: int,
    sample_width: int,
) -> float:
    if byte_length == 0:
        return 0.0
    return byte_length / float(sample_rate * channels * sample_width)


def _detail(error: BaseException) -> str:
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _validate_source_id(source_id: str) -> str:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must not be empty")
    return source_id


def _validate_status(status: AudioStatus) -> None:
    if not isinstance(status, AudioStatus):
        raise ValueError(f"status must be AudioStatus, got {status!r}")


def _validate_timestamp(timestamp: Any) -> float:
    value = _validate_non_negative_float(timestamp, "timestamp")
    return value


def _validate_positive_float(value: Any, label: str) -> float:
    number = _validate_float(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive, got {value!r}")
    return number


def _validate_non_negative_float(value: Any, label: str) -> float:
    number = _validate_float(value, label)
    if number < 0:
        raise ValueError(f"{label} must be non-negative, got {value!r}")
    return number


def _validate_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number, got {value!r}")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return number
