"""Tests for the keyless auth proof-of-path helpers."""

import unittest

from src.cloud.sparky_relay.keyless_auth import AzureRelayConfig, build_demo_sequence, validate_required_config


class KeylessAuthSpikeTests(unittest.TestCase):
    def test_config_requires_required_values(self) -> None:
        with self.assertRaises(ValueError):
            AzureRelayConfig.from_env({})

    def test_device_code_payload_contains_expected_fields(self) -> None:
        config = AzureRelayConfig(
            tenant_id="tenant-123",
            client_id="client-456",
            relay_url="https://relay.example.test",
        )

        payload = config.build_device_code_payload()

        self.assertEqual(payload["client_id"], "client-456")
        self.assertEqual(payload["tenant"], "tenant-123")
        self.assertEqual(payload["scope"], "https://cognitiveservices.azure.com/.default")

    def test_demo_sequence_uses_relay_and_audience(self) -> None:
        payload = build_demo_sequence(
            {
                "AZURE_TENANT_ID": "tenant-123",
                "AZURE_CLIENT_ID": "client-456",
                "SPARKY_RELAY_URL": "https://relay.example.test",
            }
        )

        self.assertIn("https://login.microsoftonline.com/tenant-123/oauth2/v2.0/devicecode", payload["device_code_url"])
        self.assertEqual(payload["relay_url"], "https://relay.example.test")
        self.assertEqual(payload["relay_payload"]["audience"], "api://AzureADTokenExchange")

    def test_validate_required_config_accepts_valid_values(self) -> None:
        validate_required_config(
            {
                "AZURE_TENANT_ID": "tenant-123",
                "AZURE_CLIENT_ID": "client-456",
                "SPARKY_RELAY_URL": "https://relay.example.test",
            }
        )


if __name__ == "__main__":
    unittest.main()
