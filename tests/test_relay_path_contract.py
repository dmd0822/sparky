"""Pins the deployed relay URL contract to the routes the ASGI app registers.

`infra/environments/<env>/main.bicep` publishes `relayUrl` with an `/api` suffix,
every doc tells operators to set `SPARKY_RELAY_URL` to that value, and Azure
Container Apps ingress does not strip path prefixes. The relay app previously
registered bare paths only, so `POST ${SPARKY_RELAY_URL}/ai/chat` resolved to
`/api/ai/chat` and fell through to a 404. These tests fail if the infra output
suffix and the registered routes ever drift apart again.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from src.cloud.sparky_relay.relay_api import REQUEST_SCHEMAS

REPO_ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = REPO_ROOT / "infra" / "environments"
RELAY_URL_OUTPUT = re.compile(
    r"output\s+relayUrl\s+string\s*=\s*'https://\$\{relay\.outputs\.ingressFqdn\}(?P<suffix>[^']*)'"
)


def relay_url_suffixes() -> dict[str, str]:
    """Return the path suffix each environment appends to the relay FQDN."""
    suffixes: dict[str, str] = {}
    for entrypoint in sorted(ENVIRONMENTS.glob("*/main.bicep")):
        match = RELAY_URL_OUTPUT.search(entrypoint.read_text(encoding="utf-8"))
        if match is None:
            raise AssertionError(
                f"{entrypoint} does not output relayUrl as "
                "'https://${relay.outputs.ingressFqdn}<suffix>'."
            )
        suffixes[entrypoint.parent.name] = match.group("suffix")
    return suffixes


class RelayUrlOutputTests(unittest.TestCase):
    def test_every_environment_publishes_a_relay_url(self) -> None:
        suffixes = relay_url_suffixes()
        self.assertTrue(suffixes, "No infra/environments/*/main.bicep files were found.")

    def test_environments_agree_on_the_relay_url_suffix(self) -> None:
        suffixes = relay_url_suffixes()
        self.assertEqual(
            len(set(suffixes.values())),
            1,
            "dev and prod must advertise the same relay URL shape so one client "
            f"configuration works against both: {suffixes}",
        )


class RelayRouteContractTests(unittest.TestCase):
    """The deployed relayUrl plus each documented path must resolve to a route."""

    def setUp(self) -> None:
        try:
            from starlette.routing import Match
        except ImportError as exc:  # pragma: no cover - minimal CI images.
            raise unittest.SkipTest("Starlette is not installed.") from exc
        from src.cloud.sparky_relay.asgi import create_app

        self.match = Match
        self.app = create_app()

    def _matches(self, method: str, path: str) -> bool:
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "root_path": "",
            "headers": [],
        }
        return any(
            route.matches(scope)[0] is self.match.FULL for route in self.app.router.routes
        )

    def test_bare_paths_are_served(self) -> None:
        for name, schema in REQUEST_SCHEMAS.items():
            with self.subTest(route=name):
                self.assertTrue(
                    self._matches(schema["method"], schema["path"]),
                    f"{schema['method']} {schema['path']} is not routed by the relay app.",
                )

    def test_published_relay_url_paths_are_served(self) -> None:
        for environment, suffix in relay_url_suffixes().items():
            for name, schema in REQUEST_SCHEMAS.items():
                routed = f"{suffix}{schema['path']}"
                with self.subTest(environment=environment, route=name, path=routed):
                    self.assertTrue(
                        self._matches(schema["method"], routed),
                        f"{environment} publishes relayUrl with suffix {suffix!r}, so "
                        f"{schema['method']} {routed} reaches the container, but the "
                        "relay app does not register that path.",
                    )

    def test_prefixed_requests_are_normalised_for_the_relay_core(self) -> None:
        from src.cloud.sparky_relay.asgi import API_PREFIX, relay_path

        for name, schema in REQUEST_SCHEMAS.items():
            with self.subTest(route=name):
                self.assertEqual(
                    relay_path(f"{API_PREFIX}{schema['path']}"),
                    schema["path"],
                    "The relay core routes on bare paths, so prefixed requests must be "
                    "normalised before they reach it.",
                )
                self.assertEqual(relay_path(schema["path"]), schema["path"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
