"""Tests for the optional FastAPI relay hosting adapter."""

from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace
from typing import Any, Mapping
import unittest
from unittest.mock import patch

try:
    import fastapi  # noqa: F401
except ImportError as exc:  # pragma: no cover - exercised in minimal CI images.
    raise unittest.SkipTest("FastAPI is not installed in the test environment.") from exc

from src.cloud.sparky_relay.asgi import (
    _build_relay_config_from_env,
    _handle_relay_request,
    create_app,
)
from src.cloud.sparky_relay.relay_api import RelayRequest, RelayResponse


class FakeRelay:
    def __init__(self) -> None:
        self.requests: list[RelayRequest] = []

    def handle(self, request: RelayRequest) -> RelayResponse:
        self.requests.append(request)
        return RelayResponse(
            403,
            {"error": {"code": "missing_grant", "message": "no"}, "correlation_id": "cid-1"},
            {"x-correlation-id": "cid-1"},
        )


class FakeRequest:
    def __init__(
        self,
        *,
        method: str = "POST",
        path: str = "/ai/chat",
        headers: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> None:
        self.method = method
        self.url = SimpleNamespace(path=path)
        self.headers = headers or {"Authorization": "Bearer caller.token.value", "x-correlation-id": "cid-1"}
        self._body = body or {"prompt": "hello"}

    async def json(self) -> Mapping[str, Any]:
        return self._body


class RelayAsgiTests(unittest.TestCase):
    def test_create_app_exposes_relay_routes(self) -> None:
        app = create_app(FakeRelay())  # type: ignore[arg-type]

        route_paths = {getattr(route, "path", "") for route in app.routes}

        self.assertTrue({"/health", "/ai/chat", "/ai/vision", "/speech/synthesize", "/speech/recognize"}.issubset(route_paths))

    def test_health_does_not_require_relay_configuration(self) -> None:
        app = create_app()
        health_endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/health")

        with patch.dict(os.environ, {}, clear=True):
            response = asyncio.run(health_endpoint(FakeRequest(method="GET", path="/health")))  # type: ignore[arg-type]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-correlation-id"], "cid-1")
        self.assertEqual(
            json.loads(response.body),
            {"status": "ok", "authenticated": False, "correlation_id": "cid-1"},
        )

    def test_handler_preserves_relay_status_body_and_headers(self) -> None:
        relay = FakeRelay()

        response = asyncio.run(_handle_relay_request(FakeRequest(), lambda: relay))  # type: ignore[arg-type]

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["x-correlation-id"], "cid-1")
        self.assertEqual(json.loads(response.body)["error"]["code"], "missing_grant")
        self.assertEqual(relay.requests[0].path, "/ai/chat")
        self.assertEqual(relay.requests[0].body["prompt"], "hello")

    def test_ai_routes_return_503_when_relay_configuration_is_unavailable(self) -> None:
        def unavailable_relay() -> FakeRelay:
            raise ValueError("bad config contains super-secret-env-value")

        for path in ("/ai/chat", "/ai/vision", "/speech/synthesize", "/speech/recognize"):
            with self.subTest(path=path):
                response = asyncio.run(
                    _handle_relay_request(
                        FakeRequest(path=path, headers={"x-correlation-id": "cid-503"}),
                        unavailable_relay,
                    )
                )
                body = json.loads(response.body)

                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.headers["x-correlation-id"], "cid-503")
                self.assertEqual(body["correlation_id"], "cid-503")
                self.assertEqual(body["error"]["code"], "relay_unavailable")
                self.assertEqual(body["error"]["message"], "Relay is not configured.")
                self.assertNotIn("super-secret-env-value", response.body.decode("utf-8"))
                self.assertNotIn("Traceback", response.body.decode("utf-8"))

    def test_adr_0003_env_contract_builds_relay_config(self) -> None:
        config = _build_relay_config_from_env(
            {
                "AZURE_TENANT_ID": "tenant-123",
                "SPARKY_RELAY_AUDIENCE": "api://relay-app-id",
                "SPARKY_RELAY_DEVICE_SCOPE": "api://relay-app-id/.default",
                "SPARKY_FOUNDRY_SCOPE": "https://cognitiveservices.azure.com/.default",
                "SPARKY_SPEECH_SCOPE": "https://cognitiveservices.azure.com/.default",
            }
        )

        self.assertEqual(config.tenant_id, "tenant-123")
        self.assertEqual(config.relay_audience, "api://relay-app-id")
        self.assertEqual(config.device_scope, "api://relay-app-id/.default")


if __name__ == "__main__":
    unittest.main()
