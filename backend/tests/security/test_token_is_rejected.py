# -*- coding: utf-8 -*-
"""v2 · The security suite: eight cases against a REAL Keycloak.

Separate from the fast suite and marked `security`, so it can be excluded:

    pytest tests/security -q                 # this suite (needs docker compose up keycloak + db)
    pytest -m "not security" -q              # everything else, unchanged and just as fast

Putting a token in front of the API only means something if a bad token is refused, so the point of
these cases is the refusals: seven of the eight expect an error. Tokens are real — obtained through
the full Authorization Code + PKCE flow (`pkce_login.py`), because direct access grants are disabled.

Some tokens cannot be obtained from Keycloak (there is no way to ask it for `alg: none`), so those are
FORGED locally from a real one: the header and payload are rewritten and re-encoded. That is precisely
the attack being tested.
"""
import base64
import json
import os
import time
import uuid

import pytest

pytestmark = [pytest.mark.security]

API = os.environ.get("FPS_API_URL", "http://127.0.0.1:8000")
GUARDED = "/api/v1/clients"      # any guarded route; the check happens before the handler

# A skipped suite exits 0, so an unreachable API would report "the security tests passed" for tests that
# never ran. `make verify-clean-clone` sets this: there, a missing service is a failure, not a skip.
REQUIRE_LIVE = os.environ.get("FPS_REQUIRE_LIVE") == "1"


def _unavailable(reason: str):
    if REQUIRE_LIVE:
        raise AssertionError(f"FPS_REQUIRE_LIVE=1 and {reason}")
    pytest.skip(reason)


# --------------------------------------------------------------------- helpers

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def re_sign_free(token: str, *, header: dict | None = None, payload: dict | None = None, signature: str | None = None) -> str:
    """Rebuild a token with a rewritten header/payload, keeping (or replacing) the signature."""
    h, p, s = token.split(".")
    head = json.loads(_unb64(h)) | (header or {})
    body = json.loads(_unb64(p)) | (payload or {})
    return f"{_b64(json.dumps(head).encode())}.{_b64(json.dumps(body).encode())}.{signature if signature is not None else s}"


@pytest.fixture(scope="module")
def http():
    import httpx
    with httpx.Client(base_url=API, timeout=30.0) as client:
        try:
            probe = client.get("/health")
        except Exception as exc:                             # pragma: no cover
            _unavailable(f"the API is not answering at {API}: {exc}")
        else:
            if probe.status_code != 200:                     # answering, but not with a healthy API
                _unavailable(f"the API at {API} answered /health with {probe.status_code}")
        yield client


@pytest.fixture(scope="module")
def trainer_token():
    from tests.security.pkce_login import TRAINER, access_token
    try:
        return access_token(*TRAINER)
    except Exception as exc:                                 # pragma: no cover
        _unavailable(f"Keycloak is not answering: {exc}")


@pytest.fixture(scope="module")
def no_role_token():
    from tests.security.pkce_login import NO_ROLE, access_token
    try:
        return access_token(*NO_ROLE)
    except Exception as exc:                                 # pragma: no cover
        _unavailable(f"Keycloak is not answering: {exc}")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ----------------------------------------------------------------- the 8 cases

def test_1_valid_token_with_the_role_is_served(http, trainer_token):
    r = http.get(GUARDED, headers=auth(trainer_token))
    assert r.status_code == 200, r.text


def test_2_no_authorization_header_is_401(http):
    r = http.get(GUARDED)
    assert r.status_code == 401, r.text
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_3_valid_token_without_the_role_is_403_and_not_500(http, no_role_token):
    """`sinrol` gets a perfectly valid token that carries NO `realm_access` claim at all — not an
    empty list, the claim is absent. That is where a blind token["realm_access"]["roles"] raises a
    KeyError and answers 500, turning a refusal into a crash."""
    r = http.get(GUARDED, headers=auth(no_role_token))
    assert r.status_code == 403, r.text
    assert r.status_code != 500
    assert r.json()["code"] == "forbidden"


