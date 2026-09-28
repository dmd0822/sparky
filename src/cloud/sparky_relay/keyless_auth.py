"""Helpers for the keyless Entra-to-relay-to-Foundry proof of path."""

from __future__ import annotations

import argparse
import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping


COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
DEFAULT_RELAY_AUDIENCE = "api://AzureADTokenExchange"
DEFAULT_DEVICE_SCOPE = f"{DEFAULT_RELAY_AUDIENCE}/.default"

_FORBIDDEN_DEVICE_SCOPE_AUDIENCES = (
    "https://cognitiveservices.azure.com",
    "https://ai.azure.com",
    "https://cognitive.microsoft.com",
)


@dataclass(frozen=True)
class AzureRelayConfig:
    """Configuration required for the keyless relay flow."""

    tenant_id: str
    client_id: str
    relay_url: str
    relay_audience: str = DEFAULT_RELAY_AUDIENCE
    device_scope: str = DEFAULT_DEVICE_SCOPE
    foundry_scope: str = COGNITIVE_SERVICES_SCOPE
    speech_scope: str = COGNITIVE_SERVICES_SCOPE

    def __post_init__(self) -> None:
        assert_device_scope_is_relay_audience(self.device_scope)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AzureRelayConfig":
        values = dict(os.environ if env is None else env)
        required = {
            "AZURE_TENANT_ID": "tenant_id",
            "AZURE_CLIENT_ID": "client_id",
            "SPARKY_RELAY_URL": "relay_url",
        }
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ValueError(
                "Missing required configuration values: " + ", ".join(missing)
            )

        return cls(
            tenant_id=values["AZURE_TENANT_ID"],
            client_id=values["AZURE_CLIENT_ID"],
            relay_url=values["SPARKY_RELAY_URL"],
            relay_audience=values.get("SPARKY_RELAY_AUDIENCE", DEFAULT_RELAY_AUDIENCE),
            device_scope=values.get("SPARKY_RELAY_DEVICE_SCOPE", DEFAULT_DEVICE_SCOPE),
            foundry_scope=values.get(
                "SPARKY_FOUNDRY_SCOPE",
                values.get("AZURE_COGNITIVE_SCOPE", COGNITIVE_SERVICES_SCOPE),
            ),
            speech_scope=values.get(
                "SPARKY_SPEECH_SCOPE",
                values.get("AZURE_COGNITIVE_SCOPE", COGNITIVE_SERVICES_SCOPE),
            ),
        )

    def build_device_code_payload(self) -> dict[str, str]:
        """Construct the Entra device-code request for a user or device."""

        return {
            "client_id": self.client_id,
            "scope": self.device_scope,
            "tenant": self.tenant_id,
        }

    def build_managed_identity_scope(self) -> str:
        """The Foundry scope consumed by the relay after it receives a valid token."""

        return self.foundry_scope

    def build_managed_identity_scopes(self) -> dict[str, str]:
        """Return downstream managed-identity scopes for each relay-to-service hop."""

        return {
            "foundry": self.foundry_scope,
            "speech": self.speech_scope,
        }

    def build_demo_sequence(self) -> dict[str, Any]:
        """Return the commands needed to exercise the proof-of-path sequence."""

        return {
            "device_code_url": (
                "https://login.microsoftonline.com/"
                f"{self.tenant_id}/oauth2/v2.0/devicecode"
            ),
            "token_url": (
                "https://login.microsoftonline.com/"
                f"{self.tenant_id}/oauth2/v2.0/token"
            ),
            "relay_url": self.relay_url,
            "device_code_payload": self.build_device_code_payload(),
            "relay_headers": {
                "Authorization": "Bearer <relay-audience-access-token>",
                "Content-Type": "application/json",
            },
            "hop_tokens": {
                "pi_to_relay": {
                    "holder": "Raspberry Pi public client",
                    "audience": self.relay_audience,
                    "scope": self.device_scope,
                    "must_never_be": "Azure AI / Cognitive Services bearer token, API key, or connection string",
                },
                "relay_to_foundry": {
                    "holder": "Relay system-assigned managed identity",
                    "audience": "https://cognitiveservices.azure.com",
                    "scope": self.foundry_scope,
                    "credential": "managed identity + Cognitive Services User RBAC",
                },
                "relay_to_speech": {
                    "holder": "Relay system-assigned managed identity",
                    "audience": "https://cognitiveservices.azure.com",
                    "scope": self.speech_scope,
                    "credential": "managed identity + Cognitive Services User RBAC",
                },
            },
            "relay_payloads": {
                "foundry_chat": {
                    "operation": "POST /ai/chat",
                    "managed_identity_scope": self.foundry_scope,
                    "resource": "foundry",
                },
                "speech_synthesis": {
                    "operation": "POST /speech/synthesize",
                    "managed_identity_scope": self.speech_scope,
                    "resource": "speech",
                    "sdk_auth_note": (
                        "Current Speech SDK docs prefer TokenCredential with a custom-domain endpoint; "
                        "REST or legacy authorization-token paths construct "
                        "aad#<speech-resource-id>#<aad-access-token>."
                    ),
                },
            },
            "curl_example": [
                "curl -X POST "
                "'https://login.microsoftonline.com/"
                + self.tenant_id
                + "/oauth2/v2.0/devicecode' "
                "-H 'Content-Type: application/x-www-form-urlencoded' "
                "--data-urlencode 'client_id="
                + self.client_id
                + "' "
                "--data-urlencode 'scope="
                + self.device_scope
                + "'",
                "curl -X POST "
                f"'{self.relay_url}/ai/chat' "
                "-H 'Authorization: Bearer <relay-audience-access-token>' "
                "-H 'Content-Type: application/json' "
                "--data '{\"prompt\":\"health check\"}'",
                "curl -X POST "
                f"'{self.relay_url}/speech/synthesize' "
                "-H 'Authorization: Bearer <relay-audience-access-token>' "
                "-H 'Content-Type: application/json' "
                "--data '{\"text\":\"Sparky keyless speech smoke test\"}'",
            ],
        }


