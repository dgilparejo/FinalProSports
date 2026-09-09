# -*- coding: utf-8 -*-
"""Domain tests of the retrieval policies (E3): text representation and attribute similarity. Pure Python."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.attribute_similarity_policy import (  # noqa: E402
    DEFAULT_WEIGHTS, AttributeWeights, attribute_score, hybrid_score, restriction_compatibility,
)
from finalprosports.domain.composition.policy.retrieval_text_policy import GOAL_LABELS, document_text, query_text  # noqa: E402
from finalprosports.domain.model import ClientProfile, Goal  # noqa: E402

M30 = ClientProfile("q", "p", "M", 30, 180, 5, goal=Goal.VOLUME)


def test_query_and_document_share_the_same_header():
    q = query_text(M30)
    d = document_text(Goal.VOLUME, None, "M", 30, 5, False, {"DESAYUNO": ["avena", "plátano"], "CENA": ["pollo", "brócoli"]}, ["sin hidratos en la cena"])
    assert d.startswith(q), (q, d)
    assert q.splitlines()[0] == f"OBJETIVO: {GOAL_LABELS[Goal.VOLUME]} | META: volumen_masa"
    assert "PERFIL: sexo M | edad 25-39 | actividad 5 | intolerancias no" in q


def test_document_uses_goal_text_slots_in_day_order_dedup_and_notes():
    d = document_text(Goal.KETO, "DIETA CETOGENICA", "F", 44, None, True,
                      {"CENA": ["salmón", "salmón", "espinacas"], "DESAYUNO": ["huevo", "", "aguacate"]}, ["nota A", " ", "nota B"])
    lines = d.splitlines()
    assert lines[0] == "OBJETIVO: DIETA CETOGENICA | META: cetosis_keto"
    assert lines[1] == "PERFIL: sexo F | edad 40-54 | actividad ? | intolerancias sí"
    assert lines[2] == "DESAYUNO: huevo, aguacate" and lines[3] == "CENA: salmón, espinacas"      # day order, empty and duplicate removed
    assert lines[4] == "NOTAS: nota A · nota B"


def test_document_without_notes_has_no_notes_line_and_unknowns_are_explicit():
    d = document_text(None, "", None, None, None, False, {}, [])
    assert d == f"OBJETIVO: {GOAL_LABELS[Goal.UNCLASSIFIED]} | META: sin_clasificar\nPERFIL: sexo ? | edad edad_NA | actividad ? | intolerancias no"


def test_attribute_score_is_one_for_identical_and_bounded():
    assert attribute_score(M30, M30) == 1.0
    other = ClientProfile("c", "p", "F", 60, 160, 1, goal=Goal.KETO)
    s = attribute_score(M30, other)
    assert 0.0 <= s < 0.15, s                                   # everything differs: restriction term (nothing declared) + residual activity match only


def test_goal_dominates_by_weight_and_unknowns_are_neutral():
    same_goal_other_sex = ClientProfile("c", "p", "F", 30, 165, 5, goal=Goal.VOLUME)
    other_goal_same_rest = ClientProfile("c", "p", "M", 30, 180, 5, goal=Goal.FAT_LOSS)
    assert attribute_score(M30, same_goal_other_sex) > attribute_score(M30, other_goal_same_rest)
    unknown = ClientProfile("c", "p", None, None, None, None, goal=Goal.VOLUME)
    w = DEFAULT_WEIGHTS
    # El denominador son los rasgos OBSERVABLES, no `w.total`. Los cinco originales conservan su 0,5 neutro cuando
    # falta el dato; los añadidos (complexión, método, altura, deporte) se excluyen del numerador y del denominador
    # cuando no se pueden evaluar. Sin eso, dos perfiles IDÉNTICOS sin complexión anotada puntuaban 0,95 en vez de
    # 1,0 —lo comprueba el test de arriba—, que es lo que obligó a cambiar la política, no la expectativa.
    observables = w.goal + w.sex + w.age + w.activity + w.restrictions
    expected = (w.goal * 1 + w.sex * .5 + w.age * .5 + w.activity * .5 + w.restrictions * 1) / observables
    assert abs(attribute_score(M30, unknown) - expected) < 1e-9


def test_age_decays_linearly_to_zero_at_the_span():
    w = AttributeWeights(goal=0, sex=0, age=1, activity=0, restrictions=0, age_span_years=30)
    assert attribute_score(M30, ClientProfile("c", "p", "M", 45, 180, 5, goal=Goal.VOLUME), w) == 0.5
    assert attribute_score(M30, ClientProfile("c", "p", "M", 70, 180, 5, goal=Goal.VOLUME), w) == 0.0


def test_restriction_compatibility_only_counts_declared_flags():
    q = ClientProfile("q", "p", "M", 30, 180, 5, has_intolerances=True)
    assert restriction_compatibility(q, ClientProfile("c", "p", "M", 30, 180, 5, has_intolerances=True)) == 1.0
    assert restriction_compatibility(q, ClientProfile("c", "p", "M", 30, 180, 5)) == 0.3
    assert restriction_compatibility(M30, ClientProfile("c", "p", "M", 30, 180, 5, has_allergies=True)) == 1.0   # query declares nothing


def test_hybrid_mixes_normalised_cosine_and_attributes():
    assert hybrid_score(1.0, 0.0, 0.5) == 0.5 and hybrid_score(0.0, 1.0, 0.5) == 0.5
    assert hybrid_score(1.0, 0.0, 1.0) == 1.0 and hybrid_score(1.0, 0.0, 0.0) == 0.0


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
