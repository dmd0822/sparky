"""Tests for the framework-neutral authenticated relay API."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any, Mapping
import unittest

from src.cloud.sparky_relay.keyless_auth import AzureRelayConfig, expected_issuer
from src.cloud.sparky_relay.relay_api import (
    REQUEST_SCHEMAS,
    RESPONSE_SCHEMAS,
    RelayApp,
    RelayRequest,
)
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


class RecordingDownstream:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any], Mapping[str, str]]] = []

    def chat(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append(("chat", payload, headers))
        return {"reply": "woof"}

    def vision(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append(("vision", payload, headers))
        return {"caption": "robot dog", "labels": ["dog", "robot"]}

    def speech(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append(("speech", payload, headers))
        return {"audio": "base64-wav", "audio_format": "wav"}

    def recognize(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append(("recognize", payload, headers))
        return {"transcript": "hello sparky", "confidence": 0.93}


class RelayAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.relay_config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
            relay_audience="api://relay-app-id",
            device_scope="api://relay-app-id/.default",
        )
        self.auth_config = RelayAuthConfig(
            tenant_id=self.relay_config.tenant_id,
            audience=self.relay_config.relay_audience,
            required_roles=("Relay.Device",),
            required_scopes=("Relay.Access",),
            enrolled_device_claim="sparky_enrolled",
            clock_skew_seconds=30,
        )
        self.downstream = RecordingDownstream()
        self.credential = RecordingCredential()
        self.app = RelayApp(
            relay_config=self.relay_config,
            auth_config=self.auth_config,
            verifier=FakeVerifier(),
            credential=self.credential,
            downstream=self.downstream,
            now=NOW,
        )

    def claims(self, **overrides: Any) -> dict[str, Any]:
        claims: dict[str, Any] = {
            "aud": self.relay_config.relay_audience,
            "iss": expected_issuer(self.relay_config.tenant_id),
            "tid": self.relay_config.tenant_id,
            "sub": "device-1",
            "exp": NOW + 300,
            "nbf": NOW - 30,
            "scp": "Relay.Access",
        }
        claims.update(overrides)
        return claims

    def auth_headers(self, token: str | None = None) -> dict[str, str]:
        token = token or unsigned_jwt(self.claims())
        return {"Authorization": f"Bearer {token}", "x-correlation-id": "cid-1"}

    def request(self, path: str, body: Mapping[str, Any], token: str | None = None) -> RelayRequest:
        return RelayRequest("POST", path, self.auth_headers(token), body)

    def test_authentication_accepts_valid_scope(self) -> None:
        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(), {}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body["status"], "ok")
        self.assertEqual(response.body["correlation_id"], "cid-1")

    def test_authentication_accepts_valid_role(self) -> None:
        token = unsigned_jwt(self.claims(scp="", roles=["Relay.Device"]))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 200)

    def test_authentication_accepts_enrolled_device_claim(self) -> None:
        token = unsigned_jwt(self.claims(scp="", roles=[], sparky_enrolled=True))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 200)

    def test_missing_token_is_unauthorized(self) -> None:
        response = self.app.handle(RelayRequest("GET", "/health", {"x-correlation-id": "cid-1"}, {}))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "missing_token")

    def test_malformed_token_is_unauthorized(self) -> None:
        response = self.app.handle(
            RelayRequest("GET", "/health", {"Authorization": "Bearer not-a-jwt", "x-correlation-id": "cid-1"}, {})
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "malformed_token")

    def test_bad_signature_is_unauthorized(self) -> None:
        response = self.app.handle(
            RelayRequest("GET", "/health", self.auth_headers("bad.signature.token"), {})
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "invalid_token")

    def test_wrong_issuer_is_unauthorized(self) -> None:
        token = unsigned_jwt(self.claims(iss="https://login.microsoftonline.com/other/v2.0"))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "invalid_issuer")

    def test_wrong_tenant_is_unauthorized(self) -> None:
        token = unsigned_jwt(self.claims(tid="other-tenant"))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "invalid_tenant")

    def test_wrong_audience_is_unauthorized(self) -> None:
        token = unsigned_jwt(self.claims(aud="api://other-api"))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "invalid_audience")

    def test_graph_audience_is_explicitly_rejected(self) -> None:
        token = unsigned_jwt(self.claims(aud="https://graph.microsoft.com"))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "invalid_audience")

    def test_expired_token_is_unauthorized(self) -> None:
        token = unsigned_jwt(self.claims(exp=NOW - 31))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "token_expired")

    def test_future_nbf_is_unauthorized(self) -> None:
        token = unsigned_jwt(self.claims(nbf=NOW + 31))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.body["error"]["code"], "token_not_yet_valid")

    def test_missing_role_scope_or_device_claim_is_forbidden(self) -> None:
        token = unsigned_jwt(self.claims(scp="", roles=[], sparky_enrolled=False))

        response = self.app.handle(RelayRequest("GET", "/health", self.auth_headers(token), {}))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.body["error"]["code"], "missing_grant")

    def test_token_material_does_not_appear_in_error_body_or_logs(self) -> None:
        token = "caller-secret-token"
        with self.assertLogs("src.cloud.sparky_relay.relay_auth", level="WARNING") as logs:
            response = self.app.handle(
                RelayRequest("GET", "/health", {"Authorization": f"Bearer {token}"}, {})
            )

        body_text = json.dumps(response.body)
        log_text = "\n".join(logs.output)
        self.assertNotIn(token, body_text)
        self.assertNotIn(token, log_text)
        self.assertEqual(response.status_code, 401)

    def test_caller_token_is_never_forwarded_downstream(self) -> None:
        caller_token = unsigned_jwt(self.claims())

        response = self.app.handle(self.request("/ai/chat", {"prompt": "hello"}, caller_token))

        self.assertEqual(response.status_code, 200)
        _, _, headers = self.downstream.calls[0]
        self.assertIn("managed-hop-token", headers["Authorization"])
        self.assertNotIn(caller_token, headers["Authorization"])

    def test_chat_endpoint_integration(self) -> None:
        response = self.app.handle(self.request("/ai/chat", {"prompt": "hello"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body["reply"], "woof")
        self.assertEqual(self.downstream.calls[0][0], "chat")

    def test_vision_endpoint_integration(self) -> None:
        response = self.app.handle(self.request("/ai/vision", {"image": "base64-image"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body["caption"], "robot dog")
        self.assertEqual(self.downstream.calls[0][0], "vision")

    def test_speech_endpoint_integration(self) -> None:
        response = self.app.handle(self.request("/speech/synthesize", {"text": "hello"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body["audio_format"], "wav")
        self.assertEqual(self.downstream.calls[0][0], "speech")

    def test_speech_recognition_endpoint_integration(self) -> None:
        response = self.app.handle(self.request("/speech/recognize", {"audio": "base64-wav"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body["transcript"], "hello sparky")
        self.assertEqual(response.body["confidence"], 0.93)
        self.assertEqual(self.downstream.calls[0][0], "recognize")

    def test_contract_schemas_cover_each_endpoint(self) -> None:
        self.assertEqual(
            {schema["path"] for schema in REQUEST_SCHEMAS.values()},
            {"/health", "/ai/chat", "/ai/vision", "/speech/synthesize", "/speech/recognize"},
        )
        for name in ("health", "chat", "vision", "speech", "recognize", "error"):
            with self.subTest(schema=name):
                self.assertIn(name, RESPONSE_SCHEMAS)
                self.assertTrue(RESPONSE_SCHEMAS[name]["required"])

    def test_contract_response_shapes_for_each_endpoint(self) -> None:
        cases = {
            "health": RelayRequest("GET", "/health", self.auth_headers(), {}),
            "chat": self.request("/ai/chat", {"prompt": "hello"}),
            "vision": self.request("/ai/vision", {"image": "base64-image"}),
            "speech": self.request("/speech/synthesize", {"text": "hello"}),
            "recognize": self.request("/speech/recognize", {"audio": "base64-wav"}),
        }
        for name, request in cases.items():
            with self.subTest(endpoint=name):
                response = self.app.handle(request)
                self.assertEqual(response.status_code, 200)
                for field in RESPONSE_SCHEMAS[name]["required"]:
                    self.assertIn(field, response.body)


if __name__ == "__main__":
    unittest.main()
