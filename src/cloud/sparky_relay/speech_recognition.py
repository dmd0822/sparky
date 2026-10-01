"""Azure Speech recognition adapter for the relay downstream port."""

from __future__ import annotations

import base64
import binascii
import json
import socket
import time
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from .keyless_auth import AzureRelayConfig, build_speech_aad_authorization_token


DEFAULT_TIMEOUT_SECONDS = 20.0


class SpeechRecognitionTransport(Protocol):
    """HTTP transport seam used by the Speech recognition adapter."""

    def send(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        """Send a request and return status plus response bytes."""


class UrlLibSpeechRecognitionTransport:
    """Stdlib HTTP transport for Speech recognition requests."""

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


class SpeechRecognitionAdapter:
    """Translate relay speech recognition requests into Azure Speech REST calls."""

    def __init__(
        self,
        config: AzureRelayConfig,
        transport: SpeechRecognitionTransport | None = None,
        *,
        clock: Callable[[], float] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.config = config
        self.transport = transport or UrlLibSpeechRecognitionTransport()
        self.clock = clock or time.monotonic
        self.timeout_seconds = timeout_seconds

    def recognize(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        start = self.clock()
        if not self.config.speech_endpoint:
            return self._failure(
                code="speech_not_configured",
                message="Speech endpoint is not configured.",
                start=start,
            )

        try:
            body = self._audio_body(payload)
        except ValueError as exc:
            return self._failure(code="invalid_request", message=str(exc), start=start)

        try:
            authorization = self._authorization_header(headers["Authorization"])
        except (KeyError, ValueError) as exc:
            message = str(exc) if str(exc) else "Speech recognition requires authorization."
            return self._failure(code="invalid_request", message=message, start=start)

        request_headers = {
            "Authorization": authorization,
            "Content-Type": self.config.speech_input_format,
            "Accept": "application/json",
            "User-Agent": "sparky-relay",
            "x-correlation-id": headers.get("x-correlation-id", ""),
        }
        try:
            status_code, response_bytes = self.transport.send(
                self._request_url(),
                body,
                request_headers,
                self.timeout_seconds,
            )
        except (TimeoutError, socket.timeout):
            return self._failure(
                code="timeout",
                message="Speech recognition request timed out.",
                start=start,
            )
        except OSError as exc:
            return self._failure(
                code="transport_error",
                message=f"Speech recognition transport failed: {exc.__class__.__name__}.",
                start=start,
            )

        if status_code < 200 or status_code >= 300:
            return self._failure(
                code="downstream_status",
                message="Speech recognition returned a non-success status.",
                start=start,
                status_code=status_code,
            )
        return self._parse_response(response_bytes, start)

    def _audio_body(self, payload: Mapping[str, Any]) -> bytes:
        audio = payload.get("audio")
        if not isinstance(audio, str) or not audio.strip():
            raise ValueError("Speech recognition payload requires base64 audio.")
        try:
            decoded = base64.b64decode(audio, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Speech recognition audio must be valid base64.") from exc
        if not decoded:
            raise ValueError("Speech recognition audio must not be empty.")
        return decoded

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
        query = urlencode({"language": self.config.speech_recognition_language, "format": "detailed"})
        return (
            f"{self.config.speech_endpoint.rstrip('/')}"
            f"/stt/speech/recognition/conversation/cognitiveservices/v1?{query}"
        )

    def _parse_response(self, response_bytes: bytes, start: float) -> Mapping[str, Any]:
        if not response_bytes:
            return self._failure(
                code="empty_result",
                message="Speech recognition returned no result.",
                start=start,
            )
        try:
            payload = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._failure(
                code="empty_result",
                message="Speech recognition returned malformed JSON.",
                start=start,
            )
        if not isinstance(payload, Mapping):
            return self._failure(
                code="empty_result",
                message="Speech recognition returned an unexpected result shape.",
                start=start,
            )

        recognition_status = payload.get("RecognitionStatus")
        if recognition_status in {"NoMatch", "InitialSilenceTimeout", "BabbleTimeout"}:
            return self._failure(
                code="no_match",
                message="Speech recognition found no matching transcript.",
                start=start,
                recognition_status=str(recognition_status),
            )
        if recognition_status != "Success":
            return self._failure(
                code="downstream_status",
                message="Speech recognition returned a failure status.",
                start=start,
                recognition_status=str(recognition_status) if recognition_status is not None else None,
            )

        nbest = payload.get("NBest")
        if not isinstance(nbest, list) or not nbest or not isinstance(nbest[0], Mapping):
            return self._failure(
                code="empty_result",
                message="Speech recognition returned no transcript candidates.",
                start=start,
                recognition_status=str(recognition_status),
            )
        best = nbest[0]
        display = best.get("Display")
        if not isinstance(display, str) or not display.strip():
            return self._failure(
                code="empty_result",
                message="Speech recognition returned an empty transcript.",
                start=start,
                recognition_status=str(recognition_status),
            )
        confidence = best.get("Confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        return {
            "transcript": display,
            "confidence": float(confidence),
            "metadata": {
                "latency_ms": self._latency_ms(start),
                "recognition_status": recognition_status,
            },
        }

    def _failure(
        self,
        *,
        code: str,
        message: str,
        start: float,
        status_code: int | None = None,
        recognition_status: str | None = None,
    ) -> Mapping[str, Any]:
        metadata: dict[str, Any] = {
            "latency_ms": self._latency_ms(start),
            "failure": {"code": code, "message": message},
        }
        if status_code is not None:
            metadata["status_code"] = status_code
        if recognition_status:
            metadata["recognition_status"] = recognition_status
        return {"transcript": "", "confidence": 0.0, "status": code, "metadata": metadata}

    def _latency_ms(self, start: float) -> int:
        return max(0, round((self.clock() - start) * 1000))
