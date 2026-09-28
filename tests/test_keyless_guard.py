"""Static policy tests for the keyless Azure AI auth spike."""

from __future__ import annotations

from pathlib import Path
import unittest

from src.cloud.sparky_relay.keyless_guard import assert_no_key_fallbacks, scan_text


ROOT = Path(__file__).parents[1]
SPIKE_DOC = ROOT / "docs" / "keyless-auth-spike.md"


class KeylessGuardScannerTests(unittest.TestCase):
    def test_repo_code_config_and_infra_have_no_key_based_fallbacks(self) -> None:
        assert_no_key_fallbacks(ROOT)

    def test_scanner_fails_loudly_on_subscription_key_fallback(self) -> None:
        text = "headers = {'Ocp-Apim-Subscription-Key': configured_key}"

        findings = scan_text(Path("example.py"), text)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern_name, "subscription-key-header")

    def test_scanner_fails_loudly_on_connection_string_fallback(self) -> None:
        text = "value = 'DefaultEndpointsProtocol=https;AccountKey=placeholder'"

        findings = scan_text(Path("example.bicep"), text)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern_name, "account-key-connection")


class KeylessAuthSpikeDocPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SPIKE_DOC.read_text(encoding="utf-8")

    def test_spike_doc_contains_required_security_sections(self) -> None:
        for heading in (
            "## Three-hop token model",
            "## Raspberry Pi enrollment steps",
            "## Explicitly ruled out",
            "## Negative-case key fallback verification",
            "## Reproducible smoke test",
            "## Hardware-in-the-loop validation",
            "## Blocking findings and open risks",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.text)

    def test_spike_doc_records_deployment_target_and_subscription_policy(self) -> None:
        self.assertIn("rg-sparky", self.text)
        self.assertIn("southcentralus", self.text)
        self.assertIn("AZURE_SUBSCRIPTION_ID", self.text)
        self.assertIn("az account set", self.text)
        self.assertIn("sparky-<resource>-<env>", self.text)
        self.assertIn("sparkyscr<env>", self.text)

    def test_spike_doc_states_pi_never_receives_ai_credentials(self) -> None:
        self.assertIn("Pi never receives Azure AI bearer tokens", self.text)
        self.assertIn("relay-audience token only", self.text)
        self.assertIn("Cognitive Services User", self.text)

    def test_spike_doc_records_current_speech_entra_auth_finding(self) -> None:
        self.assertIn("Speech SDK", self.text)
        self.assertIn("TokenCredential", self.text)
        self.assertIn("aad#<speech-resource-id>#<aad-access-token>", self.text)


if __name__ == "__main__":
    unittest.main()
