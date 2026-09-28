"""Tests for the keyless auth proof-of-path helpers."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
import unittest

from src.cloud.sparky_relay.keyless_auth import (
    COGNITIVE_SERVICES_SCOPE,
    AzureRelayConfig,
    TokenAcquisitionError,
    acquire_downstream_tokens,
    build_demo_sequence,
    build_speech_aad_authorization_token,
    expected_issuer,
    validate_relay_token,
    validate_required_config,
)


def unsigned_jwt(claims: dict[str, str]) -> str:
    def encode(value: dict[str, str]) -> str:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode(claims)}."


class RecordingCredential:
    def __init__(self, tokens: dict[str, str] | None = None, fail: bool = False) -> None:
        self.tokens = tokens or {}
        self.fail = fail
        self.scopes: list[str] = []

    def get_token(self, scope: str) -> SimpleNamespace:
        self.scopes.append(scope)
        if self.fail:
            raise RuntimeError("managed identity unavailable")
        return SimpleNamespace(token=self.tokens.get(scope, "token-for-" + scope))


class KeylessAuthSpikeTests(unittest.TestCase):
    def test_config_requires_required_values(self) -> None:
        with self.assertRaises(ValueError):
            AzureRelayConfig.from_env({})

    def test_device_code_payload_targets_relay_scope_not_ai_scope(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
            relay_audience="api://relay-app-id",
            device_scope="api://relay-app-id/.default",
        )

        payload = config.build_device_code_payload()

        self.assertEqual(payload["client_id"], "client-456")
        self.assertEqual(payload["tenant"], "tenant-123")
        self.assertEqual(payload["scope"], "api://relay-app-id/.default")
        self.assertNotEqual(payload["scope"], COGNITIVE_SERVICES_SCOPE)

    def test_device_scope_guard_rejects_azure_ai_audience(self) -> None:
        with self.assertRaisesRegex(ValueError, "relay app registration"):
            AzureRelayConfig(
                tenant_id="tenant-123",
                client_id="client-456",
                relay_url="https://relay.example.test",
                device_scope=COGNITIVE_SERVICES_SCOPE,
            )

    def test_from_env_separates_device_foundry_and_speech_scopes(self) -> None:
        config = AzureRelayConfig.from_env(
            {
                "AZURE_TENANT_ID": "tenant-123",
                "AZURE_CLIENT_ID": "client-456",
                "SPARKY_RELAY_URL": "https://relay.example.test",
                "SPARKY_RELAY_AUDIENCE": "api://relay-app-id",
                "SPARKY_RELAY_DEVICE_SCOPE": "api://relay-app-id/user_impersonation",
                "SPARKY_FOUNDRY_SCOPE": COGNITIVE_SERVICES_SCOPE,
                "SPARKY_SPEECH_SCOPE": COGNITIVE_SERVICES_SCOPE,
            }
        )

        self.assertEqual(config.relay_audience, "api://relay-app-id")
        self.assertEqual(config.device_scope, "api://relay-app-id/user_impersonation")
        self.assertEqual(config.foundry_scope, COGNITIVE_SERVICES_SCOPE)
        self.assertEqual(config.speech_scope, COGNITIVE_SERVICES_SCOPE)

    def test_demo_sequence_uses_relay_and_contains_foundry_and_speech_calls(self) -> None:
        payload = build_demo_sequence(
            {
                "AZURE_TENANT_ID": "tenant-123",
                "AZURE_CLIENT_ID": "client-456",
                "SPARKY_RELAY_URL": "https://relay.example.test",
                "SPARKY_RELAY_AUDIENCE": "api://relay-app-id",
                "SPARKY_RELAY_DEVICE_SCOPE": "api://relay-app-id/.default",
            }
        )

        self.assertIn("https://login.microsoftonline.com/tenant-123/oauth2/v2.0/devicecode", payload["device_code_url"])
        self.assertEqual(payload["relay_url"], "https://relay.example.test")
        self.assertEqual(
            payload["relay_headers"]["Authorization"],
            "Bearer <relay-audience-access-token>",
        )
        self.assertEqual(payload["hop_tokens"]["pi_to_relay"]["audience"], "api://relay-app-id")
        self.assertIn("foundry_chat", payload["relay_payloads"])
        self.assertIn("speech_synthesis", payload["relay_payloads"])
        joined_commands = "\n".join(payload["curl_example"])
        self.assertIn("Authorization: Bearer <relay-audience-access-token>", joined_commands)
        self.assertIn("/ai/chat", joined_commands)
        self.assertIn("/speech/synthesize", joined_commands)

    def test_validate_required_config_accepts_valid_values(self) -> None:
        validate_required_config(
            {
                "AZURE_TENANT_ID": "tenant-123",
                "AZURE_CLIENT_ID": "client-456",
                "SPARKY_RELAY_URL": "https://relay.example.test",
            }
        )

    def test_relay_token_validation_accepts_expected_audience_and_issuer(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
        )
        token = unsigned_jwt(
            {"aud": config.relay_audience, "iss": expected_issuer(config.tenant_id)}
        )

        validate_relay_token(token, config)

    def test_relay_token_validation_rejects_wrong_audience(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
        )
        token = unsigned_jwt(
            {"aud": "https://cognitiveservices.azure.com", "iss": expected_issuer(config.tenant_id)}
        )

        with self.assertRaisesRegex(ValueError, "audience"):
            validate_relay_token(token, config)

    def test_relay_token_validation_rejects_wrong_issuer(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
        )
        token = unsigned_jwt(
            {"aud": config.relay_audience, "iss": "https://login.microsoftonline.com/other/v2.0"}
        )

        with self.assertRaisesRegex(ValueError, "issuer"):
            validate_relay_token(token, config)

    def test_managed_identity_token_acquisition_requests_foundry_and_speech_scopes(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
            foundry_scope="https://cognitiveservices.azure.com/.default",
            speech_scope="https://cognitiveservices.azure.com/.default",
        )
        credential = RecordingCredential()

        tokens = acquire_downstream_tokens(config, credential)

        self.assertEqual(tokens["foundry"], "token-for-https://cognitiveservices.azure.com/.default")
        self.assertEqual(tokens["speech"], "token-for-https://cognitiveservices.azure.com/.default")
        self.assertEqual(
            credential.scopes,
            ["https://cognitiveservices.azure.com/.default", "https://cognitiveservices.azure.com/.default"],
        )

    def test_managed_identity_token_acquisition_failure_is_loud(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
        )

        with self.assertRaises(TokenAcquisitionError):
            acquire_downstream_tokens(config, RecordingCredential(fail=True))

    def test_speech_aad_authorization_token_uses_documented_rest_format(self) -> None:
        token = build_speech_aad_authorization_token(
            "/subscriptions/<subscription-id>/resourceGroups/rg-sparky/providers/Microsoft.CognitiveServices/accounts/sparky-speech-dev",
            "access-token",
        )

        self.assertEqual(
            token,
            "aad#/subscriptions/<subscription-id>/resourceGroups/rg-sparky/providers/Microsoft.CognitiveServices/accounts/sparky-speech-dev#access-token",
        )


if __name__ == "__main__":
    unittest.main()
