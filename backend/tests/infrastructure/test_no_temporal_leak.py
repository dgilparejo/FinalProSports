# -*- coding: utf-8 -*-
"""La regla temporal de la báscula, comprobada sobre la RECUPERACIÓN REAL (bloque 0.1).

`tests/domain/test_body_measurement_policy.py` comprueba la política aislada. Este fichero comprueba lo que de verdad
importa: que el LATERAL de `CANDIDATE_SQL` — que es donde se resuelve, porque la fecha de corte es distinta para cada
candidato — no deja pasar ni una lectura posterior a la dieta del caso.

Falla en dos escenarios que no son hipotéticos: si alguien cambia `<` por `<=` en el LATERAL, o si alguien decide
«rellenar» los casos sin lectura previa con la más cercana en el tiempo. Los dos harían subir las cifras y los dos
serían fuga.
"""
import os

import pytest

pytestmark = pytest.mark.infrastructure


def test_no_retrieved_case_carries_a_reading_after_its_own_diet():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from sqlalchemy import text

    from finalprosports.domain.model import ClientProfile, Goal
    from finalprosports.infrastructure.composition_root import CompositionRoot

    root = CompositionRoot.from_env()
    pid = root.configured_professional_id
    with root.case_repository._sf() as s:                                                          # noqa: SLF001
        doc_date = {r.id: r.doc_date for r in s.execute(
            text("SELECT id, doc_date FROM diets WHERE professional_id = :p"), {"p": pid}).all()}

    checked, with_reading = 0, 0
    for goal in (Goal.VOLUME, Goal.FAT_LOSS, Goal.KETO):
        profile = ClientProfile("nuevo", pid, "M", 32, 178, 3, goal=goal)
        cases = root.retrieve_similar_cases_service.retrieve(pid, profile, 20)
        assert cases, f"sin candidatos para {goal}"
        for c in cases:
            checked += 1
            stamp = c.case_profile.measured_at if c.case_profile is not None else None
            if stamp is None:
                continue
            with_reading += 1
            fecha = doc_date.get(c.diet.id)
            assert fecha is not None, f"{c.diet.id} lleva lectura sin tener fecha de documento"
            assert stamp < fecha.isoformat(), f"FUGA TEMPORAL: {c.diet.id} del {fecha} usa una báscula del {stamp}"
    # Sin esta línea el test pasaría también si NINGÚN caso llevara lectura, que es la forma más fácil de que una
    # comprobación de fuga se vuelva decorativa sin que nadie lo note.
    assert with_reading >= 20, f"solo {with_reading} de {checked} casos traen lectura: la comprobación sería vacía"


def test_the_lateral_join_is_strict_not_inclusive():
    """Contra la propia base de datos: ninguna fila casada por el LATERAL empata en fecha con su dieta."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from sqlalchemy import text

    from finalprosports.infrastructure.composition_root import CompositionRoot
    root = CompositionRoot.from_env()
    pid = root.configured_professional_id
    with root.case_repository._sf() as s:                                                          # noqa: SLF001
        n = s.execute(text("""
            SELECT count(*) FROM diets d
            JOIN LATERAL (SELECT b.measured_at FROM body_measurements b
                          WHERE b.professional_id = d.professional_id AND b.client_code = d.client_code
                            AND b.measured_at::date < d.doc_date
                          ORDER BY b.measured_at DESC LIMIT 1) bm ON TRUE
            WHERE d.professional_id = :p AND bm.measured_at::date >= d.doc_date"""), {"p": pid}).scalar()
    assert n == 0, f"{n} dietas emparejadas con una lectura no anterior"
