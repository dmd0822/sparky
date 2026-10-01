"""Tests for the Speech recognition downstream adapter."""

from __future__ import annotations

import base64
import json
from pathlib import Path
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
from src.cloud.sparky_relay.speech_recognition import SpeechRecognitionAdapter


NOW = 1_800_000_000
ROOT = Path(__file__).parents[1]
AUDIO_FIXTURE = ROOT / "tests" / "fixtures" / "audio" / "tone-16khz.wav"
RESPONSE_FIXTURE = ROOT / "tests" / "fixtures" / "speech-recognition-detailed.json"


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


class SpeechRecognitionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
            relay_audience="api://relay-app-id",
            device_scope="api://relay-app-id/.default",
            speech_endpoint="https://sparky-speech.cognitiveservices.azure.com",
            speech_resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/speech",
            speech_recognition_language="en-US",
            speech_input_format="audio/wav; codecs=audio/pcm; samplerate=16000",
        )
        self.audio_bytes = AUDIO_FIXTURE.read_bytes()
        self.audio_payload = base64.b64encode(self.audio_bytes).decode("ascii")
        self.response_bytes = RESPONSE_FIXTURE.read_bytes()
        self.headers = {"Authorization": "Bearer managed-hop-token", "x-correlation-id": "cid-speech"}

    def adapter(
        self,
        transport: RecordingTransport,
        *,
        config: AzureRelayConfig | None = None,
        clock: SteppingClock | None = None,
    ) -> SpeechRecognitionAdapter:
        return SpeechRecognitionAdapter(
            config or self.config,
            transport,
            clock=clock or SteppingClock(10.0, 10.125),
            timeout_seconds=7.5,
        )

    def test_success_shapes_request_parses_transcript_confidence_latency_and_auth(self) -> None:
        transport = RecordingTransport(self.response_bytes)

        result = self.adapter(transport).recognize({"audio": self.audio_payload}, self.headers)

        self.assertEqual(result["transcript"], "What's the weather like?")
        self.assertAlmostEqual(result["confidence"], 0.9052885)
        self.assertEqual(result["metadata"]["latency_ms"], 125)
        self.assertEqual(result["metadata"]["recognition_status"], "Success")
        url, body, headers, timeout = transport.calls[0]
        self.assertEqual(
            url,
            "https://sparky-speech.cognitiveservices.azure.com"
            "/stt/speech/recognition/conversation/cognitiveservices/v1?language=en-US&format=detailed",
        )
        self.assertEqual(body, self.audio_bytes)
        self.assertEqual(timeout, 7.5)
        self.assertEqual(
            headers["Authorization"],
            "Bearer aad#/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/speech#managed-hop-token",
        )
        self.assertEqual(headers["Content-Type"], "audio/wav; codecs=audio/pcm; samplerate=16000")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["User-Agent"], "sparky-relay")
        self.assertEqual(headers["x-correlation-id"], "cid-speech")

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
        transport = RecordingTransport(self.response_bytes)

        self.adapter(transport, config=config).recognize({"audio": self.audio_payload}, self.headers)

        _, _, headers, _ = transport.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer managed-hop-token")

    def test_speech_not_configured_returns_explicit_failure_result(self) -> None:
        config = AzureRelayConfig(tenant_id="tenant-123", client_id="client-456", relay_url="https://relay.example.test")

        result = self.adapter(RecordingTransport(self.response_bytes), config=config).recognize(
            {"audio": self.audio_payload},
            self.headers,
        )

        self.assertEqual(result["status"], "speech_not_configured")
        self.assertEqual(result["transcript"], "")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["metadata"]["failure"]["code"], "speech_not_configured")

    def test_missing_audio_returns_invalid_request(self) -> None:
        result = self.adapter(RecordingTransport(self.response_bytes)).recognize({}, self.headers)

        self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(result["transcript"], "")
        self.assertEqual(result["metadata"]["failure"]["code"], "invalid_request")

    def test_malformed_base64_audio_returns_invalid_request(self) -> None:
        result = self.adapter(RecordingTransport(self.response_bytes)).recognize({"audio": "not base64!!!"}, self.headers)

        self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(result["metadata"]["failure"]["code"], "invalid_request")

    def test_timeout_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"", failure=TimeoutError("slow"))).recognize(
            {"audio": self.audio_payload},
            self.headers,
        )

        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["metadata"]["failure"]["code"], "timeout")

    def test_transport_error_returns_explicit_failure_result(self) -> None:
        result = self.adapter(RecordingTransport(b"", failure=OSError("network"))).recognize(
            {"audio": self.audio_payload},
            self.headers,
        )

        self.assertEqual(result["status"], "transport_error")
        self.assertIn("OSError", result["metadata"]["failure"]["message"])

    def test_downstream_non_success_returns_explicit_failure_result_without_body_leak(self) -> None:
        result = self.adapter(RecordingTransport(b"do not expose", status_code=500)).recognize(
            {"audio": self.audio_payload},
            self.headers,
        )

        self.assertEqual(result["status"], "downstream_status")
        self.assertEqual(result["metadata"]["status_code"], 500)
        self.assertNotIn("do not expose", result["metadata"]["failure"]["message"])

    def test_no_match_returns_no_match_failure(self) -> None:
        result = self.adapter(RecordingTransport(b'{"RecognitionStatus":"NoMatch"}')).recognize(
            {"audio": self.audio_payload},
            self.headers,
        )

        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["transcript"], "")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["metadata"]["recognition_status"], "NoMatch")

    def test_empty_or_unparseable_result_returns_empty_result(self) -> None:
        for response in (b"", b"not-json", b'{"RecognitionStatus":"Success","NBest":[]}'):
            with self.subTest(response=response):
                result = self.adapter(RecordingTransport(response)).recognize(
                    {"audio": self.audio_payload},
                    self.headers,
                )

                self.assertEqual(result["status"], "empty_result")
                self.assertEqual(result["metadata"]["failure"]["code"], "empty_result")

    def test_relay_uses_managed_identity_header_and_never_caller_token(self) -> None:
        caller_token = unsigned_jwt(self.claims())
        transport = RecordingTransport(self.response_bytes)
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
                "/speech/recognize",
                {"Authorization": f"Bearer {caller_token}", "x-correlation-id": "cid-speech"},
                {"audio": self.audio_payload},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body["transcript"], "What's the weather like?")
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
