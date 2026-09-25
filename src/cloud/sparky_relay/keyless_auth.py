"""Helpers for the keyless Entra-to-relay-to-Foundry proof of path."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode


@dataclass(frozen=True)
class AzureRelayConfig:
    """Configuration required for the keyless relay flow."""

    tenant_id: str
    client_id: str
    relay_url: str
    audience: str = "api://AzureADTokenExchange"
    scope: str = "https://cognitiveservices.azure.com/.default"

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
            audience=values.get("AZURE_TOKEN_AUDIENCE", "api://AzureADTokenExchange"),
            scope=values.get("AZURE_COGNITIVE_SCOPE", "https://cognitiveservices.azure.com/.default"),
        )

    def build_device_code_payload(self) -> dict[str, str]:
        """Construct the Entra device-code request for a user or device."""

        return {
            "client_id": self.client_id,
            "scope": self.scope,
            "tenant": self.tenant_id,
        }

    def build_managed_identity_scope(self) -> str:
        """The Azure resource scope consumed by the relay after it receives a valid token."""

        return self.scope

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
            "relay_headers": {
                "Authorization": "Bearer <entra-token>",
                "Content-Type": "application/json",
            },
            "relay_payload": {
                "resource": "https://cognitiveservices.azure.com",
                "scope": self.scope,
                "audience": self.audience,
            },
            "curl_example": [
                "curl -X POST "
                f"'{self.relay_url}/token' "
                "-H 'Authorization: Bearer <entra-token>' "
                "-H 'Content-Type: application/json' "
                "--data '{\"resource\":\"https://cognitiveservices.azure.com\",\"scope\":\""
                + self.scope
                + "\"}'",
                "curl -H 'Authorization: Bearer <managed-identity-token>' "
                f"'{self.relay_url}/ai/chat'",
            ],
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
        "AZURE_CLIENT_ID, and SPARKY_RELAY_URL. "
        "Run with --print-demo to view the proof-of-path sequence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
