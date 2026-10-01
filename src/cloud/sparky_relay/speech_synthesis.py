"""Azure Speech synthesis adapter for the relay downstream port."""

from __future__ import annotations

import base64
import socket
import time
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError
from urllib.request import Request as UrlRequest, urlopen
from xml.sax.saxutils import escape, quoteattr

from .keyless_auth import AzureRelayConfig, build_speech_aad_authorization_token


DEFAULT_TIMEOUT_SECONDS = 20.0


class SpeechTransport(Protocol):
    """HTTP transport seam used by the Speech synthesis adapter."""

    def send(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        """Send a request and return status plus response bytes."""


class UrlLibSpeechTransport:
    """Stdlib HTTP transport for Speech synthesis requests."""

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


class SpeechSynthesisAdapter:
    """Translate relay speech requests into Azure Speech synthesis calls."""

    def __init__(
        self,
        config: AzureRelayConfig,
        transport: SpeechTransport | None = None,
        *,
        clock: Callable[[], float] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.config = config
        self.transport = transport or UrlLibSpeechTransport()
        self.clock = clock or time.monotonic
        self.timeout_seconds = timeout_seconds

    def speech(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        start = self.clock()
        if not self.config.speech_endpoint:
            return self._failure(
                code="speech_not_configured",
                message="Speech endpoint is not configured.",
                start=start,
            )

        try:
            body = self._build_ssml(payload)
        except ValueError as exc:
            return self._failure(code="invalid_request", message=str(exc), start=start)

        try:
            authorization = self._authorization_header(headers["Authorization"])
        except ValueError as exc:
            return self._failure(code="invalid_request", message=str(exc), start=start)

        request_headers = {
            "Authorization": authorization,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": self.config.speech_output_format,
            "User-Agent": "sparky-relay",
            "x-correlation-id": headers.get("x-correlation-id", ""),
        }
        try:
            status_code, response_bytes = self.transport.send(
                self._request_url(),
                body.encode("utf-8"),
                request_headers,
                self.timeout_seconds,
            )
        except (TimeoutError, socket.timeout):
            return self._failure(
                code="timeout",
                message="Speech synthesis request timed out.",
                start=start,
            )
        except OSError as exc:
            return self._failure(
                code="transport_error",
                message=f"Speech synthesis transport failed: {exc.__class__.__name__}.",
                start=start,
            )

        if status_code < 200 or status_code >= 300:
            return self._failure(
                code="downstream_status",
                message="Speech synthesis returned a non-success status.",
                start=start,
                status_code=status_code,
            )
        if not response_bytes:
            return self._failure(
                code="empty_result",
                message="Speech synthesis returned no audio.",
                start=start,
            )
        return {
            "audio": base64.b64encode(response_bytes).decode("ascii"),
            "audio_format": _audio_format(self.config.speech_output_format),
            "metadata": {"latency_ms": self._latency_ms(start)},
        }

    def _build_ssml(self, payload: Mapping[str, Any]) -> str:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Speech payload requires text.")
        voice = self.config.speech_voice.strip()
        voice_attribute = f" name={quoteattr(voice)}" if voice else ""
        return (
            '<speak version="1.0" xml:lang="en-US">'
            f"<voice{voice_attribute}>{escape(text.strip())}</voice>"
            "</speak>"
        )

    def _authorization_header(self, authorization: str) -> str:
        if not self.config.speech_resource_id:
            return authorization
        prefix = "Bearer "
        bare_token = authorization[len(prefix) :] if authorization.lower().startswith(prefix.lower()) else authorization
        speech_token = build_speech_aad_authorization_token(
            self.config.speech_resource_id,
            bare_token,
        )
        return f"Bearer {speech_token}"

    def _request_url(self) -> str:
        return f"{self.config.speech_endpoint.rstrip('/')}/cognitiveservices/v1"

    def _failure(
        self,
        *,
        code: str,
        message: str,
        start: float,
        status_code: int | None = None,
    ) -> Mapping[str, Any]:
        metadata: dict[str, Any] = {
            "latency_ms": self._latency_ms(start),
            "failure": {"code": code, "message": message},
        }
        if status_code is not None:
            metadata["status_code"] = status_code
        return {"audio": "", "audio_format": "wav", "status": code, "metadata": metadata}

    def _latency_ms(self, start: float) -> int:
        return max(0, round((self.clock() - start) * 1000))


def _audio_format(output_format: str) -> str:
    normalized = output_format.strip().lower()
    if normalized.startswith("riff"):
        return "wav"
    if "mp3" in normalized and (
        normalized.startswith("audio-16khz")
        or normalized.startswith("audio-24khz")
        or normalized.startswith("audio-48khz")
    ):
        return "mp3"
    if normalized.startswith("ogg") or "ogg" in normalized:
        return "ogg"
    if normalized.startswith("webm") or "webm" in normalized:
        return "webm"
    return "wav"
