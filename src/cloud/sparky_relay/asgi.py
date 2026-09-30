"""FastAPI hosting adapter for the framework-neutral relay."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .keyless_auth import AzureRelayConfig, COGNITIVE_SERVICES_SCOPE
from .relay_api import DownstreamRelayClient, RelayApp, RelayRequest, RelayResponse
from .relay_auth import PyJwtEntraTokenVerifier, RelayAuthConfig


_DEFAULT_RELAY_APP: RelayApp | None = None


class ImdsManagedIdentityCredential:
    """Small managed-identity credential port backed by the Azure IMDS endpoint."""

    def __init__(self, endpoint: str = "http://169.254.169.254/metadata/identity/oauth2/token") -> None:
        self.endpoint = endpoint

    def get_token(self, scope: str) -> Mapping[str, str]:
        resource = _scope_to_resource(scope)
        query = urlencode({"api-version": "2018-02-01", "resource": resource})
        request = UrlRequest(f"{self.endpoint}?{query}", headers={"Metadata": "true"})
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Managed identity did not return an access token.")
        return {"token": access_token}


class ManagedIdentityDownstreamRelayClient(DownstreamRelayClient):
    """Default downstream port; service-specific calls are added behind this boundary."""

    def chat(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        return {"reply": ""}

    def vision(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        return {"caption": "", "labels": []}

    def speech(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        return {"audio": "", "audio_format": "wav"}


def create_app(relay_app: RelayApp | None = None) -> FastAPI:
    """Create the FastAPI adapter around an injected or environment-built relay."""

    app = FastAPI(title="Sparky Relay API")
    relay_provider = _static_provider(relay_app) if relay_app is not None else _get_default_relay_app

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        return await _handle_relay_request(request, relay_provider)

    @app.post("/ai/chat")
    async def chat(request: Request) -> JSONResponse:
        return await _handle_relay_request(request, relay_provider)

    @app.post("/ai/vision")
    async def vision(request: Request) -> JSONResponse:
        return await _handle_relay_request(request, relay_provider)

    @app.post("/speech/synthesize")
    async def speech(request: Request) -> JSONResponse:
        return await _handle_relay_request(request, relay_provider)

    return app


async def _handle_relay_request(
    request: Request,
    relay_provider: Callable[[], RelayApp],
) -> JSONResponse:
    body: Mapping[str, Any] = {}
    if request.method.upper() != "GET":
        try:
            raw_body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {"code": "invalid_json", "message": "Request body must be valid JSON."},
                    "correlation_id": _correlation_id(dict(request.headers)),
                },
                headers={"x-correlation-id": _correlation_id(dict(request.headers))},
            )
        if isinstance(raw_body, Mapping):
            body = raw_body
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {"code": "invalid_request", "message": "Request body must be a JSON object."},
                    "correlation_id": _correlation_id(dict(request.headers)),
                },
                headers={"x-correlation-id": _correlation_id(dict(request.headers))},
            )

    relay_request = RelayRequest(
        method=request.method,
        path=request.url.path,
        headers=dict(request.headers),
        body=body,
    )
    return _to_json_response(relay_provider().handle(relay_request))


def _get_default_relay_app() -> RelayApp:
    global _DEFAULT_RELAY_APP
    if _DEFAULT_RELAY_APP is None:
        relay_config = _build_relay_config_from_env(os.environ)
        auth_config = RelayAuthConfig.from_relay_config(relay_config)
        _DEFAULT_RELAY_APP = RelayApp(
            relay_config=relay_config,
            auth_config=auth_config,
            verifier=PyJwtEntraTokenVerifier(relay_config.tenant_id),
            credential=ImdsManagedIdentityCredential(),
            downstream=ManagedIdentityDownstreamRelayClient(),
        )
    return _DEFAULT_RELAY_APP


def _build_relay_config_from_env(env: Mapping[str, str]) -> AzureRelayConfig:
    required = (
        "AZURE_TENANT_ID",
        "SPARKY_RELAY_AUDIENCE",
        "SPARKY_RELAY_DEVICE_SCOPE",
        "SPARKY_FOUNDRY_SCOPE",
        "SPARKY_SPEECH_SCOPE",
    )
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise ValueError("Missing required relay configuration values: " + ", ".join(missing))

    return AzureRelayConfig(
        tenant_id=env["AZURE_TENANT_ID"],
        client_id=env.get("AZURE_CLIENT_ID", "relay-server"),
        relay_url=env.get("SPARKY_RELAY_URL", ""),
        relay_audience=env["SPARKY_RELAY_AUDIENCE"],
        device_scope=env["SPARKY_RELAY_DEVICE_SCOPE"],
        foundry_scope=env.get("SPARKY_FOUNDRY_SCOPE", COGNITIVE_SERVICES_SCOPE),
        speech_scope=env.get("SPARKY_SPEECH_SCOPE", COGNITIVE_SERVICES_SCOPE),
    )


def _scope_to_resource(scope: str) -> str:
    suffix = "/.default"
    return scope[: -len(suffix)] if scope.endswith(suffix) else scope


def _static_provider(relay_app: RelayApp) -> Callable[[], RelayApp]:
    return lambda: relay_app


def _to_json_response(response: RelayResponse) -> JSONResponse:
    return JSONResponse(
        status_code=response.status_code,
        content=response.body,
        headers=dict(response.headers),
    )


def _correlation_id(headers: Mapping[str, str]) -> str:
    for key, value in headers.items():
        if key.lower() == "x-correlation-id" and value.strip():
            return value.strip()
    return ""


app = create_app()
