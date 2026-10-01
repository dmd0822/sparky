"""Microsoft Foundry vision adapter for the relay downstream port."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen

from .keyless_auth import AzureRelayConfig


def _add_local_shared_contracts_to_path() -> None:
    """Expose the repo-local shared package when callers run outside repo root."""

    for parent in Path(__file__).resolve().parents:
        shared_package = parent / "src" / "shared" / "sparky_contracts" / "__init__.py"
        if shared_package.exists():
            shared_src = str(shared_package.parent.parent)
            if shared_src not in sys.path:
                sys.path.insert(0, shared_src)
            return


try:  # pragma: no cover - installed package path.
    from sparky_contracts import (
        DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
        DEFAULT_PERCEPTION_PROMPT,
        PERCEPTION_STATUS_CONFIG_ERROR,
        PERCEPTION_STATUS_DOWNSTREAM_ERROR,
        PERCEPTION_STATUS_EMPTY_RESPONSE,
        PERCEPTION_STATUS_INVALID_RESPONSE,
        PERCEPTION_STATUS_TIMEOUT,
        PERCEPTION_STATUS_TRANSPORT_ERROR,
        PERCEPTION_STATUS_UNSAFE,
        PerceptionRequest,
        PerceptionResult,
    )
except ImportError:  # pragma: no cover - repo-root test path.
    try:
        from src.shared.sparky_contracts import (
            DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
            DEFAULT_PERCEPTION_PROMPT,
            PERCEPTION_STATUS_CONFIG_ERROR,
            PERCEPTION_STATUS_DOWNSTREAM_ERROR,
            PERCEPTION_STATUS_EMPTY_RESPONSE,
            PERCEPTION_STATUS_INVALID_RESPONSE,
            PERCEPTION_STATUS_TIMEOUT,
            PERCEPTION_STATUS_TRANSPORT_ERROR,
            PERCEPTION_STATUS_UNSAFE,
            PerceptionRequest,
            PerceptionResult,
        )
    except ImportError:  # pragma: no cover - script path outside repo root.
        _add_local_shared_contracts_to_path()
        from sparky_contracts import (
            DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
            DEFAULT_PERCEPTION_PROMPT,
            PERCEPTION_STATUS_CONFIG_ERROR,
            PERCEPTION_STATUS_DOWNSTREAM_ERROR,
            PERCEPTION_STATUS_EMPTY_RESPONSE,
            PERCEPTION_STATUS_INVALID_RESPONSE,
            PERCEPTION_STATUS_TIMEOUT,
            PERCEPTION_STATUS_TRANSPORT_ERROR,
            PERCEPTION_STATUS_UNSAFE,
            PerceptionRequest,
            PerceptionResult,
        )


DEFAULT_VISION_PROMPT = DEFAULT_PERCEPTION_PROMPT
DEFAULT_IMAGE_MEDIA_TYPE = DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE
DEFAULT_TIMEOUT_SECONDS = 20.0


class VisionTransport(Protocol):
    """HTTP transport seam used by the Foundry vision adapter."""

    def send(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        """Send a request and return status plus response bytes."""


class UrlLibVisionTransport:
    """Stdlib HTTP transport for Foundry vision requests."""

    def send(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        request = UrlRequest(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", response.getcode())
                return int(status), response.read()
        except HTTPError as exc:
            return exc.code, exc.read()


class FoundryVisionAdapter:
    """Translate relay vision requests into Foundry chat-completions calls."""

    def __init__(
        self,
        config: AzureRelayConfig,
        transport: VisionTransport | None = None,
        *,
        clock: Callable[[], float] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.config = config
        self.transport = transport or UrlLibVisionTransport()
        self.clock = clock or time.monotonic
        self.timeout_seconds = timeout_seconds

    def vision(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        start = self.clock()
        deployment = self.config.vision_deployment
        if not self.config.foundry_endpoint or not deployment:
            return self._failure(
                status=PERCEPTION_STATUS_CONFIG_ERROR,
                code="vision_not_configured",
                message="Foundry vision endpoint or deployment is not configured.",
                start=start,
                deployment=deployment,
            )

        try:
            body = self._build_request_body(payload)
        except ValueError as exc:
            return self._failure(
                status=PERCEPTION_STATUS_INVALID_RESPONSE,
                code="invalid_request",
                message=str(exc),
                start=start,
                deployment=deployment,
            )

        request_headers = {
            "Authorization": headers["Authorization"],
            "Content-Type": "application/json",
            "x-correlation-id": headers.get("x-correlation-id", ""),
        }
        url = self._request_url()
        try:
            status_code, response_bytes = self.transport.send(
                url,
                json.dumps(body, separators=(",", ":")).encode("utf-8"),
                request_headers,
                self.timeout_seconds,
            )
        except (TimeoutError, socket.timeout):
            return self._failure(
                status=PERCEPTION_STATUS_TIMEOUT,
                code="timeout",
                message="Foundry vision request timed out.",
                start=start,
                deployment=deployment,
            )
        except OSError as exc:
            return self._failure(
                status=PERCEPTION_STATUS_TRANSPORT_ERROR,
                code="transport_error",
                message=f"Foundry vision transport failed: {exc.__class__.__name__}.",
                start=start,
                deployment=deployment,
            )

        if status_code < 200 or status_code >= 300:
            return self._failure(
                status=PERCEPTION_STATUS_DOWNSTREAM_ERROR,
                code="downstream_status",
                message="Foundry vision returned a non-success status.",
                start=start,
                deployment=deployment,
                status_code=status_code,
            )

        try:
            raw = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._failure(
                status=PERCEPTION_STATUS_INVALID_RESPONSE,
                code="invalid_json",
                message="Foundry vision response was not valid JSON.",
                start=start,
                deployment=deployment,
            )

        if not isinstance(raw, Mapping):
            return self._failure(
                status=PERCEPTION_STATUS_INVALID_RESPONSE,
                code="invalid_body",
                message="Foundry vision response must be a JSON object.",
                start=start,
                deployment=deployment,
            )

        usage = _extract_token_usage(raw)
        model = _string_value(raw.get("model"))
        if _is_content_filtered(raw):
            return self._failure(
                status=PERCEPTION_STATUS_UNSAFE,
                code="content_filtered",
                message="Foundry vision response was blocked by safety filtering.",
                start=start,
                deployment=deployment,
                model=model,
                token_usage=usage,
            )

        extracted = _extract_content(raw)
        if extracted is None:
            return self._failure(
                status=PERCEPTION_STATUS_INVALID_RESPONSE,
                code="missing_content",
                message="Foundry vision response did not contain message content.",
                start=start,
                deployment=deployment,
                model=model,
                token_usage=usage,
            )
        caption, labels = extracted
        if not caption.strip() and not labels:
            return self._failure(
                status=PERCEPTION_STATUS_EMPTY_RESPONSE,
                code="empty_result",
                message="Foundry vision response did not include a caption or labels.",
                start=start,
                deployment=deployment,
                model=model,
                token_usage=usage,
            )

        return PerceptionResult.ok(
            caption=caption.strip(),
            labels=labels,
            latency_ms=self._latency_ms(start),
            token_usage=usage,
            model=model,
            deployment=deployment,
        ).as_dict()

    def _build_request_body(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            request = PerceptionRequest.from_dict(payload)
        except ValueError:
            raise ValueError("Vision payload requires base64 image text.")
        prompt = request.prompt or DEFAULT_VISION_PROMPT
        media_type = request.media_type or DEFAULT_IMAGE_MEDIA_TYPE
        return {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt.strip()},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{media_type.strip()};base64,"
                                    f"{request.image_base64.strip()}"
                                )
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 300,
            "temperature": 0,
        }

    def _request_url(self) -> str:
        endpoint = self.config.foundry_endpoint.rstrip("/")
        deployment = quote(self.config.vision_deployment, safe="")
        query = urlencode({"api-version": self.config.vision_api_version})
        return f"{endpoint}/openai/deployments/{deployment}/chat/completions?{query}"

    def _failure(
        self,
        *,
        status: str,
        code: str,
        message: str,
        start: float,
        deployment: str,
        model: str = "",
        status_code: int | None = None,
        token_usage: Mapping[str, int | None] | None = None,
    ) -> Mapping[str, Any]:
        return PerceptionResult.failure(
            status=status,
            code=code,
            message=message,
            latency_ms=self._latency_ms(start),
            deployment=deployment,
            model=model,
            status_code=status_code,
            token_usage=token_usage,
        ).as_dict()

    def _latency_ms(self, start: float) -> int:
        return max(0, round((self.clock() - start) * 1000))


def _extract_content(raw: Mapping[str, Any]) -> tuple[str, list[str]] | None:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    message = first.get("message")
    if not isinstance(message, Mapping):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return _normalize_content_text(content)
    if isinstance(content, list):
        text = "\n".join(
            item.get("text", "") for item in content if isinstance(item, Mapping)
        ).strip()
        if text:
            return _normalize_content_text(text)
    return None


def _normalize_content_text(content: str) -> tuple[str, list[str]]:
    text = content.strip()
    if not text:
        return "", []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, []
    if not isinstance(parsed, Mapping):
        return text, []
    caption = _string_value(parsed.get("caption"))
    labels = [
        item.strip()
        for item in parsed.get("labels", [])
        if isinstance(item, str) and item.strip()
    ] if isinstance(parsed.get("labels"), list) else []
    return caption, labels


def _extract_token_usage(raw: Mapping[str, Any]) -> dict[str, int | None]:
    usage = raw.get("usage")
    if not isinstance(usage, Mapping):
        return {"prompt": None, "completion": None, "total": None}
    return {
        "prompt": _int_value(usage.get("prompt_tokens")),
        "completion": _int_value(usage.get("completion_tokens")),
        "total": _int_value(usage.get("total_tokens")),
    }


def _is_content_filtered(raw: Mapping[str, Any]) -> bool:
    if raw.get("prompt_filter_results"):
        return True
    choices = raw.get("choices")
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        if choice.get("finish_reason") == "content_filter":
            return True
        if _has_filtered_signal(choice.get("content_filter_results")):
            return True
    return False


def _has_filtered_signal(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("filtered") is True:
            return True
        severity = value.get("severity")
        if isinstance(severity, str) and severity.lower() not in ("", "safe"):
            return True
        return any(_has_filtered_signal(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_filtered_signal(item) for item in value)
    return False


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int_value(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
