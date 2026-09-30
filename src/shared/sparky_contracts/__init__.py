"""Shared JSON-friendly contracts for Sparky packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


PERCEPTION_STATUS_OK = "ok"
PERCEPTION_STATUS_CONFIG_ERROR = "config_error"
PERCEPTION_STATUS_DOWNSTREAM_ERROR = "downstream_error"
PERCEPTION_STATUS_EMPTY_RESPONSE = "empty_response"
PERCEPTION_STATUS_INVALID_RESPONSE = "invalid_response"
PERCEPTION_STATUS_TIMEOUT = "timeout"
PERCEPTION_STATUS_TRANSPORT_ERROR = "transport_error"
PERCEPTION_STATUS_UNSAFE = "unsafe_response"


@dataclass(frozen=True)
class PerceptionFailure:
    """Failure details for a normalized perception result."""

    code: str
    message: str
    status_code: int | None = None

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


__all__ = [
    "PERCEPTION_STATUS_CONFIG_ERROR",
    "PERCEPTION_STATUS_DOWNSTREAM_ERROR",
    "PERCEPTION_STATUS_EMPTY_RESPONSE",
    "PERCEPTION_STATUS_INVALID_RESPONSE",
    "PERCEPTION_STATUS_OK",
    "PERCEPTION_STATUS_TIMEOUT",
    "PERCEPTION_STATUS_TRANSPORT_ERROR",
    "PERCEPTION_STATUS_UNSAFE",
    "PerceptionFailure",
    "PerceptionMetadata",
    "PerceptionResult",
]
