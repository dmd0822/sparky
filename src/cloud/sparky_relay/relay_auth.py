"""Framework-agnostic Microsoft Entra validation for the Sparky relay."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import time
from typing import Any, Mapping, Protocol, Sequence

from .keyless_auth import AzureRelayConfig, expected_issuer


LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())
GRAPH_AUDIENCES = frozenset(
    {
        "https://graph.microsoft.com",
        "00000003-0000-0000-c000-000000000000",
    }
)


class TokenVerificationError(ValueError):
    """Raised by verifier ports when a token signature or envelope is invalid."""


class TokenVerifier(Protocol):
    """Port for JWT signature validation and claim extraction."""

    def verify(self, token: str) -> Mapping[str, Any]:
        """Return verified claims or raise ``TokenVerificationError``."""


@dataclass(frozen=True)
class RelayAuthConfig:
    """Authentication and authorization settings for relay requests."""

    tenant_id: str
    audience: str
    required_roles: tuple[str, ...] = ("Sparky.Relay.Device",)
    required_scopes: tuple[str, ...] = ("Sparky.Relay.Access",)
    enrolled_device_claim: str | None = None
    clock_skew_seconds: int = 120

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("Relay tenant is required.")
        if not self.audience:
            raise ValueError("Relay audience is required.")
        if (
            not self.required_roles
            and not self.required_scopes
            and not self.enrolled_device_claim
        ):
            raise ValueError("Relay authorization requires a role, scope, or device claim.")

    @classmethod
    def from_relay_config(
        cls,
        config: AzureRelayConfig,
        *,
        required_roles: Sequence[str] = ("Sparky.Relay.Device",),
        required_scopes: Sequence[str] = ("Sparky.Relay.Access",),
        enrolled_device_claim: str | None = None,
        clock_skew_seconds: int = 120,
    ) -> "RelayAuthConfig":
        return cls(
            tenant_id=config.tenant_id,
            audience=config.relay_audience,
            required_roles=tuple(required_roles),
            required_scopes=tuple(required_scopes),
            enrolled_device_claim=enrolled_device_claim,
            clock_skew_seconds=clock_skew_seconds,
        )


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context made available to relay handlers."""

    subject: str
    tenant_id: str
    claims: Mapping[str, Any] = field(repr=False)
    token: str = field(repr=False)


@dataclass(frozen=True)
class AuthFailure(Exception):
    """Sanitized authentication or authorization failure."""

    status_code: int
    code: str
    reason: str
    correlation_id: str


def extract_bearer_token(headers: Mapping[str, str]) -> str:
    """Return a bearer token from request headers or raise a sanitized failure."""

    value = _header(headers, "authorization")
    if not value:
        raise AuthFailure(401, "missing_token", "Authentication is required.", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip() or " " in token.strip():
        raise AuthFailure(401, "malformed_token", "The bearer token is malformed.", "")
    token = token.strip()
    if len(token.split(".")) != 3:
        raise AuthFailure(401, "malformed_token", "The bearer token is malformed.", "")
    return token


def authenticate_request(
    headers: Mapping[str, str],
    config: RelayAuthConfig,
    verifier: TokenVerifier,
    *,
    now: int | None = None,
    correlation_id: str,
) -> AuthContext:
    """Validate bearer token signature, tenant, audience, lifetime, and grants."""

    try:
        token = extract_bearer_token(headers)
        claims = verifier.verify(token)
        if not isinstance(claims, Mapping):
            raise TokenVerificationError("verifier returned non-object claims")
        _validate_claims(claims, config, now=int(time.time()) if now is None else now)
        return AuthContext(
            subject=str(claims.get("sub") or claims.get("oid") or "unknown"),
            tenant_id=str(claims.get("tid")),
            claims=claims,
            token=token,
        )
    except AuthFailure as failure:
        failure = _with_correlation(failure, correlation_id)
        LOGGER.warning("Relay authentication failed: %s", failure.code)
        raise failure
    except TokenVerificationError:
        failure = AuthFailure(
            401,
            "invalid_token",
            "The bearer token could not be validated.",
            correlation_id,
        )
        LOGGER.warning("Relay authentication failed: %s", failure.code)
        raise failure


def _validate_claims(claims: Mapping[str, Any], config: RelayAuthConfig, *, now: int) -> None:
    issuer = claims.get("iss")
    if issuer != expected_issuer(config.tenant_id):
        raise AuthFailure(401, "invalid_issuer", "The bearer token issuer is not trusted.", "")

    tenant = claims.get("tid")
    if tenant != config.tenant_id:
        raise AuthFailure(401, "invalid_tenant", "The bearer token tenant is not trusted.", "")

    audience = claims.get("aud")
    audiences = set(audience if isinstance(audience, list) else [audience])
    if audiences & GRAPH_AUDIENCES or config.audience not in audiences:
        raise AuthFailure(401, "invalid_audience", "The bearer token audience is not accepted.", "")

    exp = _int_claim(claims, "exp")
    if exp is None or exp + config.clock_skew_seconds < now:
        raise AuthFailure(401, "token_expired", "The bearer token is expired.", "")

    nbf = _int_claim(claims, "nbf")
    if nbf is not None and nbf - config.clock_skew_seconds > now:
        raise AuthFailure(401, "token_not_yet_valid", "The bearer token is not yet valid.", "")

    if not _has_required_grant(claims, config):
        raise AuthFailure(403, "missing_grant", "The caller is not authorized for this relay.", "")


def _has_required_grant(claims: Mapping[str, Any], config: RelayAuthConfig) -> bool:
    roles = claims.get("roles", ())
    if isinstance(roles, str):
        role_values = {roles}
    else:
        role_values = {str(role) for role in roles if isinstance(role, str)}
    if role_values.intersection(config.required_roles):
        return True

    scope_claim = claims.get("scp", "")
    if isinstance(scope_claim, str):
        scope_values = set(scope_claim.split())
    else:
        scope_values = {str(scope) for scope in scope_claim if isinstance(scope, str)}
    if scope_values.intersection(config.required_scopes):
        return True

    if config.enrolled_device_claim:
        return bool(claims.get(config.enrolled_device_claim))
    return False


def _int_claim(claims: Mapping[str, Any], name: str) -> int | None:
    value = claims.get(name)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _with_correlation(failure: AuthFailure, correlation_id: str) -> AuthFailure:
    if failure.correlation_id == correlation_id:
        return failure
    return AuthFailure(failure.status_code, failure.code, failure.reason, correlation_id)


class PyJwtEntraTokenVerifier:
    """Production verifier backed by Entra OpenID signing keys."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id

    def verify(self, token: str) -> Mapping[str, Any]:
        try:
            import jwt
            from jwt import PyJWKClient
        except ImportError as exc:  # pragma: no cover - exercised only without prod deps.
            raise TokenVerificationError(
                "PyJWT is required for production token verification."
            ) from exc

        jwks_url = (
            "https://login.microsoftonline.com/"
            f"{self.tenant_id}/discovery/v2.0/keys"
        )
        try:
            key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": False,
                    "verify_nbf": False,
                },
            )
        except Exception as exc:  # pragma: no cover - exact library errors vary.
            raise TokenVerificationError("JWT signature validation failed.") from exc
        if not isinstance(claims, dict):
            raise TokenVerificationError("JWT payload must be an object.")
        return claims


def jwt_payload_without_verification(token: str) -> Mapping[str, Any]:
    """Decode a JWT payload for tests and diagnostics without trusting it."""

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Expected three JWT segments.")
    import base64

    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    if not isinstance(payload, dict):
        raise ValueError("JWT payload must be an object.")
    return payload
