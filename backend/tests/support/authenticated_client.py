"""Fast level: a TestClient whose authentication dependency is overridden.

The 177 existing tests exercise the ENGINE through the API. Making each of them do a real
Authorization Code round trip against Keycloak would make the suite slow and tie it to a running
container for no gain: none of them is about authentication. So they override the one dependency
and keep running exactly as before.

What is NOT faked: the override still BINDS the professional context, so everything downstream —
the output adapter, the `professional_id` filter of every query — runs the real code path. The only
thing skipped is the token check itself, which the security suite (tests/security/) covers against
a real Keycloak.
"""
from finalprosports.infrastructure.config.security import bind_professional


def authenticated_client(professional_id: str | None = None):
    """TestClient for the real app, authenticated as the configured professional."""
    from fastapi.testclient import TestClient

    from finalprosports.infrastructure.config.settings import Settings
    from finalprosports.main import app

    pid = professional_id or Settings().professional_id

    async def _authenticated() -> str:
        bind_professional(pid)          # the context IS bound: only the token check is skipped
        return pid

    app.dependency_overrides[app.state.authenticate] = _authenticated
    return TestClient(app)


def configured_professional_id() -> str:
    from finalprosports.infrastructure.config.settings import Settings
    return Settings().professional_id