def test_4_expired_token_is_401(http, trainer_token):
    """Forged from the real token: only `exp`/`iat` move, so what is being checked is the expiry and
    not something else. The signature no longer matches either — both roads lead to 401."""
    expired = re_sign_free(trainer_token, payload={"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200})
    r = http.get(GUARDED, headers=auth(expired))
    assert r.status_code == 401, r.text


def test_5_token_from_another_issuer_is_401(http, trainer_token):
    forged = re_sign_free(trainer_token, payload={"iss": "http://localhost:8080/realms/otro"})
    r = http.get(GUARDED, headers=auth(forged))
    assert r.status_code == 401, r.text


def test_6_token_whose_audience_excludes_fps_backend_is_401(http, trainer_token):
    forged = re_sign_free(trainer_token, payload={"aud": "account"})
    r = http.get(GUARDED, headers=auth(forged))
    assert r.status_code == 401, r.text


def test_7_alg_none_is_401(http, trainer_token):
    """The classic JWT attack: strip the signature and declare the token unsigned. Rejected by the
    algorithm allow-list before the signature is even looked at."""
    unsigned = re_sign_free(trainer_token, header={"alg": "none"}, signature="")
    r = http.get(GUARDED, headers=auth(unsigned))
    assert r.status_code == 401, r.text

    # and the same trick with HS256, signing with the public key as if it were a shared secret
    hs256 = re_sign_free(trainer_token, header={"alg": "HS256"})
    r = http.get(GUARDED, headers=auth(hs256))
    assert r.status_code == 401, r.text


def test_8_altered_signature_is_401(http, trainer_token):
    head, payload, signature = trainer_token.split(".")
    flipped = ("B" if signature[0] != "B" else "C") + signature[1:]
    r = http.get(GUARDED, headers=auth(f"{head}.{payload}.{flipped}"))
    assert r.status_code == 401, r.text


# ------------------------------------------------------- what stays reachable

def test_health_is_open(http):
    r = http.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_the_application_is_delivered_empty_of_clients(http, trainer_token):
    """The 467 corpus cases stay in the DATABASE — retrieval needs them — but they are a third party's
    case base, not this professional's portfolio, and the application is delivered empty. So the count
    is EXACT: the `make demo` clients and nothing else. `<=` would pass with a corpus case swapped in
    for a demo one, which is precisely the leak worth catching.

    The expected number is READ FROM THE SEEDER (`DEMO_CLIENTS`), not written here: the roster grew from
    three to sixteen on 2026-09-09 and a literal would have turned that into a red suite instead of a
    fact about the portfolio.

    The filter lives in the repository (S1) and now runs under a professional resolved from the token,
    so this also pins that the tenant filter is doing its job rather than the corpus simply being absent."""
    from finalprosports.infrastructure.adapter.inbound.cli.seed_demo import DEMO_CLIENTS

    rows = http.get(GUARDED, headers=auth(trainer_token)).json()
    names = sorted(c["full_name"] for c in rows)
    assert len(rows) == len(DEMO_CLIENTS), f"{len(rows)} clients visible, expected exactly the {len(DEMO_CLIENTS)} demo ones: {names}"
    assert all("Ficticio" in n or "Ficticia" in n or "Demo" in n for n in names), names

    # and not one of them is a corpus pseudonym leaking through as a client
    assert not any(str(c["id"]).startswith("CLIENTE_") for c in rows), names
    for c in rows:
        uuid.UUID(str(c["id"]))            # a portfolio client is keyed by a UUID (S9), never by a code


def test_an_unmapped_subject_is_403_and_not_500(http, trainer_token):
    """A token signed by the realm for a subject this installation does not know. It cannot be forged
    (the signature would break), so the mapping is checked directly against the resolver."""
    from finalprosports.infrastructure.adapter.outbound.persistence.repository.professional_directory_adapter import (
        ProfessionalDirectoryAdapter,
    )
    from finalprosports.infrastructure.composition_root import CompositionRoot
    directory = CompositionRoot.from_env().professional_directory
    assert isinstance(directory, ProfessionalDirectoryAdapter)
    assert directory.professional_for_subject("00000000-0000-4000-8000-000000000000") is None
