"""Tests for the Speech synthesis downstream adapter."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any, Mapping
import unittest

from src.cloud.sparky_relay.keyless_auth import AzureRelayConfig, expected_issuer
from src.cloud.sparky_relay.relay_api import RelayApp, RelayRequest
from src.cloud.sparky_relay.relay_auth import (
    RelayAuthConfig,
    TokenVerificationError,
    jwt_payload_without_verification,
)
from src.cloud.sparky_relay.speech_synthesis import SpeechSynthesisAdapter


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
        response: bytes,
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
        return self.status_code, self.response


class SteppingClock:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def __call__(self) -> float:
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


class SpeechSynthesisAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
            relay_audience="api://relay-app-id",
            device_scope="api://relay-app-id/.default",
            speech_endpoint="https://sparky-speech.cognitiveservices.azure.com",
            speech_resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/speech",
            speech_voice="en-US-AvaMultilingualNeural",
            speech_output_format="riff-24khz-16bit-mono-pcm",
        )
        self.headers = {"Authorization": "Bearer managed-hop-token", "x-correlation-id": "cid-speech"}

    def adapter(
        self,
        transport: RecordingTransport,
        *,
        config: AzureRelayConfig | None = None,
        clock: SteppingClock | None = None,
    ) -> SpeechSynthesisAdapter:
        return SpeechSynthesisAdapter(
            config or self.config,
            transport,
            clock=clock or SteppingClock(10.0, 10.125),
            timeout_seconds=7.5,
        )

    def test_success_normalizes_audio_latency_auth_and_escaped_ssml(self) -> None:
        transport = RecordingTransport(b"RIFF-audio")

        result = self.adapter(transport).speech({"text": "Sparky <speaks> & listens"}, self.headers)

        self.assertEqual(result["audio"], base64.b64encode(b"RIFF-audio").decode("ascii"))
        self.assertEqual(result["audio_format"], "wav")
        self.assertEqual(result["metadata"]["latency_ms"], 125)
        url, body, headers, timeout = transport.calls[0]
        self.assertEqual(url, "https://sparky-speech.cognitiveservices.azure.com/cognitiveservices/v1")
        self.assertEqual(timeout, 7.5)
        self.assertEqual(
            headers["Authorization"],
            "Bearer aad#/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/speech#managed-hop-token",
        )
        self.assertEqual(headers["Content-Type"], "application/ssml+xml")
        self.assertEqual(headers["X-Microsoft-OutputFormat"], "riff-24khz-16bit-mono-pcm")
        self.assertEqual(headers["x-correlation-id"], "cid-speech")
        ssml = body.decode("utf-8")
        self.assertIn("Sparky &lt;speaks&gt; &amp; listens", ssml)
        self.assertNotIn("Sparky <speaks> & listens", ssml)

    def test_passes_through_authorization_when_resource_id_is_not_set(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
            relay_audience="api://relay-app-id",
            device_scope="api://relay-app-id/.default",
            speech_endpoint="https://sparky-speech.cognitiveservices.azure.com",
            speech_resource_id="",
        )
        transport = RecordingTransport(b"audio")

        self.adapter(transport, config=config).speech({"text": "hello"}, self.headers)

        _, _, headers, _ = transport.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer managed-hop-token")

    def test_timeout_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"", failure=TimeoutError("slow"))).speech(
            {"text": "hello"},
            self.headers,
        )

        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["audio"], "")
        self.assertEqual(result["audio_format"], "wav")
        self.assertEqual(result["metadata"]["failure"]["code"], "timeout")

    def test_invalid_body_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"audio")).speech({"text": 1}, self.headers)

        self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(result["audio"], "")
        self.assertEqual(result["metadata"]["failure"]["code"], "invalid_request")

    def test_downstream_non_success_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"do not expose", status_code=500)).speech(
            {"text": "hello"},
            self.headers,
        )

        self.assertEqual(result["status"], "downstream_status")
        self.assertEqual(result["metadata"]["status_code"], 500)
        self.assertNotIn("do not expose", result["metadata"]["failure"]["message"])

    def test_empty_audio_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"")).speech({"text": "hello"}, self.headers)

        self.assertEqual(result["status"], "empty_result")
        self.assertEqual(result["metadata"]["failure"]["code"], "empty_result")

    def test_relay_uses_managed_identity_header_and_never_caller_token(self) -> None:
        caller_token = unsigned_jwt(self.claims())
        transport = RecordingTransport(b"audio")
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
                "/speech/synthesize",
                {"Authorization": f"Bearer {caller_token}", "x-correlation-id": "cid-speech"},
                {"text": "hello"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(credential.scopes, ["https://cognitiveservices.azure.com/.default"])
        _, _, headers, _ = transport.calls[0]
        self.assertEqual(
            headers["Authorization"],
            "Bearer aad#/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/speech#managed-hop-token",
        )
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
