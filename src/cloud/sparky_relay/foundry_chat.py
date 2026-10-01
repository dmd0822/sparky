"""Microsoft Foundry chat adapter for the relay downstream port."""

from __future__ import annotations

import json
import socket
import time
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen

from .keyless_auth import AzureRelayConfig


DEFAULT_TIMEOUT_SECONDS = 20.0


class ChatTransport(Protocol):
    """HTTP transport seam used by the Foundry chat adapter."""

    def send(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        """Send a request and return status plus response bytes."""


class UrlLibChatTransport:
    """Stdlib HTTP transport for Foundry chat requests."""

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


class FoundryChatAdapter:
    """Translate relay chat requests into Foundry chat-completions calls."""

    def __init__(
        self,
        config: AzureRelayConfig,
        transport: ChatTransport | None = None,
        *,
        clock: Callable[[], float] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.config = config
        self.transport = transport or UrlLibChatTransport()
        self.clock = clock or time.monotonic
        self.timeout_seconds = timeout_seconds

    def chat(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        start = self.clock()
        deployment = self.config.chat_deployment
        if not self.config.foundry_endpoint or not deployment:
            return self._failure(
                code="chat_not_configured",
                message="Foundry chat endpoint or deployment is not configured.",
                start=start,
                deployment=deployment,
            )

        try:
            body = self._build_request_body(payload)
        except ValueError as exc:
            return self._failure(
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
        try:
            status_code, response_bytes = self.transport.send(
                self._request_url(),
                json.dumps(body, separators=(",", ":")).encode("utf-8"),
                request_headers,
                self.timeout_seconds,
            )
        except (TimeoutError, socket.timeout):
            return self._failure(
                code="timeout",
                message="Foundry chat request timed out.",
                start=start,
                deployment=deployment,
            )
        except OSError as exc:
            return self._failure(
                code="transport_error",
                message=f"Foundry chat transport failed: {exc.__class__.__name__}.",
                start=start,
                deployment=deployment,
            )

        if status_code < 200 or status_code >= 300:
            return self._failure(
                code="downstream_status",
                message="Foundry chat returned a non-success status.",
                start=start,
                deployment=deployment,
                status_code=status_code,
            )

        try:
            raw = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._failure(
                code="invalid_json",
                message="Foundry chat response was not valid JSON.",
                start=start,
                deployment=deployment,
            )

        if not isinstance(raw, Mapping):
            return self._failure(
                code="invalid_body",
                message="Foundry chat response must be a JSON object.",
                start=start,
                deployment=deployment,
            )

        usage = _extract_token_usage(raw)
        model = _string_value(raw.get("model"))
        if _is_content_filtered(raw):
            return self._failure(
                code="content_filtered",
                message="Foundry chat response was blocked by safety filtering.",
                start=start,
                deployment=deployment,
                model=model,
                token_usage=usage,
            )

        content = _extract_content(raw)
        if content is None:
            return self._failure(
                code="missing_content",
                message="Foundry chat response did not contain message content.",
                start=start,
                deployment=deployment,
                model=model,
                token_usage=usage,
            )
        if not content.strip():
            return self._failure(
                code="empty_result",
                message="Foundry chat response did not include a reply.",
                start=start,
                deployment=deployment,
                model=model,
                token_usage=usage,
            )
        return {"reply": content.strip(), "metadata": self._metadata(start, deployment, model, usage)}

    def _build_request_body(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Chat payload requires prompt text.")
        messages: list[dict[str, str]] = []
        system = payload.get("system")
        if isinstance(system, str) and system.strip():
            messages.append({"role": "system", "content": system.strip()})
        messages.append({"role": "user", "content": prompt.strip()})
        return {"messages": messages}

    def _request_url(self) -> str:
        endpoint = self.config.foundry_endpoint.rstrip("/")
        deployment = quote(self.config.chat_deployment, safe="")
        query = urlencode({"api-version": self.config.chat_api_version})
        return f"{endpoint}/openai/deployments/{deployment}/chat/completions?{query}"

    def _failure(
        self,
        *,
        code: str,
        message: str,
        start: float,
        deployment: str,
        model: str = "",
        status_code: int | None = None,
        token_usage: Mapping[str, int | None] | None = None,
    ) -> Mapping[str, Any]:
        metadata = self._metadata(start, deployment, model, token_usage)
        metadata["failure"] = {"code": code, "message": message}
        if status_code is not None:
            metadata["status_code"] = status_code
        return {"reply": "", "status": code, "metadata": metadata}

    def _metadata(
        self,
        start: float,
        deployment: str,
        model: str = "",
        token_usage: Mapping[str, int | None] | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "latency_ms": self._latency_ms(start),
            "deployment": deployment,
        }
        if model:
            metadata["model"] = model
        if token_usage is not None:
            metadata["token_usage"] = dict(token_usage)
        return metadata

    def _latency_ms(self, start: float) -> int:
        return max(0, round((self.clock() - start) * 1000))


def _extract_content(raw: Mapping[str, Any]) -> str | None:
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
        return content
    if isinstance(content, list):
        text = "\n".join(
            item.get("text", "") for item in content if isinstance(item, Mapping)
        ).strip()
        return text if text else None
    return None


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
