# -*- coding: utf-8 -*-
"""End-to-end smoke test (E2.7): `docker compose up db`, migrations applied, corpus loaded and vectorised.
Skipped when DATABASE_URL is not set. Uses the real components wired by the composition root (e5 in process + pgvector).

The acceptance criterion (top-5 in < 100 ms) is asserted on the SQL phase — the sequential cosine scan — which is what
the "no HNSW" decision is about. The query-embedding phase is reported separately (CPU inference is model-bound, not
database-bound). Statistics over many profiles live in the latency baseline adapter (_dataset/latency_baseline.json)."""
import os
import statistics
import time

import pytest

pytestmark = pytest.mark.infrastructure


def test_top5_similar_cases_sql_phase_under_100ms():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from finalprosports.domain.composition.policy.retrieval_text_policy import query_text
    from finalprosports.domain.model import CaseQuery, ClientProfile, Goal
    from finalprosports.infrastructure.composition_root import CompositionRoot

    root = CompositionRoot.from_env()
    pid = root.configured_professional_id
    profiles = [ClientProfile("SMOKE_1", pid, "M", 32, 178, 5, goal=Goal.VOLUME), ClientProfile("SMOKE_2", pid, "F", 45, 165, 3, goal=Goal.FAT_LOSS),
                ClientProfile("SMOKE_3", pid, "M", 22, 180, 6, goal=Goal.KETO), ClientProfile("SMOKE_4", pid, "F", 29, 168, 4, goal=Goal.INTERMITTENT_FASTING),
                ClientProfile("SMOKE_5", pid, "M", 58, 175, 2, goal=Goal.CARB_CYCLING)]
    q = lambda p: CaseQuery(p, tuple(root.embedder.embed_query(query_text(p))))  # noqa: E731
    root.case_repository.find_similar(pid, q(profiles[0]), 5, frozenset())   # warm-up

    embed_ms, sql_ms = [], []
    for p in profiles:
        t0 = time.perf_counter(); cq = q(p); t1 = time.perf_counter()
        cases = root.case_repository.find_similar(pid, cq, 5, frozenset()); t2 = time.perf_counter()
        embed_ms.append((t1 - t0) * 1000); sql_ms.append((t2 - t1) * 1000)
        assert len(cases) == 5
        assert [c.rank for c in cases] == [1, 2, 3, 4, 5]
        assert all(-1.0 <= c.score.vector <= 1.0 for c in cases)
        assert cases[0].score.total >= cases[-1].score.total                     # ordered by the strategy's score
        assert all(c.diet.client_code != p.client_code for c in cases)

    # El servicio ya NO devuelve los k primeros del repositorio: pide k*OVERFETCH y aplica la seleccion D3 de
    # `neighbourhood_policy` (un caso por cliente, pureza primero). Lo que se comprueba es el contrato NUEVO -- lo
    # entregado sale del conjunto de candidatos, sin repetir cliente y renumerado 1..k -- y no la igualdad con los k
    # primeros, que era justamente el defecto: dos versiones del mismo cliente entraban juntas.
    from finalprosports.domain.composition.policy.neighbourhood_policy import OVERFETCH
    via_service = root.retrieve_similar_cases_service.retrieve(pid, profiles[0], k=5)
    direct = root.case_repository.find_similar(pid, q(profiles[0]), 5, frozenset())
    pool = root.case_repository.find_similar(pid, q(profiles[0]), 5 * OVERFETCH, frozenset())
    assert {c.diet.id for c in via_service} <= {c.diet.id for c in pool}
    assert len({c.diet.client_code for c in via_service}) == len(via_service), "D3 no puede repetir cliente"
    assert [c.rank for c in via_service] == list(range(1, len(via_service) + 1))

    # leave-one-out seam: excluded ids never come back
    excluded = frozenset(c.diet.id for c in direct)
    again = root.case_repository.find_similar(pid, q(profiles[0]), 5, excluded)
    assert not excluded & {c.diet.id for c in again}

    print(f"\nembed p50 {statistics.median(embed_ms):.1f} ms | sql p50 {statistics.median(sql_ms):.1f} ms, max {max(sql_ms):.1f} ms")
    assert statistics.median(sql_ms) < 100, f"SQL phase p50 {statistics.median(sql_ms):.1f} ms"
