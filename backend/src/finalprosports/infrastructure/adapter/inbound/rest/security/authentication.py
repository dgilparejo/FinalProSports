"""The authentication dependency: the single door into the application.

It is mounted on the `/api/v1` router itself, so every route under it carries the check by
construction rather than by remembering to decorate each one; `tests/architecture/test_every_route_is_guarded.py`
fails if a route ever escapes it.

MUST STAY `async`. FastAPI runs a SYNC dependency in a worker thread, which gets a COPY of the
context: the `bind_professional` call would land in that copy and be discarded, and the endpoint
would then find nothing bound. An async dependency runs in the request's own task, so the binding
is the one the endpoint (and the threadpool it may be dispatched to) sees.
"""
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from finalprosports.infrastructure.config.security import (
    AuthenticationError, AuthorizationError, TokenVerifier, bind_professional, role_of,
)

# auto_error=False: HTTPBearer's own 403-for-a-missing-header is the wrong code. A missing or
# malformed Authorization header is 401 (who are you?), never 403 (I know you, you may not).
_bearer = HTTPBearer(auto_error=False, description="Access token del realm fps (Authorization Code + PKCE)")


def build_authentication_dependency(verifier: TokenVerifier, directory, required_role: str):
    """Returns the dependency that validates the token, checks the role and binds the professional."""

    async def authenticate(request: Request,
                           credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
        if credentials is None or not credentials.credentials:
            raise AuthenticationError("missing Authorization: Bearer header")
        if credentials.scheme.lower() != "bearer":
            raise AuthenticationError(f"unsupported authorization scheme: {credentials.scheme}")

        claims = verifier.verify(credentials.credentials)          # signature, alg, iss, aud, exp, nbf

        if not role_of(claims, required_role):
            raise AuthorizationError(f"the token carries no '{required_role}' realm role")

        subject = claims.get("sub", "")
        professional_id = directory.professional_for_subject(subject)
        if professional_id is None:
            # A valid token from a user this installation knows nothing about. Authenticated, not
            # authorised, and above all NOT a 500: the answer says the account is not provisioned.
            raise AuthorizationError("the authenticated subject is not mapped to any professional in this installation")

        bind_professional(professional_id)
        request.state.professional_id = professional_id            # for logging and for the tests
        return professional_id

    return authenticate
