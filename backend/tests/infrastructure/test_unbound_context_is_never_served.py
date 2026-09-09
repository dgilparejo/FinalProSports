# -*- coding: utf-8 -*-
"""v2 · A request that reaches a handler WITHOUT a professional bound must not be answered.

The static guards (tests/architecture/test_authentication_fails_closed.py) prove the adapter raises and
that nothing catches the exception on the way out. This one asks the question end to end, over HTTP,
which is the form the answer actually matters in: if some future code path skips the binding, does the
caller get a 500 — or a 200 with somebody's data?

The failure is simulated the only honest way: the authentication dependency is replaced by one that
authenticates but FORGETS to bind, which is exactly what a new endpoint hung outside the router, or a
background task reusing the services, would look like.
"""
import os

import pytest

pytestmark = pytest.mark.infrastructure


@pytest.fixture()
def app_without_binding():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from fastapi.testclient import TestClient

    from finalprosports.main import app

    async def _authenticated_but_unbound() -> str:
        return "prof_001"          # passes authentication and never calls bind_professional

    app.dependency_overrides[app.state.authenticate] = _authenticated_but_unbound
    try:
        # raise_server_exceptions=False: let the response through instead of re-raising, so the STATUS
        # can be asserted — the whole point is what the caller receives.
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_a_route_that_skips_the_binding_is_not_answered(app_without_binding):
    response = app_without_binding.get("/api/v1/clients")

    assert response.status_code >= 500, (
        f"a request with no professional bound was answered with {response.status_code}: "
        "the context variable is failing OPEN, which is an authentication bypass"
    )
    assert response.status_code != 200


def test_no_client_data_leaks_in_that_response(app_without_binding):
    body = app_without_binding.get("/api/v1/clients").text
    assert "full_name" not in body and "client_code" not in body, body[:200]


def test_the_same_route_works_once_the_professional_is_bound(app_without_binding):
    """The control: the 500 above is the missing binding, not a broken route."""
    from finalprosports.infrastructure.config.security import bind_professional
    from finalprosports.main import app
    from tests.support.authenticated_client import configured_professional_id

    pid = configured_professional_id()

    async def _authenticated_and_bound() -> str:
        bind_professional(pid)
        return pid

    app.dependency_overrides[app.state.authenticate] = _authenticated_and_bound
    assert app_without_binding.get("/api/v1/clients").status_code == 200
