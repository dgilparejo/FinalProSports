# -*- coding: utf-8 -*-
"""S1/S9 · No endpoint of the application exposes a case of the corpus as a client, and a client of the portfolio is a NAME with a UUID key.

Runs against the loaded database (skipped without DATABASE_URL) through the real FastAPI application. The corpus codes are taken from
the case base itself (the diets table), so the test does not depend on the pseudonym pattern. It walks EVERY route whose path carries a
client id and asserts that a corpus code is never found (404 / 409 / 422), and that the listing contains none of them. Case ids
(``CLIENTE_NNN::vNN``) may still appear as EVIDENCE of a proposal: that is the case base doing retrieval, not a client."""
import json
import os
import uuid

import pytest

pytestmark = pytest.mark.infrastructure


@pytest.fixture(scope="module")
def ctx():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from finalprosports.main import app  # noqa: F401
    from finalprosports.infrastructure.composition_root import CompositionRoot
    from finalprosports.infrastructure.config.paths import dataset_dir
    from tests.support.authenticated_client import authenticated_client, configured_professional_id
    root = CompositionRoot.from_env()
    pid = configured_professional_id()          # v2: outside a request there is no token, so the tenant comes from configuration
    corpus_codes = sorted({p.client_code for p in root.client_repository.list_case_profiles(pid)} | {i.split("::")[0] for i in root.case_repository.all_ids(pid)})
    # Against the ACTIVE dataset, not a literal: 400 was dataset-v2's profile count (467, 330 with diets) and the
    # rebuilt corpus has 301. The property under test is "the case base is loaded and every one of its codes stays
    # hidden", which a literal turns into "you are using dataset-v2" the moment another one is active.
    expected = len({json.loads(line)["client_code"]
                    for line in (dataset_dir() / "profiles.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()})
    assert len(corpus_codes) >= expected, f"the case base is not loaded ({len(corpus_codes)} of {expected})"
    return authenticated_client(pid), root, pid, corpus_codes


def test_listing_contains_no_corpus_case_and_identifies_clients_by_name_and_uuid(ctx):
    client, root, pid, corpus = ctx
    r = client.get("/api/v1/clients")
    assert r.status_code == 200
    rows = r.json()
    listed = {c["id"] for c in rows}
    assert not (listed & set(corpus)), sorted(listed & set(corpus))[:5]
    for c in rows:
        uuid.UUID(c["id"])                                                             # S9: the key is a UUID, never a code
        assert "client_code" not in c and "full_name" in c
    assert len(root.client_repository.list_case_profiles(pid)) >= len(corpus)          # the case base is still there, for retrieval


def test_every_client_route_hides_corpus_codes(ctx):
    client, root, pid, corpus = ctx
    from finalprosports.main import app
    sample = corpus[:3] + corpus[-2:]
    paths = {path: ops for path, ops in app.openapi()["paths"].items() if "{client_id}" in path}        # every documented client route
    assert len(paths) >= 2, sorted(paths)
    assert not any("{client_code}" in path for path in app.openapi()["paths"]), "a route still exposes the storage key name"
    for path, ops in paths.items():
        for method in ops:
            for code in sample:
                url = path.replace("{client_id}", code)
                r = client.request(method.upper(), url, json={} if method in ("post", "put", "patch") else None)
                assert r.status_code in (404, 409, 422), (method, url, r.status_code)
                if r.status_code == 404:
                    assert r.json().get("code") == "client_not_found"


def test_propose_refuses_corpus_codes_and_registration_cannot_target_one(ctx):
    client, root, pid, corpus = ctx
    code = corpus[0]
    r = client.post("/api/v1/diets/propose", json={"client_id": code, "goal": "volumen_masa"})
    assert r.status_code == 422, r.text                                                # not even a valid key shape
    r = client.post("/api/v1/clients", json={"client_code": code, "full_name": "Prueba Ficticia Demo", "sex": "M"})
    assert r.status_code == 201, r.text                                                # the code is ignored: the key is assigned by the application
    created = r.json()
    assert created["id"] != code and uuid.UUID(created["id"]) and created["full_name"] == "Prueba Ficticia Demo"
    assert root.client_repository.get(pid, code) is None                              # and the corpus profile is untouched / unreachable
    root.client_repository.delete(pid, created["id"])


def test_register_by_name_then_read_by_uuid(ctx):
    client, root, pid, corpus = ctx
    r = client.post("/api/v1/clients", json={"full_name": "Vera Ficticia Demo", "birth_date": "1990-06-15", "phone": "+34 000 000 009",
                                             "sex": "F", "height_cm": 170, "activity_level": 4, "goal": "definicion_grasa", "restrictions": ["contains_gluten"]})
    assert r.status_code == 201, r.text
    c = r.json()
    try:
        key = c["id"]
        uuid.UUID(key)
        assert c["age"] is not None and c["age"] >= 35 and c["restrictions"] == ["contains_gluten"] and c["has_intolerances"] is True
        r = client.get(f"/api/v1/clients/{key}")
        assert r.status_code == 200 and r.json()["full_name"] == "Vera Ficticia Demo" and r.json()["birth_date"] == "1990-06-15"
        r = client.get(f"/api/v1/clients/{key}/record")
        assert r.status_code == 200 and r.json()["record"]["identification"]["full_name"] == "Vera Ficticia Demo" and r.json()["client"]["id"] == key
        assert any(row["id"] == key for row in client.get("/api/v1/clients").json())
        r = client.post("/api/v1/clients", json={"sex": "F"})
        assert r.status_code == 422                                                    # no name, no client
    finally:
        root.client_repository.delete(pid, key)


def test_saved_diets_of_corpus_codes_are_unreachable(ctx):
    client, root, pid, corpus = ctx
    r = client.get(f"/api/v1/diets/{corpus[0]}::e01")
    assert r.status_code == 404