def assert_device_scope_is_relay_audience(scope: str) -> None:
    """Reject scopes that would hand the Pi an Azure AI bearer token."""

    normalized = scope.strip().lower()
    if not normalized:
        raise ValueError("Device-hop scope must not be empty.")
    for forbidden in _FORBIDDEN_DEVICE_SCOPE_AUDIENCES:
        if normalized.startswith(forbidden) or forbidden in normalized:
            raise ValueError(
                "Device-hop scope must target the relay app registration, not Azure AI."
            )


def build_speech_aad_authorization_token(resource_id: str, aad_access_token: str) -> str:
    """Build the Speech REST/legacy authorization-token value for Entra auth."""

    if not resource_id or not aad_access_token:
        raise ValueError("Speech resource ID and Microsoft Entra access token are required.")
    return f"aad#{resource_id}#{aad_access_token}"


def _decode_jwt_segment(segment: str) -> dict[str, Any]:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def parse_unverified_jwt_claims(token: str) -> dict[str, Any]:
    """Decode unsigned JWT claims for spike validation tests.

    This helper does not verify signatures; production relay code must validate
    issuer signing keys before trusting claims.
    """

    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Expected a JWT with header and payload segments.")
    payload = _decode_jwt_segment(parts[1])
    if not isinstance(payload, dict):
        raise ValueError("JWT payload must decode to an object.")
    return payload


def expected_issuer(tenant_id: str) -> str:
    """Return the v2.0 Entra issuer expected for the device token."""

    return f"https://login.microsoftonline.com/{tenant_id}/v2.0"


def validate_relay_token_claims(claims: Mapping[str, Any], config: AzureRelayConfig) -> None:
    """Validate the device token audience and issuer before relay use."""

    audience = claims.get("aud")
    issuer = claims.get("iss")
    if audience != config.relay_audience:
        raise ValueError("Device token audience does not match the relay audience.")
    if issuer != expected_issuer(config.tenant_id):
        raise ValueError("Device token issuer does not match the configured tenant.")


def validate_relay_token(token: str, config: AzureRelayConfig) -> None:
    """Decode and validate a relay-bound device token."""

    validate_relay_token_claims(parse_unverified_jwt_claims(token), config)


class TokenAcquisitionError(RuntimeError):
    """Raised when managed-identity token acquisition fails."""


def acquire_downstream_access_token(scope: str, credential: Any) -> str:
    """Acquire a managed-identity token from an injected credential object."""

    try:
        token = credential.get_token(scope)
    except Exception as exc:  # pragma: no cover - exact SDK exception is injected.
        raise TokenAcquisitionError(f"Managed identity token acquisition failed for {scope}.") from exc

    value = getattr(token, "token", None)
    if value is None and isinstance(token, Mapping):
        value = token.get("token")
    if not isinstance(value, str) or not value:
        raise TokenAcquisitionError(f"Managed identity token acquisition returned no token for {scope}.")
    return value


def acquire_downstream_tokens(config: AzureRelayConfig, credential: Any) -> dict[str, str]:
    """Acquire relay-managed tokens for Foundry and Speech."""

    return {
        "foundry": acquire_downstream_access_token(config.foundry_scope, credential),
        "speech": acquire_downstream_access_token(config.speech_scope, credential),
    }


def validate_required_config(config: Mapping[str, str]) -> None:
    """Raise a ValueError when required config keys are missing."""

    AzureRelayConfig.from_env(config)


def build_demo_sequence(config: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build the proof-of-path demonstration payload for documentation and tests."""

    resolved = AzureRelayConfig.from_env(config)
    return resolved.build_demo_sequence()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-demo",
        action="store_true",
        help="Print the token-exchange proof-of-path sequence without contacting Azure.",
    )
    return parser


def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.print_demo:
        try:
            manifest = build_demo_sequence()
        except ValueError as exc:
            print(f"Configuration error: {exc}")
            return 1
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    print(
        "Keyless auth smoke check is configured via AZURE_TENANT_ID, "
        "AZURE_CLIENT_ID, SPARKY_RELAY_URL, SPARKY_RELAY_DEVICE_SCOPE, "
        "SPARKY_FOUNDRY_SCOPE, and SPARKY_SPEECH_SCOPE. "
        "Run with --print-demo to view the proof-of-path sequence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
