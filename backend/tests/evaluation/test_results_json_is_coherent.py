# -*- coding: utf-8 -*-
"""`docs/evaluation/results.json` es la FUENTE de todas las cifras de la evaluación, y la memoria lo cita.

Es el único fichero de `docs/` que se versiona (la excepción está declarada en el `.gitignore` y la vigila
`tests/architecture/test_repository_hygiene.py`). Lo escribe `eval.report --rerun` desde
`$FPS_DATASET_DIR/composer_per_query.jsonl`.

Este test no compara el JSON con ningún documento: comprueba que **es coherente consigo mismo y con lo que se
afirma**. Sin esto, un fichero citado en la memoria puede quedarse desactualizado o incoherente y nadie se enteraría
hasta la defensa.

Antes vivía aquí una suite mayor que además comprobaba que `RESULTS.md` fuese el render exacto del JSON y que las
cifras escritas a mano en `DISCUSSION.md` fueran las medidas. Esos dos documentos ya no se entregan con el código
—están en la memoria—, así que aquellas comprobaciones se retiraron en vez de dejarlas pasando en vacío.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.infrastructure.adapter.inbound.eval.report import GRAN  # noqa: E402
from finalprosports.infrastructure.config.paths import docs_dir  # noqa: E402

RESULTS = docs_dir() / "evaluation" / "results.json"
RES = json.loads(RESULTS.read_text(encoding="utf-8"))


def test_the_source_of_the_figures_is_versioned():
    """No es una comprobación trivial: es la que falla si alguien vuelve a ignorar `docs/` entero."""
    assert RESULTS.exists(), f"falta {RESULTS}: regenerar con `make eval`"
    assert RES["meta"]["queries"] > 0 and RES["meta"]["delivered_variant"]


def test_success_table_is_internally_consistent():
    for tab in RES["success"].values():
        for g in GRAN.values():
            s = tab[g]
            assert abs(s["composer_vs_copy"] - (s["composer"] - s["copy_top1"])) < 2e-4
            assert abs(s["composer_vs_ceiling"] - (s["composer"] - s["ceiling"])) < 2e-4
            assert s["floor_same_goal"] <= s["copy_top1"] <= s["composer"], (g, s)     # el orden de la ablación se sostiene en las tres granularidades
    a = RES["success"]["A_excl_nearest_neighbour"]
    assert a["queries"] < RES["success"]["B_incl_nearest_neighbour"]["queries"] == RES["meta"]["queries"]


def test_statistics_match_the_claims():
    pairs = RES["statistics"]["pairs"]
    for g in GRAN.values():
        # 1. El titular, y la única afirmación de superioridad: componer bate a copiar el caso más parecido.
        assert pairs["composer - copy_top1"][g]["excludes_zero"] and pairs["composer - copy_top1"][g]["mean_diff"] > 0
        # 2. Frente al techo laxo SIN el vecino más cercano la afirmación es IGUALDAD, no superioridad, y eso es una
        #    reformulación, no una relajación: en el corpus reconstruido la diferencia es +0,005 con un intervalo que
        #    contiene el cero. Afirmar la redacción anterior sería afirmar algo que la medición ya no sostiene; no
        #    afirmar nada dejaría pasar una regresión real. Lo que queda clavado es: no POR DEBAJO.
        ceiling = pairs["composer - ceiling_excl_nn (subset)"][g]
        assert ceiling["mean_diff"] >= 0 or not ceiling["excludes_zero"], (g, ceiling)
    assert pairs["composer - ceiling_incl_nn"]["normalized_key"]["mean_diff"] <= 0     # por debajo del techo con vecino: la afirmación es «iguala o supera», nunca «supera»
    # 3. El validador sube el cumplimiento condicional sobre el del compositor.
    assert pairs["validated_strict - composer (conditional compliance)"]["cumplimiento condicional"]["excludes_zero"]
    assert pairs["validated_strict - hidden diet (conditional compliance)"]["cumplimiento condicional"]["excludes_zero"]


def test_ablation_ends_with_the_delivered_configuration():
    """La última fila antes del techo es lo que sirve la API (estrategia → plausibilidad → validador), en los dos escenarios."""
    rows = RES["ablation"]
    assert [row["variant"] for row in rows] == ["floor_same_goal", "copy_top1", "composer_no_degradation", "composer_raw", "validated_strict", "validated_plausible", "ceiling"]
    assert RES["ablation_extra"]["delivered_variant"] == "validated_plausible" == RES["meta"]["delivered_variant"]
    by = {row["variant"]: row for row in rows}
    assert by["validated_plausible"]["plausibility_violations"] < by["validated_strict"]["plausibility_violations"]   # la capa deja menos violaciones que el validador solo
    assert RES["statistics"]["pairs"]["entregada - copy_top1"]["normalized_key"]["excludes_zero"]                    # la configuración entregada sigue batiendo a copiar
    rc = RES["recurrent"]
    assert list(rc["table"])[-1] == "routed_delivered" == rc["meta"]["delivered_variant"]
    assert rc["table"]["routed_delivered"]["plausibility_violations"] <= rc["table"]["routed_validated"]["plausibility_violations"]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
