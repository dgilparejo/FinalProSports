"""v2 — access token validation against Keycloak's JWKS, and the request-scoped identity.

Two things live here, and the second one is the delicate one.

1. `TokenVerifier`: validates the token LOCALLY against the realm's public keys. No introspection
   call per request. `PyJWKClient` caches the key set with a TTL and, when a `kid` is not in the
   cached set, refetches once — which is exactly what happens when Keycloak rotates its key.

2. `_CURRENT_PROFESSIONAL`: the professional resolved from THIS request's token. A context variable
   is implicit context, and implicit context fails silently, so it fails CLOSED here:

   - reading it unset RAISES `ProfessionalContextNotBound`. There is no default, no fallback to a
     fixed professional, no "first professional in the table". A code path that reaches the output
     adapter without having passed the authentication dependency is a bug, and a bug must be loud:
     serving a default would be an authentication bypass, not a degraded mode.
   - `bind_professional` is the ONLY writer, and the only caller allowed is the FastAPI dependency
     in `adapter/inbound/rest/security/authentication.py`. `tests/architecture/test_single_context_writer.py`
     fails if anything else in `src/` calls it.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

RS256 = "RS256"   # the ONLY accepted algorithm: asymmetric, so a token cannot be forged with a value the API also holds


class AuthenticationError(Exception):
    """No usable token: absent, malformed, expired, wrong signature, wrong issuer, wrong audience. -> 401."""


class AuthorizationError(Exception):
    """The token is valid, but it does not authorise this operation (missing role, subject not mapped). -> 403."""


class ProfessionalContextNotBound(RuntimeError):
    """The professional was read outside a request that authenticated. A bug, never a request outcome."""


@dataclass(frozen=True)
class KeycloakConfig:
    issuer: str                       # value that must appear VERBATIM in `iss`
    audience: str                     # value that must be IN `aud`
    required_role: str                # realm role without which the answer is 403
    jwks_url: str                     # taken from the internal issuer when the API talks to Keycloak container-to-container
    jwks_cache_seconds: float = 300.0
    leeway_seconds: float = 10.0      # small clock skew for exp/nbf/iat

    @staticmethod
    def from_settings(settings: Any) -> "KeycloakConfig":
        internal = (getattr(settings, "keycloak_internal_issuer", "") or settings.keycloak_issuer).rstrip("/")
        return KeycloakConfig(issuer=settings.keycloak_issuer.rstrip("/"),
                              audience=settings.keycloak_audience,
                              required_role=settings.keycloak_required_role,
                              jwks_url=f"{internal}/protocol/openid-connect/certs",
                              jwks_cache_seconds=settings.keycloak_jwks_cache_seconds,
                              leeway_seconds=settings.keycloak_leeway_seconds)


class TokenVerifier:
    """Signature, algorithm, issuer, audience, expiry and not-before. Everything else is the caller's business."""

    def __init__(self, config: KeycloakConfig, jwk_client: PyJWKClient | None = None):
        self._config = config
        self._jwks = jwk_client or PyJWKClient(config.jwks_url, cache_keys=True, lifespan=config.jwks_cache_seconds, timeout=10)

    def verify(self, token: str) -> dict:
        """Return the claims of a token that passed every check; raise AuthenticationError otherwise."""
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            return jwt.decode(
                token, key,
                algorithms=[RS256],                     # `none` and HS256 are rejected here, before the signature is looked at
                issuer=self._config.issuer,
                audience=self._config.audience,         # membership: PyJWT accepts `aud` as a string or as a list
                leeway=self._config.leeway_seconds,
                options={"verify_signature": True, "verify_exp": True, "verify_nbf": True,
                         "verify_iat": True, "verify_iss": True,
                         "verify_aud": True,            # EXPLICIT: several libraries leave this off by default and then the check is decorative
                         "require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(str(exc)) from exc
        except Exception as exc:                        # JWKS unreachable, malformed key set, ...
            raise AuthenticationError(f"the token could not be validated: {exc}") from exc


def role_of(claims: dict, role: str) -> bool:
    """`realm_access` may be ABSENT (a user with no realm role gets no such claim at all), so this
    never indexes blindly: a missing claim is 'no role', which is a 403, not a KeyError and a 500."""
    realm_access = claims.get("realm_access")
    roles = realm_access.get("roles", ()) if isinstance(realm_access, dict) else ()
    return role in roles


_CURRENT_PROFESSIONAL: ContextVar[str] = ContextVar("current_professional_id")


def bind_professional(professional_id: str) -> Token:
    """THE ONLY WRITER. Called by the authentication dependency and by nothing else."""
    if not professional_id:
        raise ValueError("the professional id cannot be empty")
    return _CURRENT_PROFESSIONAL.set(professional_id)


def current_professional_id_or_raise() -> str:
    """Fail closed: no token bound to this context means no professional, not a default one."""
    try:
        return _CURRENT_PROFESSIONAL.get()
    except LookupError as exc:
        raise ProfessionalContextNotBound(
            "no professional is bound to this context: the request did not pass the authentication "
            "dependency (or this is running outside a request)") from exc
