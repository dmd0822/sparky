"""Shared JSON-friendly contracts for Sparky packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


PERCEPTION_CONTRACT_VERSION = "1.0"

DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE = "image/jpeg"
DEFAULT_PERCEPTION_PROMPT = (
    "Analyze this Sparky camera frame. Return compact JSON with a string "
    "caption and an array of short label strings."
)
PERCEPTION_PROMPT_NORMAL_SCENE = (
    "Describe the visible scene for Sparky's behavior planner. Prefer concrete "
    "objects, people, obstacles, and room context."
)
PERCEPTION_PROMPT_AMBIGUOUS_SCENE = (
    "Describe only what can be seen with confidence. If the frame is blurry, "
    "dark, or ambiguous, say so and use sparse labels."
)
PERCEPTION_PROMPT_FAILURE_SCENE = (
    "When the image cannot be analyzed safely or reliably, return an explicit "
    "failure status with concise failure details."
)
SAMPLE_PERCEPTION_PROMPTS = {
    "normal_scene": PERCEPTION_PROMPT_NORMAL_SCENE,
    "ambiguous_scene": PERCEPTION_PROMPT_AMBIGUOUS_SCENE,
    "failed_scene": PERCEPTION_PROMPT_FAILURE_SCENE,
}

PERCEPTION_STATUS_OK = "ok"
PERCEPTION_STATUS_CONFIG_ERROR = "config_error"
PERCEPTION_STATUS_DOWNSTREAM_ERROR = "downstream_error"
PERCEPTION_STATUS_EMPTY_RESPONSE = "empty_response"
PERCEPTION_STATUS_INVALID_RESPONSE = "invalid_response"
PERCEPTION_STATUS_TIMEOUT = "timeout"
PERCEPTION_STATUS_TRANSPORT_ERROR = "transport_error"
PERCEPTION_STATUS_UNSAFE = "unsafe_response"


@dataclass(frozen=True)
class PerceptionRequest:
    """Stable relay-facing request shape for image perception.

    Device camera packaging stays local to the device package. This DTO is the
    narrower shared contract the relay already understands: base64 image bytes,
    prompt text, media type, an optional correlation id, and optional source
    metadata that callers may use for tracing without changing the relay's
    required ``image`` field.
    """

    image_base64: str
    media_type: str = DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE
    prompt: str | None = DEFAULT_PERCEPTION_PROMPT
    correlation_id: str | None = None
    source_id: str | None = None
    sequence: int | None = None
    timestamp: float | None = None
    source_width: int | None = None
    source_height: int | None = None

    def __post_init__(self) -> None:
        image = _required_string(self.image_base64, "image_base64")
        object.__setattr__(self, "image_base64", image)
        object.__setattr__(
            self,
            "media_type",
            _optional_string(self.media_type) or DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
        )
        object.__setattr__(
            self,
            "prompt",
            _optional_string(self.prompt) or DEFAULT_PERCEPTION_PROMPT,
        )
        object.__setattr__(self, "correlation_id", _optional_string(self.correlation_id))
        object.__setattr__(self, "source_id", _optional_string(self.source_id))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PerceptionRequest":
        if not isinstance(payload, Mapping):
            raise ValueError("PerceptionRequest payload must be a mapping.")
        source = payload.get("source")
        source_payload = source if isinstance(source, Mapping) else {}
        return cls(
            image_base64=_string_field(payload, "image")
            or _string_field(payload, "image_base64"),
            media_type=(
                _string_field(payload, "media_type")
                or _string_field(payload, "image_media_type")
                or DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE
            ),
            prompt=_string_field(payload, "prompt") or DEFAULT_PERCEPTION_PROMPT,
            correlation_id=_string_field(payload, "correlation_id"),
            source_id=_string_field(source_payload, "source_id")
            or _string_field(payload, "source_id"),
            sequence=_int_field(source_payload, "sequence")
            if "sequence" in source_payload
            else _int_field(payload, "sequence"),
            timestamp=_float_field(source_payload, "timestamp")
            if "timestamp" in source_payload
            else _float_field(payload, "timestamp"),
            source_width=_int_field(source_payload, "source_width")
            if "source_width" in source_payload
            else _int_field(payload, "source_width"),
            source_height=_int_field(source_payload, "source_height")
            if "source_height" in source_payload
            else _int_field(payload, "source_height"),
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "image": self.image_base64,
            "prompt": self.prompt,
            "media_type": self.media_type,
        }
        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id
        source = _omit_none(
            {
                "source_id": self.source_id,
                "sequence": self.sequence,
                "timestamp": self.timestamp,
                "source_width": self.source_width,
                "source_height": self.source_height,
            }
        )
        if source:
            payload["source"] = source
        return payload


@dataclass(frozen=True)
class PerceptionFailure:
    """Failure details for a normalized perception result."""

    code: str
    message: str
    status_code: int | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PerceptionFailure":
        if not isinstance(payload, Mapping):
            raise ValueError("PerceptionFailure payload must be a mapping.")
        return cls(
            code=_required_string(_string_field(payload, "code"), "code"),
            message=_required_string(_string_field(payload, "message"), "message"),
            status_code=_int_field(payload, "status_code"),
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


@dataclass(frozen=True)
class PerceptionMetadata:
    """Observability fields attached to a perception result."""

    latency_ms: int
    token_usage: Mapping[str, int | None] = field(default_factory=dict)
    model: str = ""
    deployment: str = ""
    failure: PerceptionFailure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "token_usage", _normalise_token_usage(self.token_usage))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PerceptionMetadata":
        if not isinstance(payload, Mapping):
            raise ValueError("PerceptionMetadata payload must be a mapping.")
        failure_payload = payload.get("failure")
        return cls(
            latency_ms=_int_field(payload, "latency_ms") or 0,
            token_usage=_token_usage_payload(payload.get("token_usage")),
            model=_string_field(payload, "model") or "",
            deployment=_string_field(payload, "deployment") or "",
            failure=PerceptionFailure.from_dict(failure_payload)
            if isinstance(failure_payload, Mapping)
            else None,
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "latency_ms": self.latency_ms,
            "token_usage": {
                "prompt": self.token_usage.get("prompt"),
                "completion": self.token_usage.get("completion"),
                "total": self.token_usage.get("total"),
            },
            "model": self.model,
            "deployment": self.deployment,
        }
        if self.failure is not None:
            payload["failure"] = self.failure.as_dict()
        return payload


@dataclass(frozen=True)
class PerceptionResult:
    """Stable device-facing perception response."""

    caption: str
    labels: tuple[str, ...]
    status: str
    metadata: PerceptionMetadata
    correlation_id: str | None = None

    @classmethod
    def ok(
        cls,
        *,
        caption: str,
        labels: list[str] | tuple[str, ...],
        latency_ms: int,
        token_usage: Mapping[str, int | None],
        model: str,
        deployment: str,
    ) -> "PerceptionResult":
        return cls(
            caption=caption,
            labels=tuple(labels),
            status=PERCEPTION_STATUS_OK,
            metadata=PerceptionMetadata(
                latency_ms=latency_ms,
                token_usage=token_usage,
                model=model,
                deployment=deployment,
            ),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PerceptionResult":
        if not isinstance(payload, Mapping):
            raise ValueError("PerceptionResult payload must be a mapping.")
        labels = payload.get("labels", ())
        if not isinstance(labels, (list, tuple)):
            labels = ()
        metadata = payload.get("metadata")
        return cls(
            caption=_string_field(payload, "caption") or "",
            labels=tuple(item for item in labels if isinstance(item, str)),
            status=_string_field(payload, "status") or PERCEPTION_STATUS_OK,
            metadata=PerceptionMetadata.from_dict(metadata)
            if isinstance(metadata, Mapping)
            else PerceptionMetadata(latency_ms=0),
            correlation_id=_string_field(payload, "correlation_id"),
        )

    @classmethod
    def failure(
        cls,
        *,
        status: str,
        code: str,
        message: str,
        latency_ms: int,
        deployment: str,
        model: str = "",
        status_code: int | None = None,
        token_usage: Mapping[str, int | None] | None = None,
    ) -> "PerceptionResult":
        return cls(
            caption="",
            labels=(),
            status=status,
            metadata=PerceptionMetadata(
                latency_ms=latency_ms,
                token_usage=token_usage or {},
                model=model,
                deployment=deployment,
                failure=PerceptionFailure(code=code, message=message, status_code=status_code),
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "caption": self.caption,
            "labels": list(self.labels),
            "status": self.status,
            "metadata": self.metadata.as_dict(),
        }
        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id
        return payload

    def to_payload(self) -> dict[str, Any]:
        return self.as_dict()


<<<<<<< HEAD
=======
@dataclass(frozen=True)
class ConversationTurnTimings:
    """Per-leg conversation latency measurements in monotonic-clock seconds.

    A value of ``None`` means the leg did not run. Completed and failed turns use
    the same shape so operators can tune capture, STT, chat, TTS, and playback
    independently without confusing an unrun leg with a zero-duration leg.
    """

    audio_capture_seconds: float | None = None
    stt_seconds: float | None = None
    chat_seconds: float | None = None
    tts_seconds: float | None = None
    playback_seconds: float | None = None
    total_seconds: float | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "audio_capture_seconds",
            "stt_seconds",
            "chat_seconds",
            "tts_seconds",
            "playback_seconds",
            "total_seconds",
        ):
            object.__setattr__(self, field_name, _optional_non_negative_float(getattr(self, field_name), field_name))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConversationTurnTimings":
        if not isinstance(payload, Mapping):
            raise ValueError("ConversationTurnTimings payload must be a mapping.")
        return cls(
            audio_capture_seconds=_float_field(payload, "audio_capture_seconds"),
            stt_seconds=_float_field(payload, "stt_seconds"),
            chat_seconds=_float_field(payload, "chat_seconds"),
            tts_seconds=_float_field(payload, "tts_seconds"),
            playback_seconds=_float_field(payload, "playback_seconds"),
            total_seconds=_float_field(payload, "total_seconds"),
        )

    def as_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "audio_capture_seconds": self.audio_capture_seconds,
                "stt_seconds": self.stt_seconds,
                "chat_seconds": self.chat_seconds,
                "tts_seconds": self.tts_seconds,
                "playback_seconds": self.playback_seconds,
                "total_seconds": self.total_seconds,
            }
        )


>>>>>>> main
def _omit_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_field(payload: Mapping[str, Any], key: str) -> str | None:
    return _optional_string(payload.get(key))


def _int_field(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float_field(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


<<<<<<< HEAD
=======
def _optional_non_negative_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a non-negative number or None.")
    number = float(value)
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return number


>>>>>>> main
def _token_usage_payload(value: Any) -> Mapping[str, int | None]:
    return value if isinstance(value, Mapping) else {}


def _normalise_token_usage(value: Mapping[str, int | None]) -> dict[str, int | None]:
    return {
        "prompt": _token_int(value.get("prompt")),
        "completion": _token_int(value.get("completion")),
        "total": _token_int(value.get("total")),
    }


def _token_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = [
    "DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE",
    "DEFAULT_PERCEPTION_PROMPT",
    "PERCEPTION_CONTRACT_VERSION",
    "PERCEPTION_PROMPT_AMBIGUOUS_SCENE",
    "PERCEPTION_PROMPT_FAILURE_SCENE",
    "PERCEPTION_PROMPT_NORMAL_SCENE",
    "PERCEPTION_STATUS_CONFIG_ERROR",
    "PERCEPTION_STATUS_DOWNSTREAM_ERROR",
    "PERCEPTION_STATUS_EMPTY_RESPONSE",
    "PERCEPTION_STATUS_INVALID_RESPONSE",
    "PERCEPTION_STATUS_OK",
    "PERCEPTION_STATUS_TIMEOUT",
    "PERCEPTION_STATUS_TRANSPORT_ERROR",
    "PERCEPTION_STATUS_UNSAFE",
    "SAMPLE_PERCEPTION_PROMPTS",
<<<<<<< HEAD
=======
    "ConversationTurnTimings",
>>>>>>> main
    "PerceptionFailure",
    "PerceptionMetadata",
    "PerceptionRequest",
    "PerceptionResult",
]
