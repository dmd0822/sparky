"""Tests for the relay-auth smoke harness."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts" / "relay_auth_smoke.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("relay_auth_smoke", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MutableClock:
    def __init__(self, start: float = 100.0) -> None:
        self.value = start
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class RelayAuthSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_script_module()
        self.env = {
            "AZURE_TENANT_ID": "tenant-123",
            "AZURE_CLIENT_ID": "client-456",
            "SPARKY_RELAY_URL": "https://relay.example.test/api",
            "SPARKY_RELAY_AUDIENCE": "api://relay-app-id",
            "SPARKY_RELAY_DEVICE_SCOPE": "api://relay-app-id/.default",
        }
        self.config = self.module.load_config(self.env)

    def test_scope_guard_rejects_forbidden_device_scope(self) -> None:
        env = dict(self.env)
        env["SPARKY_RELAY_DEVICE_SCOPE"] = "https://cognitiveservices.azure.com/.default"

        with self.assertRaisesRegex(self.module.SmokeFailure, "relay app registration"):
            self.module.load_config(env)

    def test_device_code_polling_handles_pending_then_success(self) -> None:
        token = self.module.build_unsigned_jwt(
            {
                "aud": self.config.relay_audience,
                "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
                "tid": "tenant-123",
                "exp": 999999,
                "scp": "Relay.Access",
            }
        )
        post = self.module.QueuePostForm(
            [
                {"error": "authorization_pending"},
                {"access_token": token},
            ]
        )
        clock = MutableClock()
        session = self.module.DeviceCodeSession("device", "USER", "https://verify", 600, 3)

        result = self.module.poll_for_token(
            self.config,
            session,
            post,
            sleep=clock.sleep,
            clock=clock.clock,
        )

        self.assertEqual(result, token)
        self.assertEqual(clock.sleeps, [3])
        self.assertEqual(len(post.calls), 2)

    def test_device_code_polling_honors_slow_down_interval(self) -> None:
        token = self.module.build_unsigned_jwt(
            {
                "aud": self.config.relay_audience,
                "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
                "tid": "tenant-123",
                "exp": 999999,
                "scp": "Relay.Access",
            }
        )
        post = self.module.QueuePostForm(
            [
                {"error": "slow_down"},
                {"access_token": token},
            ]
        )
        clock = MutableClock()
        session = self.module.DeviceCodeSession("device", "USER", "https://verify", 600, 2)

        result = self.module.poll_for_token(
            self.config,
            session,
            post,
            sleep=clock.sleep,
            clock=clock.clock,
        )

        self.assertEqual(result, token)
        self.assertEqual(clock.sleeps, [7])

    def test_device_code_polling_fails_on_expired_token(self) -> None:
        post = self.module.QueuePostForm([{"error": "expired_token"}])
        session = self.module.DeviceCodeSession("device", "USER", "https://verify", 600, 1)

        with self.assertRaisesRegex(self.module.SmokeFailure, "expired_token"):
            self.module.poll_for_token(self.config, session, post, sleep=lambda _seconds: None)

    def test_audience_assertion_accepts_relay_and_rejects_graph(self) -> None:
        relay_token = self.module.build_unsigned_jwt(
            {
                "aud": self.config.relay_audience,
                "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
                "tid": "tenant-123",
                "exp": 999999,
            }
        )
        graph_token = self.module.build_unsigned_jwt(
            {
                "aud": "https://graph.microsoft.com",
                "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
                "tid": "tenant-123",
                "exp": 999999,
            }
        )

        self.assertEqual(self.module.inspect_token(relay_token, self.config).claims["aud"], self.config.relay_audience)
        with self.assertRaisesRegex(self.module.SmokeFailure, "audience"):
            self.module.inspect_token(graph_token, self.config)

    def test_correlation_id_echo_is_required(self) -> None:
        ok = self.module.HttpResult(200, {"x-correlation-id": "cid-1"}, "{}")
        missing = self.module.HttpResult(200, {}, "{}")

        self.module.assert_correlation_echo(ok, "cid-1")
        with self.assertRaisesRegex(self.module.SmokeFailure, "correlation"):
            self.module.assert_correlation_echo(missing, "cid-1")

    def test_full_negative_matrix_passes_against_fake_relay(self) -> None:
        fake = self.module.FakeTransport()
        fake.tenant_id = self.config.tenant_id
        fake.audience = self.config.relay_audience
        claims = self.module._valid_claims(self.config.tenant_id, self.config.relay_audience, fake.now)

        result = self.module.run_negative_matrix(
            self.config,
            claims,
            fake.request,
            (),
            out=StringIO(),
        )

        self.assertEqual(result.status, self.module.Status.PASS)
        self.assertEqual(len(fake.http_calls), len(self.module.ENDPOINTS) * len(self.module.NEGATIVE_CASES))

    def test_ci_mode_makes_zero_live_network_calls(self) -> None:
        def fail_form(_url, _data):
            raise AssertionError("live form transport called")

        def fail_http(_method, _url, _headers, _body):
            raise AssertionError("live relay transport called")

        original_form = self.module.live_post_form
        original_http = self.module.live_http_call
        self.module.live_post_form = fail_form
        self.module.live_http_call = fail_http
        try:
            output = StringIO()
            exit_code = self.module.main(["--ci"], out=output)
        finally:
            self.module.live_post_form = original_form
            self.module.live_http_call = original_http

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertIn("Relay-auth smoke PASS", output.getvalue())
        self.assertIn("Negative auth matrix", output.getvalue())


if __name__ == "__main__":
    unittest.main()
