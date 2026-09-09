"""Authorization Code + PKCE (S256) driven end to end against a real Keycloak.

The `fps-frontend` client has direct access grants DISABLED on purpose (OAuth 2.1), so a token
cannot be fetched with a password grant. This helper does what the browser does: it opens the
authorization endpoint, posts the login form, catches the `code` from the redirect and exchanges
it with the verifier. It is the only way the security suite can hold a genuine token.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import secrets
import urllib.parse

import httpx

KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE_URL", "http://localhost:8080")
REALM = os.environ.get("KEYCLOAK_REALM", "fps")
CLIENT_ID = os.environ.get("KEYCLOAK_FRONTEND_CLIENT_ID", "fps-frontend")
REDIRECT_URI = os.environ.get("KEYCLOAK_REDIRECT_URI", "http://localhost:4200/")

TRAINER = ("entrenador", "entrenador")
NO_ROLE = ("sinrol", "sinrol")

_FORM_ACTION = re.compile(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', re.IGNORECASE)


def issuer(base: str = KEYCLOAK_BASE, realm: str = REALM) -> str:
    return f"{base}/realms/{realm}"


def _set_cookies(response: httpx.Response) -> dict[str, str]:
    """name -> value for every Set-Cookie of a response, ignoring flags."""
    out: dict[str, str] = {}
    for key, value in response.headers.multi_items():
        if key.lower() == "set-cookie":
            name, _, rest = value.partition("=")
            out[name.strip()] = rest.split(";")[0]
    return out


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def login(username: str, password: str, *, base: str = KEYCLOAK_BASE, realm: str = REALM,
          client_id: str = CLIENT_ID, redirect_uri: str = REDIRECT_URI, scope: str = "openid") -> dict:
    """Full browser flow. Returns the token endpoint response (access_token, refresh_token, ...)."""
    verifier, challenge = _pkce_pair()
    auth_url = f"{issuer(base, realm)}/protocol/openid-connect/auth"
    params = {"client_id": client_id, "response_type": "code", "scope": scope,
              "redirect_uri": redirect_uri, "state": secrets.token_urlsafe(16),
              "code_challenge": challenge, "code_challenge_method": "S256"}

    with httpx.Client(follow_redirects=False, timeout=30.0) as http:
        page = http.get(auth_url, params=params)
        page.raise_for_status()
        match = _FORM_ACTION.search(page.text)
        if not match:  # Keycloak changed its login template
            raise RuntimeError("login form not found in the authorization response")
        action = html.unescape(match.group(1))  # HTML entities only: the query is already percent-encoded

        # Keycloak marks KC_RESTART and AUTH_SESSION_ID `Secure`. A browser still sends them to
        # http://localhost (a trustworthy origin); http.cookiejar does not, and the login then fails
        # with "Restart login cookie not found". Carry them by hand, as the browser would.
        jar = _set_cookies(page)
        posted = http.post(action, data={"username": username, "password": password},
                           headers={"Content-Type": "application/x-www-form-urlencoded",
                                    "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())})
        location = posted.headers.get("location", "")
        if posted.status_code != 302 or "code=" not in location:
            raise RuntimeError(f"authentication did not produce a code (status {posted.status_code})")
        code = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["code"][0]

        token = http.post(f"{issuer(base, realm)}/protocol/openid-connect/token",
                          data={"grant_type": "authorization_code", "code": code,
                                "client_id": client_id, "redirect_uri": redirect_uri,
                                "code_verifier": verifier})
        token.raise_for_status()
        return token.json()


def access_token(username: str, password: str, **kw) -> str:
    return login(username, password, **kw)["access_token"]


def decode_payload(token: str) -> dict:
    """Decode WITHOUT verifying — for inspection and for building tampered tokens in the tests."""
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def decode_header(token: str) -> dict:
    part = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


if __name__ == "__main__":  # manual inspection: python -m tests.security.pkce_login
    import sys

    user, pwd = (TRAINER if len(sys.argv) < 2 or sys.argv[1] == "entrenador" else NO_ROLE)
    bundle = login(user, pwd)
    print("=== header ===")
    print(json.dumps(decode_header(bundle["access_token"]), indent=2, ensure_ascii=False))
    print("=== payload ===")
    print(json.dumps(decode_payload(bundle["access_token"]), indent=2, ensure_ascii=False))
    print("=== lifetimes ===")
    print("access_token expires_in :", bundle.get("expires_in"), "s")
    print("refresh_token expires_in:", bundle.get("refresh_expires_in"), "s")
