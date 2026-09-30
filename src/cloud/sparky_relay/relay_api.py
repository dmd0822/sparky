"""Stdlib-only relay request dispatcher and endpoint handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
import uuid
from typing import Any, Mapping, MutableMapping, Protocol

from .keyless_auth import AzureRelayConfig, acquire_downstream_access_token
from .relay_auth import (
    AuthContext,
    AuthFailure,
    RelayAuthConfig,
    TokenVerifier,
    authenticate_request,
)


LOGGER = logging.getLogger(__name__)

REQUEST_SCHEMAS: dict[str, dict[str, Any]] = {
    "health": {"method": "GET", "path": "/health", "required": []},
    "chat": {"method": "POST", "path": "/ai/chat", "required": ["prompt"]},
    "vision": {"method": "POST", "path": "/ai/vision", "required": ["image"]},
    "speech": {"method": "POST", "path": "/speech/synthesize", "required": ["text"]},
}

RESPONSE_SCHEMAS: dict[str, dict[str, Any]] = {
    "health": {"required": ["status", "correlation_id", "authenticated"]},
    "chat": {"required": ["reply", "correlation_id"]},
    "vision": {"required": ["caption", "labels", "correlation_id"]},
    "speech": {"required": ["audio", "audio_format", "correlation_id"]},
    "error": {"required": ["error", "correlation_id"]},
}


@dataclass(frozen=True)
class RelayRequest:
    """Minimal framework-neutral request object."""

    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelayResponse:
    """Minimal framework-neutral response object."""

    status_code: int
    body: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)


class DownstreamRelayClient(Protocol):
    """Port for managed-identity calls to Foundry and Speech."""

    def chat(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        """Return a relay-shaped chat result."""

    def vision(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        """Return a relay-shaped vision result."""

    def speech(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        """Return a relay-shaped speech result."""


class RelayPolicy(Protocol):
    """Post-auth policy hook."""

    def allow(self, context: AuthContext, request: RelayRequest) -> tuple[bool, str]:
        """Return whether the authenticated request is allowed."""


class RateLimiter(Protocol):
    """Rate-limiting hook."""

    def allow(self, key: str, now: float | None = None) -> bool:
        """Return whether the request should proceed."""


class AllowAllPolicy:
    """Default policy hook that permits authenticated callers."""

    def allow(self, context: AuthContext, request: RelayRequest) -> tuple[bool, str]:
        return True, "allowed"


class InMemoryRateLimiter:
    """Small process-local fixed-window limiter for the default relay."""

    def __init__(self, limit: int = 120, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: MutableMapping[str, tuple[int, int]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        current = int(now if now is not None else time.time())
        window = current // self.window_seconds
        existing_window, count = self._windows.get(key, (window, 0))
        if existing_window != window:
            self._windows[key] = (window, 1)
            return True
        if count >= self.limit:
            return False
        self._windows[key] = (window, count + 1)
        return True


@dataclass
class RelayApp:
    """Framework-neutral authenticated relay API."""

    relay_config: AzureRelayConfig
    auth_config: RelayAuthConfig
    verifier: TokenVerifier
    credential: Any
    downstream: DownstreamRelayClient
    policy: RelayPolicy = field(default_factory=AllowAllPolicy)
    rate_limiter: RateLimiter = field(default_factory=InMemoryRateLimiter)
    now: int | None = None

    def handle(self, request: RelayRequest) -> RelayResponse:
        correlation_id = _correlation_id(request.headers)
        try:
            context = authenticate_request(
                request.headers,
                self.auth_config,
                self.verifier,
                now=self.now,
                correlation_id=correlation_id,
            )
            if not self.rate_limiter.allow(context.subject):
                return _error(429, "rate_limited", "Too many requests.", correlation_id)
            allowed, reason = self.policy.allow(context, request)
            if not allowed:
                LOGGER.warning("Relay policy denied request: %s", reason)
                return _error(403, "policy_denied", "The request is not allowed.", correlation_id)
            return self._dispatch(request, context, correlation_id)
        except AuthFailure as failure:
            return _error(failure.status_code, failure.code, failure.reason, failure.correlation_id)
        except DownstreamCredentialError:
            LOGGER.error("Relay credential boundary guard blocked a downstream request.")
            return _error(500, "credential_boundary", "Relay credential boundary failed.", correlation_id)

    def _dispatch(
        self,
        request: RelayRequest,
        context: AuthContext,
        correlation_id: str,
    ) -> RelayResponse:
        method = request.method.upper()
        if method == "GET" and request.path == "/health":
            return _response(
                200,
                {
                    "status": "ok",
                    "authenticated": True,
                    "correlation_id": correlation_id,
                },
                correlation_id,
            )
        if method == "POST" and request.path == "/ai/chat":
            return self._chat(request, context, correlation_id)
        if method == "POST" and request.path == "/ai/vision":
            return self._vision(request, context, correlation_id)
        if method == "POST" and request.path == "/speech/synthesize":
            return self._speech(request, context, correlation_id)
        return _error(404, "not_found", "No relay endpoint matched the request.", correlation_id)

    def _chat(
        self,
        request: RelayRequest,
        context: AuthContext,
        correlation_id: str,
    ) -> RelayResponse:
        prompt = request.body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return _error(400, "invalid_request", "Chat requires a prompt.", correlation_id)
        headers = self._downstream_headers(
            self.relay_config.foundry_scope,
            context,
            correlation_id,
        )
        result = dict(self.downstream.chat(request.body, headers))
        result.setdefault("reply", "")
        result["correlation_id"] = correlation_id
        return _response(200, result, correlation_id)

    def _vision(
        self,
        request: RelayRequest,
        context: AuthContext,
        correlation_id: str,
    ) -> RelayResponse:
        image = request.body.get("image")
        if not isinstance(image, str) or not image.strip():
            return _error(400, "invalid_request", "Vision requires an image payload.", correlation_id)
        headers = self._downstream_headers(
            self.relay_config.foundry_scope,
            context,
            correlation_id,
        )
        result = dict(self.downstream.vision(request.body, headers))
        result.setdefault("caption", "")
        result.setdefault("labels", [])
        result["correlation_id"] = correlation_id
        return _response(200, result, correlation_id)

    def _speech(
        self,
        request: RelayRequest,
        context: AuthContext,
        correlation_id: str,
    ) -> RelayResponse:
        text = request.body.get("text")
        if not isinstance(text, str) or not text.strip():
            return _error(400, "invalid_request", "Speech requires text.", correlation_id)
        headers = self._downstream_headers(
            self.relay_config.speech_scope,
            context,
            correlation_id,
        )
        result = dict(self.downstream.speech(request.body, headers))
        result.setdefault("audio", "")
        result.setdefault("audio_format", "wav")
        result["correlation_id"] = correlation_id
        return _response(200, result, correlation_id)

    def _downstream_headers(
        self,
        scope: str,
        context: AuthContext,
        correlation_id: str,
    ) -> dict[str, str]:
        managed_token = acquire_downstream_access_token(scope, self.credential)
        headers = {
            "Authorization": f"Bearer {managed_token}",
            "x-correlation-id": correlation_id,
        }
        assert_caller_token_not_forwarded(context.token, headers)
        return headers


class DownstreamCredentialError(RuntimeError):
    """Raised when caller credential material reaches a downstream request."""


def assert_caller_token_not_forwarded(
    caller_token: str,
    downstream_headers: Mapping[str, str],
) -> None:
    """Fail closed if the inbound bearer value is present in downstream headers."""

    if not caller_token:
        return
    for value in downstream_headers.values():
        if caller_token in value:
            raise DownstreamCredentialError("Caller token was placed on a downstream request.")


def _correlation_id(headers: Mapping[str, str]) -> str:
    for key, value in headers.items():
        if key.lower() == "x-correlation-id" and value.strip():
            return value.strip()
    return str(uuid.uuid4())


def _response(status_code: int, body: Mapping[str, Any], correlation_id: str) -> RelayResponse:
    return RelayResponse(
        status_code=status_code,
        body=body,
        headers={"x-correlation-id": correlation_id},
    )


def _error(status_code: int, code: str, message: str, correlation_id: str) -> RelayResponse:
    return _response(
        status_code,
        {"error": {"code": code, "message": message}, "correlation_id": correlation_id},
        correlation_id,
    )
