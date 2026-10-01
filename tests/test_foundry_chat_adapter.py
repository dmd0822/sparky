"""Tests for the Foundry chat downstream adapter."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any, Mapping
import unittest

from src.cloud.sparky_relay.foundry_chat import FoundryChatAdapter
from src.cloud.sparky_relay.keyless_auth import AzureRelayConfig, expected_issuer
from src.cloud.sparky_relay.relay_api import RelayApp, RelayRequest
from src.cloud.sparky_relay.relay_auth import (
    RelayAuthConfig,
    TokenVerificationError,
    jwt_payload_without_verification,
)


NOW = 1_800_000_000


def unsigned_jwt(claims: dict[str, Any]) -> str:
    def encode(value: dict[str, Any]) -> str:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode(claims)}."


class FakeVerifier:
    def verify(self, token: str) -> Mapping[str, Any]:
        if token == "bad.signature.token":
            raise TokenVerificationError("signature failed")
        return jwt_payload_without_verification(token)


class RecordingCredential:
    def __init__(self, token: str = "managed-hop-token") -> None:
        self.token = token
        self.scopes: list[str] = []

    def get_token(self, scope: str) -> SimpleNamespace:
        self.scopes.append(scope)
        return SimpleNamespace(token=self.token)


class RecordingTransport:
    def __init__(
        self,
        response: Mapping[str, Any] | bytes,
        *,
        status_code: int = 200,
        failure: BaseException | None = None,
    ) -> None:
        self.response = response
        self.status_code = status_code
        self.failure = failure
        self.calls: list[tuple[str, bytes, Mapping[str, str], float]] = []

    def send(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append((url, body, dict(headers), timeout))
        if self.failure is not None:
            raise self.failure
        if isinstance(self.response, bytes):
            return self.status_code, self.response
        return self.status_code, json.dumps(self.response).encode("utf-8")


class SteppingClock:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def __call__(self) -> float:
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


class FoundryChatAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
            relay_audience="api://relay-app-id",
            device_scope="api://relay-app-id/.default",
            foundry_endpoint="https://sparky-foundry.openai.azure.com",
            chat_deployment="sparky-chat",
            chat_api_version="2024-10-21",
        )
        self.headers = {"Authorization": "Bearer managed-hop-token", "x-correlation-id": "cid-chat"}

    def adapter(
        self,
        transport: RecordingTransport,
        *,
        clock: SteppingClock | None = None,
    ) -> FoundryChatAdapter:
        return FoundryChatAdapter(
            self.config,
            transport,
            clock=clock or SteppingClock(10.0, 10.125),
            timeout_seconds=7.5,
        )

    def foundry_success(self) -> dict[str, Any]:
        return {
            "id": "chatcmpl-1",
            "model": "gpt-4.1-mini",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Hello from Sparky."},
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
        }

    def test_success_normalizes_reply_latency_and_request_body(self) -> None:
        transport = RecordingTransport(self.foundry_success())

        result = self.adapter(transport).chat(
            {"system": "Be concise.", "prompt": "Say hello.", "ignored": True},
            self.headers,
        )

        self.assertEqual(result["reply"], "Hello from Sparky.")
        self.assertEqual(result["metadata"]["latency_ms"], 125)
        self.assertEqual(result["metadata"]["token_usage"], {"prompt": 11, "completion": 4, "total": 15})
        url, body, headers, timeout = transport.calls[0]
        self.assertEqual(
            url,
            "https://sparky-foundry.openai.azure.com/openai/deployments/"
            "sparky-chat/chat/completions?api-version=2024-10-21",
        )
        self.assertEqual(timeout, 7.5)
        self.assertEqual(headers["Authorization"], "Bearer managed-hop-token")
        self.assertEqual(headers["x-correlation-id"], "cid-chat")
        self.assertEqual(
            json.loads(body.decode("utf-8")),
            {
                "messages": [
                    {"role": "system", "content": "Be concise."},
                    {"role": "user", "content": "Say hello."},
                ]
            },
        )

    def test_timeout_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport({}, failure=TimeoutError("slow"))).chat(
            {"prompt": "hello"},
            self.headers,
        )

        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["metadata"]["failure"]["code"], "timeout")

    def test_invalid_json_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"{not-json")).chat({"prompt": "hello"}, self.headers)

        self.assertEqual(result["status"], "invalid_json")
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["metadata"]["failure"]["code"], "invalid_json")

    def test_invalid_body_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"[]")).chat({"prompt": "hello"}, self.headers)

        self.assertEqual(result["status"], "invalid_body")
        self.assertEqual(result["metadata"]["failure"]["code"], "invalid_body")

    def test_downstream_non_success_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport({"error": "no"}, status_code=429)).chat(
            {"prompt": "hello"},
            self.headers,
        )

        self.assertEqual(result["status"], "downstream_status")
        self.assertEqual(result["metadata"]["status_code"], 429)
        self.assertNotIn("error", result["metadata"]["failure"]["message"].lower())

    def test_relay_uses_managed_identity_header_and_never_caller_token(self) -> None:
        caller_token = unsigned_jwt(self.claims())
        transport = RecordingTransport(self.foundry_success())
        credential = RecordingCredential()
        app = RelayApp(
            relay_config=self.config,
            auth_config=self.auth_config(),
            verifier=FakeVerifier(),
            credential=credential,
            downstream=self.adapter(transport),
            now=NOW,
        )

        response = app.handle(
            RelayRequest(
                "POST",
                "/ai/chat",
                {"Authorization": f"Bearer {caller_token}", "x-correlation-id": "cid-chat"},
                {"prompt": "hello"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(credential.scopes, ["https://cognitiveservices.azure.com/.default"])
        _, _, headers, _ = transport.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer managed-hop-token")
        self.assertNotIn(caller_token, headers["Authorization"])

    def claims(self, **overrides: Any) -> dict[str, Any]:
        claims: dict[str, Any] = {
            "aud": self.config.relay_audience,
            "iss": expected_issuer(self.config.tenant_id),
            "tid": self.config.tenant_id,
            "sub": "device-1",
            "exp": NOW + 300,
            "nbf": NOW - 30,
            "scp": "Relay.Access",
        }
        claims.update(overrides)
        return claims

    def auth_config(self) -> RelayAuthConfig:
        return RelayAuthConfig(
            tenant_id=self.config.tenant_id,
            audience=self.config.relay_audience,
            required_roles=("Relay.Device",),
            required_scopes=("Relay.Access",),
            enrolled_device_claim="sparky_enrolled",
            clock_skew_seconds=30,
        )


if __name__ == "__main__":
    unittest.main()
