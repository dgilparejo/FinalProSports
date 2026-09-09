# -*- coding: utf-8 -*-
"""Application tests of RetrieveSimilarCasesService with in-memory adapters (no database, no model).
What is checked: mandatory exclusions (own client + template groups), embedding only when the strategy needs it,
caller exclusions merged (LOO seam), gap logged below the threshold or on an empty result."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.service.retrieval.retrieve_similar_cases_service import RetrieveSimilarCasesService  # noqa: E402
from finalprosports.domain.composition.policy.gap_policy import CandidateCounts, assess_gap  # noqa: E402
from finalprosports.domain.model import CaseQuery, ClientProfile, Diet, Goal, RetrievedCase, SimilarityScore  # noqa: E402


class FakeEmbedder:
    calls = 0

    def embed_query(self, text):
        FakeEmbedder.calls += 1
        return [1.0, 0.0]

    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def dimension(self):
        return 2


class FakeCases:
    """In-memory CaseRepositoryOutputPort: ranks by a fixed score table, honours exclusions."""

    def __init__(self, diets: dict[str, Diet], scores: dict[str, float], requires_embedding=True):
        self.diets, self.scores, self.requires_embedding, self.last_query = diets, scores, requires_embedding, None

    def find_similar(self, professional_id, query: CaseQuery, k, exclude_diet_ids):
        self.last_query = query
        ranked = sorted((d for d in self.diets if d not in exclude_diet_ids), key=lambda d: -self.scores[d])[:k]
        return tuple(RetrievedCase(self.diets[d], SimilarityScore(0.0, self.scores[d], self.scores[d]), i + 1) for i, d in enumerate(ranked))

    def get(self, professional_id, diet_id):
        return self.diets[diet_id]

    def all_ids(self, professional_id):
        return tuple(self.diets)

    def diet_ids_of_client(self, professional_id, client_code):
        return frozenset(d for d, x in self.diets.items() if x.client_code == client_code)

    def diet_ids_sharing_template_with(self, professional_id, client_code):
        groups = {x.template_group_id for x in self.diets.values() if x.client_code == client_code and x.template_group_id}
        return frozenset(d for d, x in self.diets.items() if x.template_group_id in groups)

    def candidate_counts(self, professional_id, profile, exclude_diet_ids):
        allowed = [x for d, x in self.diets.items() if d not in exclude_diet_ids]
        same = [x for x in allowed if x.goal == profile.goal]
        return CandidateCounts(len(allowed), len(same), len(same), len(same), len(allowed), len(profile.restrictions))


class FakeGaps:
    def __init__(self):
        self.logged = []

    def log(self, professional_id, kind, payload):
        self.logged.append((kind, payload))


def diet(i, client, goal=Goal.VOLUME, tpl=None):
    return Diet(id=i, professional_id="p", client_code=client, goal=goal, meals=(), template_group_id=tpl)


DIETS = {"A::v01": diet("A::v01", "A"), "A::v02": diet("A::v02", "A", tpl="T1"), "B::v01": diet("B::v01", "B", tpl="T1"),
         "C::v01": diet("C::v01", "C"), "D::v01": diet("D::v01", "D"), "E::v01": diet("E::v01", "E")}
SCORES = {"A::v01": .99, "A::v02": .98, "B::v01": .97, "C::v01": .8, "D::v01": .7, "E::v01": .2}
PROFILE_A = ClientProfile("A", "p", "M", 30, 180, 5, goal=Goal.VOLUME)


def test_own_client_and_template_group_are_always_excluded():
    cases = FakeCases(DIETS, SCORES)
    svc = RetrieveSimilarCasesService(FakeEmbedder(), cases)
    ids = [c.diet.id for c in svc.retrieve("p", PROFILE_A, k=5)]
    assert "A::v01" not in ids and "A::v02" not in ids                    # own diets
    assert "B::v01" not in ids                                            # same template group T1 as A::v02
    assert ids == ["C::v01", "D::v01", "E::v01"]


def test_a_portfolio_client_who_is_also_a_corpus_case_never_gets_his_own_diets_back():
    """La fuga de identidad: la cartera identifica por UUID y la base de casos por seudonimo.

    El mismo cliente puede estar en los dos sitios con dos codigos distintos y sin puente entre ellos, asi que la
    exclusion por `client_code` -- que es la que hay -- no lo protege: el sistema le propone SU PROPIA dieta como si
    fuera el caso de un tercero. Se confirmo con un cliente real: sus dos dietas estan en el corpus con J = 1,0000.

    El profesional declara el seudonimo en `corpus_alias` y la exclusion obligatoria tiene que cubrirlo. Este test es
    independiente del dataset y de la base de datos a proposito: fija la regla, no el caso.
    """
    diets = dict(DIETS)
    diets["CLIENTE_022::v01"] = diet("CLIENTE_022::v01", "CLIENTE_022")
    diets["CLIENTE_022::v02"] = diet("CLIENTE_022::v02", "CLIENTE_022")
    scores = dict(SCORES) | {"CLIENTE_022::v01": 1.0, "CLIENTE_022::v02": 0.995}
    cases = FakeCases(diets, scores)
    svc = RetrieveSimilarCasesService(FakeEmbedder(), cases)

    uuid = "5539ebd3-fc81-4532-80d9-53291522d750"
    sin_alias = ClientProfile(uuid, "p", "M", 26, 178, 5, goal=Goal.VOLUME)
    devueltas = {c.diet.id for c in svc.retrieve("p", sin_alias, k=3)}
    assert "CLIENTE_022::v01" in devueltas, "sin alias declarado el caso es legitimo: es otro cliente para el sistema"

    con_alias = ClientProfile(uuid, "p", "M", 26, 178, 5, goal=Goal.VOLUME, corpus_alias="CLIENTE_022")
    exclusiones = svc.mandatory_exclusions("p", con_alias)
    assert "CLIENTE_022::v01" in exclusiones and "CLIENTE_022::v02" in exclusiones, sorted(exclusiones)
    devueltas = {c.diet.id for c in svc.retrieve("p", con_alias, k=6)}
    assert not (devueltas & {"CLIENTE_022::v01", "CLIENTE_022::v02"}), sorted(devueltas)
    assert devueltas, "excluir su alias no puede dejar la propuesta sin candidatos"


def test_the_alias_exclusion_also_covers_the_template_groups_of_the_alias():
    """Si el seudonimo comparte plantilla con otros clientes, esa plantilla es SUYA y tampoco puede volver."""
    diets = dict(DIETS)
    diets["CLIENTE_022::v01"] = diet("CLIENTE_022::v01", "CLIENTE_022", tpl="T9")
    diets["Z::v01"] = diet("Z::v01", "Z", tpl="T9")
    scores = dict(SCORES) | {"CLIENTE_022::v01": 1.0, "Z::v01": 0.99}
    svc = RetrieveSimilarCasesService(FakeEmbedder(), FakeCases(diets, scores))
    con_alias = ClientProfile("uuid-x", "p", "M", 26, 178, 5, goal=Goal.VOLUME, corpus_alias="CLIENTE_022")
    exclusiones = svc.mandatory_exclusions("p", con_alias)
    assert {"CLIENTE_022::v01", "Z::v01"} <= exclusiones, sorted(exclusiones)


def test_caller_exclusions_are_merged_for_leave_one_out():
    svc = RetrieveSimilarCasesService(FakeEmbedder(), FakeCases(DIETS, SCORES))
    ids = [c.diet.id for c in svc.retrieve("p", PROFILE_A, k=5, exclude_diet_ids=frozenset({"C::v01"}))]
    assert ids == ["D::v01", "E::v01"]


def test_embedding_is_computed_only_when_the_strategy_needs_it():
    FakeEmbedder.calls = 0
    vec_cases = FakeCases(DIETS, SCORES, requires_embedding=True)
    RetrieveSimilarCasesService(FakeEmbedder(), vec_cases).retrieve("p", PROFILE_A)
    assert FakeEmbedder.calls == 1 and vec_cases.last_query.embedding == (1.0, 0.0)
    attr_cases = FakeCases(DIETS, SCORES, requires_embedding=False)
    RetrieveSimilarCasesService(FakeEmbedder(), attr_cases).retrieve("p", PROFILE_A)
    assert FakeEmbedder.calls == 1 and attr_cases.last_query.embedding is None


def test_gap_conditions_in_order_of_importance():
    gaps = FakeGaps()
    svc = RetrieveSimilarCasesService(FakeEmbedder(), FakeCases(DIETS, SCORES), gaps, similarity_threshold=0.9)
    svc.retrieve("p", PROFILE_A, k=5)                                     # 3 candidates < k -> scarcity first; low score too (C = 0.8 < 0.9)
    kind, payload = gaps.logged[0]
    assert kind == "candidate_scarcity" and payload["triggered"] == ["candidate_scarcity", "low_score"] and payload["best_score"] == 0.8
    gaps2 = FakeGaps()
    svc2 = RetrieveSimilarCasesService(FakeEmbedder(), FakeCases(DIETS, SCORES), gaps2, similarity_threshold=0.5)
    svc2.retrieve("p", PROFILE_A, k=2)                                    # enough candidates, archetype ok, score ok -> no gap
    assert not gaps2.logged
    gaps3 = FakeGaps()
    lonely = ClientProfile("Z", "p", "M", 30, 180, 5, goal=Goal.VOLUME)
    RetrieveSimilarCasesService(FakeEmbedder(), FakeCases({}, {}), gaps3).retrieve("p", lonely)
    assert gaps3.logged[0][0] == "candidate_scarcity" and gaps3.logged[0][1]["best_score"] is None


def test_gap_policy_restriction_incompatibility_and_poor_archetype():
    c = CandidateCounts(total=100, same_goal=40, same_goal_restriction_free=0, archetype=1, restriction_free=0, restrictions_declared=1)
    a = assess_gap(c, k=5, best_score=0.95, threshold=0.8)
    assert a.triggered == ("candidate_scarcity", "poor_archetype", "restriction_incompatible") and a.kind == "candidate_scarcity"
    assert not assess_gap(CandidateCounts(100, 40, 40, 5, 100, 0), k=5, best_score=0.95, threshold=0.8).is_gap
    assert not assess_gap(CandidateCounts(100, 40, 40, 5, 0, 0), k=5, best_score=0.95, threshold=0.8).restriction_incompatible   # nothing declared


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
