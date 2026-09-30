#!/usr/bin/env python3
"""Relay authentication smoke harness for Raspberry Pi operators.

Live mode performs Entra device-code sign-in, checks the relay-audience token,
and exercises the authenticated relay endpoints. ``--ci`` uses local fakes so the
same state machine and reporting path can run without Azure or network access.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Iterable, Mapping, TextIO
from urllib import error, parse, request
import uuid


ROOT = Path(__file__).resolve().parents[1]
CLOUD_SRC = ROOT / "src" / "cloud"
if CLOUD_SRC.exists():
    sys.path.insert(0, str(CLOUD_SRC))

from sparky_relay.keyless_auth import (  # noqa: E402
    AzureRelayConfig,
    assert_device_scope_is_relay_audience,
    expected_issuer,
)


PostForm = Callable[[str, Mapping[str, str]], Mapping[str, Any]]
HttpCall = Callable[[str, str, Mapping[str, str], Mapping[str, Any] | None], "HttpResult"]
Sleep = Callable[[float], None]
Clock = Callable[[], float]

FORBIDDEN_DEVICE_SCOPE_PREFIXES = (
    "https://cognitiveservices.azure.com",
    "https://ai.azure.com",
    "https://cognitive.microsoft.com",
)
GRAPH_AUDIENCES = {
    "https://graph.microsoft.com",
    "00000003-0000-0000-c000-000000000000",
}
REQUIRED_ENV = (
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "SPARKY_RELAY_URL",
    "SPARKY_RELAY_AUDIENCE",
    "SPARKY_RELAY_DEVICE_SCOPE",
)
ENDPOINTS = (
    ("health", "GET", "/health", None),
    ("chat", "POST", "/ai/chat", {"prompt": "health check"}),
    ("vision", "POST", "/ai/vision", {"image": "******"}),
    ("speech", "POST", "/speech/synthesize", {"text": "Sparky keyless speech smoke test"}),
)
NEGATIVE_CASES = (
    "no-token",
    "malformed-token",
    "expired-token",
    "graph-audience-token",
    "missing-grant-token",
)
CHECKLIST = (
    "python -m unittest discover -s tests passed locally.",
    "python -m sparky_relay.keyless_auth --print-demo printed the three-hop manifest without contacting Azure.",
    "The keyless guard caught the deliberate scratch-file fallback and the scratch file was removed.",
    "The device-scope guard rejected the Cognitive Services device scope.",
    "Pi device-code enrollment requested only the relay app scope.",
    "The Pi never received an Azure AI bearer token, credential, client secret, or connection string.",
    "The relay validated the Pi token issuer and relay audience before downstream calls.",
    "The relay used its system-assigned managed identity for Foundry.",
    "The relay used its system-assigned managed identity for Speech.",
    "Relay logs showed token purpose, issuer, audience, and status only; no raw token or key material was logged.",
    "Foundry quota and Speech feature availability were verified or recorded as live-environment blockers.",
    "RBAC assignment behavior was verified after propagation or recorded as a live-environment blocker.",
)


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class StepResult:
    number: int
    title: str
    status: Status
    message: str

    @property
    def ok(self) -> bool:
        return self.status is not Status.FAIL


@dataclass(frozen=True)
class RunResult:
    ok: bool
    message: str
    results: tuple[StepResult, ...]


@dataclass(frozen=True)
class DeviceCodeSession:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    message: str = ""


@dataclass(frozen=True)
class TokenResult:
    access_token: str
    claims: Mapping[str, Any]


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    headers: Mapping[str, str]
    body_text: str

    def json_body(self) -> Mapping[str, Any]:
        if not self.body_text.strip():
            return {}
        value = json.loads(self.body_text)
        if not isinstance(value, dict):
            raise ValueError("Response body must be a JSON object.")
        return value


class SmokeFailure(RuntimeError):
    """Raised when a smoke step fails."""


class FakeTransport:
    """No-network transport used by --ci and unit tests."""

    def __init__(self) -> None:
        self.form_calls: list[tuple[str, Mapping[str, str]]] = []
        self.http_calls: list[tuple[str, str, Mapping[str, str], Mapping[str, Any] | None]] = []
        self.token_poll_count = 0
        self.now = 1_800_000_000
        self.tenant_id = "tenant-ci"
        self.audience = "api://relay-ci"

    def post_form(self, url: str, data: Mapping[str, str]) -> Mapping[str, Any]:
        self.form_calls.append((url, dict(data)))
        if url.endswith("/devicecode"):
            self.tenant_id = _tenant_from_url(url) or self.tenant_id
            scope = data.get("scope", self.audience + "/.default")
            self.audience = _audience_from_scope(scope)
            return {
                "device_code": "ci-device-code",
                "user_code": "CI-CODE",
                "verification_uri": "https://microsoft.com/devicelogin",
                "expires_in": 600,
                "interval": 0,
                "message": "CI sign-in simulated.",
            }
        if url.endswith("/token"):
            self.token_poll_count += 1
            return {"access_token": build_unsigned_jwt(_valid_claims(self.tenant_id, self.audience, self.now))}
        raise AssertionError(f"unexpected fake form URL {url}")

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any] | None,
    ) -> HttpResult:
        self.http_calls.append((method, url, dict(headers), None if body is None else dict(body)))
        correlation_id = _header(headers, "x-correlation-id") or str(uuid.uuid4())
        auth_value = _header(headers, "authorization")
        path = "/" + url.split("/", 3)[3].split("?", 1)[0] if "://" in url and len(url.split("/", 3)) > 3 else url
        if not auth_value:
            return _fake_error(401, "missing_token", correlation_id)
        scheme, _, token = auth_value.partition(" ")
        if scheme.lower() != "bearer" or len(token.split(".")) != 3:
            return _fake_error(401, "malformed_token", correlation_id)
        try:
            claims = decode_unverified_claims(token)
        except ValueError:
            return _fake_error(401, "invalid_token", correlation_id)
        audience = claims.get("aud")
        if audience in GRAPH_AUDIENCES or audience != self.audience:
            return _fake_error(401, "invalid_audience", correlation_id)
        exp = _int_claim(claims, "exp")
        if exp is None or exp < self.now:
            return _fake_error(401, "token_expired", correlation_id)
        if not _claims_have_grant(claims):
            return _fake_error(403, "missing_grant", correlation_id)
        bodies: dict[str, Mapping[str, Any]] = {
            "/health": {"status": "ok", "authenticated": True, "correlation_id": correlation_id},
            "/ai/chat": {"reply": "woof", "correlation_id": correlation_id},
            "/ai/vision": {"caption": "robot dog", "labels": ["dog", "robot"], "correlation_id": correlation_id},
            "/speech/synthesize": {"audio": "******", "audio_format": "wav", "correlation_id": correlation_id},
        }
        body_key = path[4:] if path.startswith("/api/") else path
        if body_key not in bodies:
            return _fake_error(404, "not_found", correlation_id)
        return HttpResult(200, {"x-correlation-id": correlation_id}, json.dumps(bodies[body_key]))


class QueuePostForm:
    """Deterministic POST-form fake for unit tests."""

    def __init__(self, responses: Iterable[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def __call__(self, url: str, data: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append((url, dict(data)))
        if not self.responses:
            raise AssertionError("no queued form response")
        response = self.responses.pop(0)
        if "error" in response:
            return dict(response)
        return dict(response)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Raspberry Pi relay-auth smoke test. Live mode performs device-code "
            "sign-in and calls the deployed relay; --ci runs deterministic fakes with no network."
        )
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Run end-to-end against in-process fakes: no network, no Azure, no interactive sign-in.",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=900,
        help="Maximum seconds to poll device-code sign-in before failing (default: 900).",
    )
    return parser


def load_config(env: Mapping[str, str]) -> AzureRelayConfig:
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if missing:
        raise SmokeFailure("Missing required environment values: " + ", ".join(missing))
    scope = env["SPARKY_RELAY_DEVICE_SCOPE"].strip()
    normalized = scope.lower()
    for prefix in FORBIDDEN_DEVICE_SCOPE_PREFIXES:
        if normalized.startswith(prefix):
            raise SmokeFailure(
                "SPARKY_RELAY_DEVICE_SCOPE must target the relay app registration, not Azure AI."
            )
    try:
        assert_device_scope_is_relay_audience(scope)
        return AzureRelayConfig.from_env(env)
    except ValueError as exc:
        raise SmokeFailure(str(exc)) from exc


def credential_shaped_env_names(env: Mapping[str, str]) -> tuple[str, ...]:
    markers = (
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "PASSWD",
        "PWD",
        "PRIVATE",
        "CERT",
        "KEY",
        "CONNECTION" + "STRING",
    )
    allowed_public = {"AZURE_TENANT_ID", "AZURE_CLIENT_ID", "SPARKY_RELAY_AUDIENCE", "SPARKY_RELAY_DEVICE_SCOPE"}
    names = []
    for name, value in env.items():
        upper = name.upper()
        if not value or upper in allowed_public:
            continue
        if not upper.startswith(("AZURE", "SPARKY", "SPEECH", "OPENAI", "COGNITIVE", "FOUNDRY")):
            continue
        if any(marker in upper for marker in markers):
            names.append(name)
    return tuple(sorted(names, key=str.upper))


def request_device_code(config: AzureRelayConfig, post_form: PostForm) -> DeviceCodeSession:
    url = _device_code_url(config.tenant_id)
    response = post_form(url, {"client_id": config.client_id, "scope": config.device_scope})
    if response.get("error"):
        raise SmokeFailure(f"Device-code request failed: {response.get('error')}")
    required = ("device_code", "user_code", "verification_uri", "expires_in", "interval")
    missing = [name for name in required if name not in response]
    if missing:
        raise SmokeFailure("Device-code response missing: " + ", ".join(missing))
    return DeviceCodeSession(
        device_code=str(response["device_code"]),
        user_code=str(response["user_code"]),
        verification_uri=str(response["verification_uri"]),
        expires_in=int(response["expires_in"]),
        interval=max(0, int(response["interval"])),
        message=str(response.get("message", "")),
    )


def poll_for_token(
    config: AzureRelayConfig,
    session: DeviceCodeSession,
    post_form: PostForm,
    *,
    sleep: Sleep = time.sleep,
    clock: Clock = time.time,
    max_wait_seconds: int | None = None,
) -> str:
    token_url = _token_url(config.tenant_id)
    interval = session.interval
    started = clock()
    expires_at = started + session.expires_in
    if max_wait_seconds is not None:
        expires_at = min(expires_at, started + max_wait_seconds)
    while clock() <= expires_at:
        response = post_form(
            token_url,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": config.client_id,
                "device_code": session.device_code,
            },
        )
        token = response.get("access_token")
        if isinstance(token, str) and token:
            return token
        code = str(response.get("error", ""))
        if code == "authorization_pending":
            sleep(interval)
            continue
        if code == "slow_down":
            interval += 5
            sleep(interval)
            continue
        if code in {"expired_token", "invalid_grant"}:
            raise SmokeFailure(f"Device-code polling failed: {code}")
        if code:
            raise SmokeFailure(f"Device-code polling failed: {code}")
        raise SmokeFailure("Device-code polling returned no access token and no error code.")
    raise SmokeFailure("Device-code polling expired before sign-in completed.")


def inspect_token(token: str, config: AzureRelayConfig) -> TokenResult:
    claims = decode_unverified_claims(token)
    audience = claims.get("aud")
    audiences = set(audience if isinstance(audience, list) else [audience])
    if config.relay_audience not in audiences:
        raise SmokeFailure("Device token audience does not match SPARKY_RELAY_AUDIENCE.")
    if audiences & GRAPH_AUDIENCES:
        raise SmokeFailure("Device token audience is Microsoft Graph, not the relay.")
    forbidden = [prefix for prefix in FORBIDDEN_DEVICE_SCOPE_PREFIXES if any(str(aud).startswith(prefix) for aud in audiences)]
    if forbidden:
        raise SmokeFailure("Device token audience targets Azure AI instead of the relay.")
    return TokenResult(token, claims)


def run_happy_path(
    config: AzureRelayConfig,
    token: str,
    http_call: HttpCall,
    leak_values: Iterable[str],
    *,
    out: TextIO,
) -> list[StepResult]:
    results: list[StepResult] = []
    for index, (name, method, path, body) in enumerate(ENDPOINTS, start=3):
        correlation_id = str(uuid.uuid4())
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "x-correlation-id": correlation_id,
        }
        result = http_call(method, _join_url(config.relay_url, path), headers, body)
        try:
            assert_status(result, {200})
            assert_correlation_echo(result, correlation_id)
            assert_no_response_leak(result, [*leak_values, token])
        except SmokeFailure as exc:
            results.append(_result(index, f"Happy path {name}", Status.FAIL, str(exc)))
            continue
        results.append(_result(index, f"Happy path {name}", Status.PASS, f"{result.status_code}; correlation id echoed"))
        print(f"Endpoint {name}: PASS ({result.status_code}, correlation id echoed)", file=out)
    return results


def run_negative_matrix(
    config: AzureRelayConfig,
    base_claims: Mapping[str, Any],
    http_call: HttpCall,
    leak_values: Iterable[str],
    *,
    out: TextIO,
) -> StepResult:
    failures: list[str] = []
    total = 0
    for endpoint_name, method, path, body in ENDPOINTS:
        for case_name, token in negative_tokens(config, base_claims):
            total += 1
            correlation_id = str(uuid.uuid4())
            headers = {"Content-Type": "application/json", "x-correlation-id": correlation_id}
            if token is not None:
                headers["Authorization"] = "Bearer " + token
            result = http_call(method, _join_url(config.relay_url, path), headers, body)
            try:
                assert_status(result, {401, 403})
                assert_correlation_echo(result, correlation_id)
                assert_structured_error(result)
                material = [*leak_values]
                if token:
                    material.append(token)
                assert_no_response_leak(result, material)
            except SmokeFailure as exc:
                failures.append(f"{endpoint_name}/{case_name}: {exc}")
    if failures:
        for failure in failures:
            print("Negative matrix failure: " + failure, file=out)
        return _result(7, "Negative auth matrix", Status.FAIL, f"{len(failures)} of {total} cases failed")
    print(f"Negative auth matrix: PASS ({total} cases returned structured 401/403)", file=out)
    return _result(7, "Negative auth matrix", Status.PASS, f"{total} cases returned structured 401/403")


def negative_tokens(config: AzureRelayConfig, base_claims: Mapping[str, Any]) -> tuple[tuple[str, str | None], ...]:
    now = int(time.time())
    relay_claims = dict(base_claims)
    relay_claims.setdefault("iss", expected_issuer(config.tenant_id))
    relay_claims.setdefault("tid", config.tenant_id)
    relay_claims.setdefault("aud", config.relay_audience)
    relay_claims.setdefault("sub", "smoke-device")
    expired = dict(relay_claims, exp=now - 3600, scp="Relay.Access")
    graph = dict(relay_claims, aud="https://graph.microsoft.com", exp=now + 3600, scp="Relay.Access")
    missing = dict(relay_claims, exp=now + 3600)
    missing.pop("scp", None)
    missing.pop("roles", None)
    missing.pop("sparky_enrolled", None)
    return (
        ("no-token", None),
        ("malformed-token", "not-a-jwt"),
        ("expired-token", build_unsigned_jwt(expired)),
        ("graph-audience-token", build_unsigned_jwt(graph)),
        ("missing-grant-token", build_unsigned_jwt(missing)),
    )


def assert_status(result: HttpResult, expected: set[int]) -> None:
    if result.status_code not in expected:
        raise SmokeFailure(f"expected status {sorted(expected)}, got {result.status_code}")


def assert_correlation_echo(result: HttpResult, expected: str) -> None:
    header_value = _header(result.headers, "x-correlation-id")
    body_value = None
    try:
        body = result.json_body()
        body_value = body.get("correlation_id")
    except (ValueError, json.JSONDecodeError):
        body = {}
    if header_value != expected and body_value != expected:
        raise SmokeFailure("correlation id was not echoed in response headers or body")


def assert_structured_error(result: HttpResult) -> None:
    try:
        body = result.json_body()
    except (ValueError, json.JSONDecodeError) as exc:
        raise SmokeFailure("error response is not JSON") from exc
    error_obj = body.get("error")
    if not isinstance(error_obj, dict) or not error_obj.get("code"):
        raise SmokeFailure("error response is not structured")


def assert_no_response_leak(result: HttpResult, values: Iterable[str]) -> None:
    text = result.body_text
    for value in values:
        if isinstance(value, str) and len(value) >= 8 and value in text:
            raise SmokeFailure("response body contained configuration or credential material")


def decode_unverified_claims(token: str) -> Mapping[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Expected three JWT segments.")
    payload = _b64url_decode(parts[1])
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JWT payload must be an object.")
    return value


def build_unsigned_jwt(claims: Mapping[str, Any]) -> str:
    header = {"alg": "none"}
    return _b64url_json(header) + "." + _b64url_json(dict(claims)) + "."


def live_post_form(url: str, data: Mapping[str, str]) -> Mapping[str, Any]:
    encoded = parse.urlencode(data).encode("utf-8")
    req = request.Request(url, data=encoded, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with request.urlopen(req, timeout=30) as response:
            return _load_json_response(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        return _load_json_response(exc.read().decode("utf-8"))
    except error.URLError as exc:
        raise SmokeFailure(f"Network request failed: {exc.reason}") from exc


def live_http_call(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Mapping[str, Any] | None,
) -> HttpResult:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, headers=dict(headers), method=method)
    try:
        with request.urlopen(req, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")
            return HttpResult(response.status, dict(response.headers.items()), text)
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return HttpResult(exc.code, dict(exc.headers.items()), text)
    except error.URLError as exc:
        raise SmokeFailure(f"Relay request failed: {exc.reason}") from exc


def run_check(
    *,
    env: Mapping[str, str] | None = None,
    ci: bool = False,
    post_form: PostForm | None = None,
    http_call: HttpCall | None = None,
    sleep: Sleep = time.sleep,
    clock: Clock = time.time,
    poll_timeout: int = 900,
    out: TextIO = sys.stdout,
) -> RunResult:
    env = dict(os.environ if env is None else env)
    if ci:
        env = _ci_env(env)
        fake = FakeTransport()
        post_form = fake.post_form if post_form is None else post_form
        http_call = fake.request if http_call is None else http_call
        sleep = (lambda _seconds: None) if sleep is time.sleep else sleep
    else:
        post_form = live_post_form if post_form is None else post_form
        http_call = live_http_call if http_call is None else http_call

    results: list[StepResult] = []
    token = ""
    claims: Mapping[str, Any] = {}
    config: AzureRelayConfig | None = None
    credential_names: tuple[str, ...] = ()
    try:
        config = load_config(env)
        credential_names = credential_shaped_env_names(env)
        message = "required env present; device scope targets relay"
        if credential_names:
            message += "; credential-shaped env names present: " + ", ".join(credential_names)
        else:
            message += "; no credential-shaped env names found"
        results.append(_result(1, "Preflight and local credential scan", Status.PASS, message))
        _print_step(results[-1], out)

        session = request_device_code(config, post_form)
        print("Device-code sign-in:", file=out)
        print(f"  user_code: {session.user_code}", file=out)
        print(f"  verification_uri: {session.verification_uri}", file=out)
        if session.message:
            print(f"  message: {session.message}", file=out)
        token = poll_for_token(config, session, post_form, sleep=sleep, clock=clock, max_wait_seconds=poll_timeout)
        token_result = inspect_token(token, config)
        claims = token_result.claims
        audience = claims.get("aud")
        issuer = claims.get("iss")
        expiry = claims.get("exp")
        results.append(_result(2, "Device-code token audience", Status.PASS, f"audience={audience}; issuer={issuer}; exp={expiry}"))
        _print_step(results[-1], out)
        print("IMPORTANT: the Pi token audience is the relay app registration, not Azure AI or Microsoft Graph.", file=out)

        leak_values = _leak_values(config, env, token, credential_names)
        results.extend(run_happy_path(config, token, http_call, leak_values, out=out))
        results.append(run_negative_matrix(config, claims, http_call, leak_values, out=out))
    except Exception as exc:  # noqa: BLE001 - convert to CLI summary.
        if isinstance(exc, KeyboardInterrupt):
            raise
        results.append(_result(len(results) + 1, "Unhandled smoke failure", Status.FAIL, f"{type(exc).__name__}: {exc}"))
        _print_step(results[-1], out)

    ok = all(result.ok for result in results)
    return RunResult(ok, "Relay-auth smoke PASS" if ok else "Relay-auth smoke FAIL", tuple(results))


def print_summary(results: Iterable[StepResult], out: TextIO = sys.stdout) -> None:
    results = tuple(results)
    print("", file=out)
    print("Summary:", file=out)
    for result in results:
        print(f"  {result.number:>2}. {result.status.value:<4} {result.title}: {result.message}", file=out)


def print_checklist(results: Iterable[StepResult], out: TextIO = sys.stdout) -> None:
    result_map = {result.title: result.status for result in results}
    smoke_ok = all(result.status is Status.PASS for result in results)
    print("", file=out)
    print("Verification checklist mapping:", file=out)
    for index, item in enumerate(CHECKLIST, start=1):
        marker = "[x]" if _checklist_item_passed(index, smoke_ok, result_map) else "[ ]"
        print(f"  {marker} {index:>2}. {item}", file=out)


def _checklist_item_passed(index: int, smoke_ok: bool, result_map: Mapping[str, Status]) -> bool:
    if index in {1, 2, 3, 4}:
        return False
    if index in {5, 6}:
        return result_map.get("Preflight and local credential scan") is Status.PASS and result_map.get("Device-code token audience") is Status.PASS
    if index == 7:
        return smoke_ok
    if index in {8, 9, 11, 12}:
        return False
    if index == 10:
        return smoke_ok
    return False


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        run_result = run_check(ci=args.ci, poll_timeout=args.poll_timeout, out=out)
    except KeyboardInterrupt:
        print("Relay-auth smoke interrupted by operator", file=out)
        return 130
    print(run_result.message, file=out)
    print_summary(run_result.results, out=out)
    print_checklist(run_result.results, out=out)
    return 0 if run_result.ok else 1


def _result(number: int, title: str, status: Status, message: str) -> StepResult:
    return StepResult(number, title, status, message)


def _print_step(result: StepResult, out: TextIO) -> None:
    print(f"Step {result.number} {result.status.value}: {result.title} - {result.message}", file=out)


def _device_code_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/devicecode"


def _token_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _join_url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _load_json_response(text: str) -> Mapping[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SmokeFailure("Response was not JSON.") from exc
    if not isinstance(value, dict):
        raise SmokeFailure("Response JSON was not an object.")
    return value


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


def _b64url_json(value: Mapping[str, Any]) -> str:
    data = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _valid_claims(tenant_id: str, audience: str, now: int) -> dict[str, Any]:
    return {
        "aud": audience,
        "iss": expected_issuer(tenant_id),
        "tid": tenant_id,
        "sub": "ci-device",
        "exp": now + 3600,
        "nbf": now - 60,
        "scp": "Relay.Access",
    }


def _claims_have_grant(claims: Mapping[str, Any]) -> bool:
    scopes = claims.get("scp", "")
    if isinstance(scopes, str) and "Relay.Access" in scopes.split():
        return True
    roles = claims.get("roles", ())
    if isinstance(roles, str):
        return bool(roles)
    if isinstance(roles, list) and roles:
        return True
    return bool(claims.get("sparky_enrolled"))


def _int_claim(claims: Mapping[str, Any], name: str) -> int | None:
    try:
        return int(claims.get(name))
    except (TypeError, ValueError):
        return None


def _fake_error(status: int, code: str, correlation_id: str) -> HttpResult:
    body = {"error": {"code": code, "message": "Request was rejected."}, "correlation_id": correlation_id}
    return HttpResult(status, {"x-correlation-id": correlation_id}, json.dumps(body))


def _ci_env(env: Mapping[str, str]) -> dict[str, str]:
    values = dict(env)
    values.update(
        {
            "AZURE_TENANT_ID": "tenant-ci",
            "AZURE_CLIENT_ID": "client-ci",
            "SPARKY_RELAY_URL": "https://relay.example.test/api",
            "SPARKY_RELAY_AUDIENCE": "api://relay-ci",
            "SPARKY_RELAY_DEVICE_SCOPE": "api://relay-ci/.default",
        }
    )
    return values


def _tenant_from_url(url: str) -> str | None:
    marker = "login.microsoftonline.com/"
    if marker not in url:
        return None
    rest = url.split(marker, 1)[1]
    return rest.split("/", 1)[0]


def _audience_from_scope(scope: str) -> str:
    if scope.endswith("/.default"):
        return scope[: -len("/.default")]
    slash = scope.rfind("/")
    return scope[:slash] if slash > 0 else scope


def _leak_values(
    config: AzureRelayConfig,
    env: Mapping[str, str],
    token: str,
    credential_names: Iterable[str],
) -> tuple[str, ...]:
    values = {
        config.tenant_id,
        config.client_id,
        config.relay_audience,
        config.device_scope,
        token,
    }
    for name in credential_names:
        value = env.get(name)
        if value:
            values.add(value)
    return tuple(value for value in values if isinstance(value, str) and len(value) >= 8)


if __name__ == "__main__":
    raise SystemExit(main())
