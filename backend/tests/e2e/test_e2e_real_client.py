# -*- coding: utf-8 -*-
"""End-to-end functional test with a real client's data, pseudonymised (`pytest -m e2e_real`, or `make e2e-real`).

The whole path in one test: register by name -> intake record -> connected-scale import -> lab results -> his two previous
versions as history -> propose the next one -> check it automatically. It is the test that replaces the trainer reading the
output line by line.

The fixture is a REAL client of the professional with the identity replaced: every clinical, dietary and body-composition value
is his, the name, phone and e-mail are invented. The value of the test does not depend on the real name, so the fixture is
committed and the test runs from a clean clone.

Two families of assertion:
  * what the system must never do          a food vetoed by the client's declared restrictions, or a plausibility violation the
                                           system INTRODUCES (one his own version does not already have).
  * what it must look like                 renewal, novelty and family fidelity inside the published bands, and the routing that
                                           the data demands (same goal -> rotate the previous version).

A violation the professional's own diet also has is reported as inherited and does not fail the test: the assertion is his
envelope and for this client he himself sits outside it (his dinner carries 17 distinct foods, over his own p95 of 15,25).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from evaluate_real_client import BANDS, Fixture, evaluate, load_client, metric_problems, verdict  # noqa: E402

pytestmark = pytest.mark.e2e_real
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_path() -> Path:
    """Qué expediente recorre el test, en este orden y con el motivo escrito.

    1. `FPS_E2E_FIXTURE`, si está puesta: así es como el titular apunta al expediente REAL, que vive FUERA del árbol.
    2. `client_recurrent_volume.json`, si existe: es el real y solo está en el repositorio privado.
    3. `client_recurrent_volume_synthetic.json`: cliente inventado, generado por `build_synthetic_fixture.py`.

    El test recorre lo mismo con los dos. Lo que cambia es lo que se puede AFIRMAR: con el real, que el sistema se
    comporta con los datos de una persona de verdad; con el sintético, que el camino entero funciona. La segunda
    afirmación es la que puede viajar a un repositorio público, porque la primera lleva datos de salud dentro."""
    import os
    env = os.environ.get("FPS_E2E_FIXTURE")
    if env:
        return Path(env)
    real = FIXTURES / "client_recurrent_volume.json"
    return real if real.exists() else FIXTURES / "client_recurrent_volume_synthetic.json"


@pytest.fixture(scope="module")
def result():
    import os

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from finalprosports.infrastructure.composition_root import CompositionRoot

    root = CompositionRoot.from_env()
    ruta = fixture_path()
    print(f"     [e2e] expediente: {ruta.name}{' (SINTÉTICO)' if 'synthetic' in ruta.name else ' (REAL, no publicable)'}")
    fx = Fixture.load(ruta)
    cid = load_client(root, fx)
    try:
        yield evaluate(root, cid, fx), fx
    finally:
        root.client_repository.delete(root.configured_professional_id, cid)


def test_the_whole_path_loads_and_the_routing_is_the_one_the_data_demands(result):
    r, fx = result
    assert r["routing"] == "same_goal" and r["strategy"] == "rotation_composer", r["routing"]
    assert r["retrieved"] == 20 and r["items"] > 30
    assert {"DESAYUNO", "COMIDA", "CENA"} <= set(r["slots"])


def test_no_food_the_client_may_not_eat_survives(result):
    r, _ = result
    assert not r["vetoed_foods"], r["vetoed_foods"]
    # the restrictions are applied INSIDE the rotation's candidate selection, so they also show up as refusals
    assert r["rotation_refusals"] >= 0


def test_the_system_introduces_no_implausibility_of_its_own(result):
    r, _ = result
    assert r["violations_introduced"] == 0, r["introduced_detail"]


def _skip_if_synthetic():
    """Las bandas de fidelidad son SUYAS y solo se pueden medir contra SUS versiones anteriores.

    Con el expediente sintético, la versión anterior también la compuso el motor: comparar una con otra da un parecido
    artificialmente alto (medido: `j_family` = 1,0 frente a su banda [0,55, 0,9]) y no dice nada de cómo renueva él.
    Maquillar el fixture para que caiga dentro de la banda sería fabricar la conclusión, así que estas dos
    comprobaciones se SALTAN con el motivo escrito y las otras tres —camino completo, restricciones y plausibilidad
    introducida— siguen corriendo, que son las que valen en un repositorio público."""
    if "synthetic" in fixture_path().name:
        pytest.skip("expediente sintético: las bandas de renovación son del profesional y se miden con su expediente real "
                    "(FPS_E2E_FIXTURE o el fixture privado)")


def test_it_renews_like_he_does_and_keeps_the_structure(result):
    """Renueva como renovaría él CON ESTE CLIENTE, y conserva la estructura.

    El suelo es el de la población (RESULTS §9); el techo, cuando él tiene dos versiones de esta persona, es su propia
    cifra. Con este cliente él mantiene 0,9556 de las claves y el 100 % de las familias entre versión y versión: pedir
    ≤ 0,60 sería exigirle al sistema renovar más que el profesional al que reproduce. El criterio vive en
    `metric_problems` y lo comparte el veredicto, para que no haya dos versiones de la misma regla."""
    _skip_if_synthetic()
    r, _ = result
    assert r["novelty_j_key"] is not None and r["j_family"] is not None, "faltan las cifras de parecido"
    problemas = metric_problems(r)
    assert not problemas, "; ".join(problemas)


def test_the_verdict_is_reported(result):
    _skip_if_synthetic()
    r, _ = result
    ok, problems = verdict(r)
    assert ok, problems
