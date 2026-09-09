# -*- coding: utf-8 -*-
"""v2 · Each claim check, exercised with a VALID signature.

Why this file exists, and it is the interesting part of the whole suite.

Rewriting `iss`, `aud` or `exp` inside a real Keycloak token breaks its signature, so the API refuses
it — with "Signature verification failed". The refusal is correct and the test is green, and it proves
NOTHING about the issuer, audience or expiry checks: they were never reached. Had `verify_aud` been
left off (the default in more than one library) those tests would still be green.

So here the tokens are signed with a key this test owns and the verifier is pointed at it. Every token
below carries a signature that verifies. The only thing wrong with each one is the claim under test,
which means the rejection can only come from the check being examined.

Needs no Keycloak: `python tests/security/test_claim_checks_are_not_decorative.py`
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import jwt                                                     # noqa: E402
from cryptography.hazmat.primitives import serialization        # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa      # noqa: E402

from finalprosports.infrastructure.config.security import (    # noqa: E402
    AuthenticationError, KeycloakConfig, TokenVerifier,
)

ISSUER = "http://localhost:8080/realms/fps"
AUDIENCE = "fps-backend"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {name}{'' if condition else ': ' + detail}")
    if not condition:
        failures.append(name)


class _StubJWKClient:
    """Stands in for PyJWKClient: hands the verifier the public key of the pair signing here."""

    def __init__(self, public_key):
        self._key = public_key

    def get_signing_key_from_jwt(self, _token):
        return type("Key", (), {"key": self._key})()


def build() -> tuple[TokenVerifier, object]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = KeycloakConfig(issuer=ISSUER, audience=AUDIENCE, required_role="entrenador",
                            jwks_url="http://unused", leeway_seconds=10.0)
    return TokenVerifier(config, jwk_client=_StubJWKClient(private.public_key())), private


def token(private, alg: str = "RS256", **claims) -> str:
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": "11111111-1111-4111-8111-111111111111",
               "iat": now, "exp": now + 300, "realm_access": {"roles": ["entrenador"]}} | claims
    return jwt.encode(payload, private, algorithm=alg)


def _hs256_by_hand(secret: bytes, now: int) -> str:
    """A token whose header says HS256, MAC-ed with the RSA public key as the shared secret."""
    import base64
    import hashlib
    import hmac
    import json as _json

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    head = b64(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(_json.dumps({"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "iat": now, "exp": now + 300}).encode())
    signing_input = f"{head}.{body}".encode()
    return f"{head}.{body}.{b64(hmac.new(secret, signing_input, hashlib.sha256).digest())}"


def rejects(verifier, tok: str) -> bool:
    try:
        verifier.verify(tok)
        return False
    except AuthenticationError:
        return True


def run() -> None:
    verifier, private = build()

    # A correctly signed, correctly addressed token is accepted — otherwise the refusals below mean nothing
    claims = verifier.verify(token(private))
    check("a_well_formed_token_is_accepted", claims["sub"] == "11111111-1111-4111-8111-111111111111")

    # -------------------------------------------------------------- audience
    check("audience_that_is_another_client_is_rejected", rejects(verifier, token(private, aud="account")))
    check("audience_missing_altogether_is_rejected", rejects(verifier, token(private, aud=None)))
    check("audience_as_a_LIST_containing_fps_backend_is_accepted",
          verifier.verify(token(private, aud=["account", AUDIENCE]))["sub"] != "",
          "membership, not equality: Keycloak emits `aud` as a string or as a list depending on the mappers")
    check("audience_as_a_list_WITHOUT_fps_backend_is_rejected", rejects(verifier, token(private, aud=["account", "otro"])))

    # ---------------------------------------------------------------- issuer
    check("another_realm_is_rejected", rejects(verifier, token(private, iss="http://localhost:8080/realms/otro")))
    check("another_host_is_rejected", rejects(verifier, token(private, iss="http://evil.example/realms/fps")))
    check("issuer_must_match_verbatim", rejects(verifier, token(private, iss=ISSUER + "/")))

    # ------------------------------------------------------------ exp / nbf
    now = int(time.time())
    check("an_expired_token_is_rejected", rejects(verifier, token(private, exp=now - 3600, iat=now - 7200)))
    check("a_token_not_yet_valid_is_rejected", rejects(verifier, token(private, nbf=now + 600)))
    check("the_clock_leeway_is_small",
          rejects(verifier, token(private, exp=now - 60, iat=now - 600)) and not rejects(verifier, token(private, exp=now - 5, iat=now - 600)),
          "10 s of skew tolerated, a minute is not")

    # ----------------------------------------------------------- required
    check("a_token_without_sub_is_rejected", rejects(verifier, token(private, sub=None)))

    # ------------------------------------------------------------ algorithm
    unsigned = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "iat": now, "exp": now + 300},
                          key="", algorithm="none")
    check("alg_none_is_rejected_even_with_perfect_claims", rejects(verifier, unsigned),
          "the classic JWT attack: declare the token unsigned and hope the library believes it")

    # PyJWT refuses to SIGN HS256 with an asymmetric key ("should not be used as an HMAC secret"),
    # which is a good defence but also means the attack token has to be built by hand to test that
    # the VERIFYING side refuses it too. This is that token, assembled byte by byte.
    public_pem = private.public_key().public_bytes(encoding=serialization.Encoding.PEM,
                                                   format=serialization.PublicFormat.SubjectPublicKeyInfo)
    check("hs256_signed_with_the_public_key_is_rejected", rejects(verifier, _hs256_by_hand(public_pem, now)),
          "the confusion attack: the API's own public key used as if it were a shared secret")

    # ------------------------------------------------------- another key
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    check("a_token_signed_by_another_key_is_rejected", rejects(verifier, token(stranger)))


if __name__ == "__main__":
    run()
    print(f"\n{'ALL PASS' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)
