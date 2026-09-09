# -*- coding: utf-8 -*-
"""Application tests of DietValidator and ProposeDietUseCase with in-memory collaborators: restriction veto has priority,
enforceable prohibitions remove the offending options (group kept when another option survives), report lists forced
changes and warnings, use case wires retrieval -> strategy -> validator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.service.validation.diet_validator import DietValidator  # noqa: E402
from finalprosports.application.strategy.case_based_composer import CaseBasedComposer  # noqa: E402
from finalprosports.application.usecase.proposal.propose_diet_use_case import ProposeDietUseCase  # noqa: E402
from finalprosports.domain.composition.factory.proposal_factory import build_proposal  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    AlternativeGroup, ClientProfile, Diet, DietItem, Food, FoodFlags, FoodGroup, Goal, ItemEvidence, Meal, MealSlot, ProposedItem, ProposedMeal, Quantity,
    Restriction, RestrictionKind, RestrictionMode, RetrievedCase, Rule, RuleConfidence, RuleScope, RuleStatus, SimilarityScore, Unit,
)

CATALOG = {1: Food(1, "pollo", FoodGroup.PROTEIN, "ave"), 2: Food(2, "pavo", FoodGroup.PROTEIN, "ave"), 3: Food(3, "arroz", FoodGroup.CARB, "cereal_grano"),
           4: Food(4, "brócoli", FoodGroup.VEGETABLE, "verdura"), 6: Food(6, "plátano", FoodGroup.FRUIT, "fruta"),
           7: Food(7, "yogur", FoodGroup.DAIRY, "lacteo", flags=FoodFlags(contains_lactose=True)),
           8: Food(8, "galletas", FoodGroup.CARB, "bolleria", flags=FoodFlags(is_processed_sugar=True))}
RULES = (Rule("prohibido_azucar_procesados", "", RuleScope.GLOBAL, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH),
         Rule("sin_hidratos_cena", "", RuleScope.GOAL, RuleStatus.KEPT, "item", ("cetosis_keto",), RuleConfidence.HIGH),
         Rule("fruta_no_en_cena", "", RuleScope.AVOID_PLACEMENT, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH),
         Rule("cena_proteina_grasa_verdura", "", RuleScope.PLACEMENT, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH))


def pitem(slot, pos, comp, fid, alt=None):
    f = CATALOG[fid]
    return ProposedItem(DietItem(slot, pos, comp, fid, f.canonical_name, f.canonical_name, f.canonical_name, Quantity(100, Unit.GRAM), alternative_group=alt),
                        ItemEvidence(("A::v01",), 1.0))


def proposal(profile):
    dinner = ProposedMeal(MealSlot.DINNER, (AlternativeGroup(0, (pitem(MealSlot.DINNER, 0, 0, 1, "g"), pitem(MealSlot.DINNER, 0, 1, 7, "g"))),
                                            AlternativeGroup(1, (pitem(MealSlot.DINNER, 1, 0, 3),)), AlternativeGroup(2, (pitem(MealSlot.DINNER, 2, 0, 4),)),
                                            AlternativeGroup(3, (pitem(MealSlot.DINNER, 3, 0, 6),))))
    snack = ProposedMeal(MealSlot.SNACK, (AlternativeGroup(0, (pitem(MealSlot.SNACK, 0, 0, 8),)),))
    return build_proposal(profile, [snack, dinner], ["nota"], ["A::v01"], "case_based_composer")


def foods_of(p, slot):
    return [o.item.food_id for m in p.meals if m.slot is slot for o in m.items]


def test_restrictions_have_priority_and_keep_the_group():
    intolerant = ClientProfile("Q", "p", "F", 30, 165, 3, goal=Goal.KETO, has_intolerances=True, restrictions=(Restriction(RestrictionKind.LACTOSE),))
    out = DietValidator(CATALOG, RestrictionMode.STRICT, enforce_rules=False).validate(proposal(intolerant), RULES)
    assert foods_of(out, MealSlot.DINNER) == [1, 3, 4, 6]                 # yogur removed, pollo keeps the group
    assert [(f.food_id, f.reason) for f in out.validation.forced_changes] == [(7, "restriction:contains_lactose")]
    assert out.validation.warnings == ()
    prof_mode = DietValidator(CATALOG, RestrictionMode.PROFESSIONAL, enforce_rules=False).validate(proposal(intolerant), RULES)
    assert 7 in foods_of(prof_mode, MealSlot.DINNER) and prof_mode.validation.warnings == ("contains_lactose:yogur",)


def test_enforced_prohibitions_and_report():
    keto = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.KETO)
    out = DietValidator(CATALOG, RestrictionMode.STRICT, enforce_rules=True).validate(proposal(keto), RULES)
    assert foods_of(out, MealSlot.DINNER) == [1, 7, 4]                    # arroz (carb at dinner, keto) and plátano (fruit at dinner) removed
    assert foods_of(out, MealSlot.SNACK) == []                            # galletas removed -> group and meal disappear
    reasons = sorted(f.reason for f in out.validation.forced_changes)
    assert reasons == ["rule:fruta_no_en_cena", "rule:prohibido_azucar_procesados", "rule:sin_hidratos_cena"]
    checks = {c.rule_id: c for c in out.validation.rule_checks}
    assert checks["sin_hidratos_cena"].satisfied and checks["sin_hidratos_cena"].enforced
    assert checks["cena_proteina_grasa_verdura"].satisfied and not checks["cena_proteina_grasa_verdura"].enforced
    assert out.validation.compliance == 1.0
    raw = DietValidator(CATALOG, RestrictionMode.STRICT, enforce_rules=False).validate(proposal(keto), RULES)
    assert raw.validation.compliance == 0.25 and not raw.validation.forced_changes


class FakeRetrieval:
    def __init__(self, cases):
        self.cases = cases

    def retrieve(self, professional_id, profile, k=5, exclude_diet_ids=frozenset()):
        return self.cases[:k]


class FakeRules:
    def all(self, professional_id):
        return RULES


def test_use_case_wires_retrieval_strategy_validator():
    d = Diet("A::v01", "p", "A", Goal.VOLUME, (Meal(MealSlot.DINNER, (pitem(MealSlot.DINNER, 0, 0, 1).item, pitem(MealSlot.DINNER, 1, 0, 3).item)),), notes=("nota",))
    cases = (RetrievedCase(d, SimilarityScore(0, 1, 1), 1),)
    uc = ProposeDietUseCase(FakeRetrieval(cases), CaseBasedComposer(CATALOG), DietValidator(CATALOG), FakeRules())
    out = uc.propose("p", ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.VOLUME), k=1)
    assert out.strategy == "case_based_composer" and out.validation is not None and out.retrieved_case_ids == ("A::v01",) and out.parameters["k"] == 8
    # a single retrieved case cannot support a note: emitting it would copy that one client's sentence verbatim
    # (MIN_NOTE_SUPPORT). The foods still come through — the floor guards the free text, not the composition.
    assert foods_of(out, MealSlot.DINNER) == [1, 3] and out.notes == ()


class FakeRecurrent:
    name = "fake_rotation"

    def propose(self, profile, cases, rules, params=None, history=(), **kw):
        d = history[-1]
        return build_proposal(profile, [ProposedMeal(m.slot, (AlternativeGroup(0, tuple(ProposedItem(i, ItemEvidence((d.id,), 1.0)) for i in m.items)),)) for m in d.meals], list(d.notes), [d.id], self.name, {"mode": "rotation"})


def test_use_case_routes_by_history_and_goal_change():
    prev = Diet("Q::v01", "p", "Q", Goal.VOLUME, (Meal(MealSlot.DINNER, (pitem(MealSlot.DINNER, 0, 0, 2).item,)),), notes=("anterior",), diet_version=1)
    case_d = Diet("A::v01", "p", "A", Goal.VOLUME, (Meal(MealSlot.DINNER, (pitem(MealSlot.DINNER, 0, 0, 1).item, pitem(MealSlot.DINNER, 1, 0, 3).item)),), notes=("nota",))
    cases = (RetrievedCase(case_d, SimilarityScore(0, 1, 1), 1),)
    uc = ProposeDietUseCase(FakeRetrieval(cases), CaseBasedComposer(CATALOG), DietValidator(CATALOG), FakeRules(), recurrent_strategy=FakeRecurrent())
    same_goal = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.VOLUME)
    out = uc.propose("p", same_goal, k=1, history=(prev,))
    assert out.strategy == "fake_rotation" and foods_of(out, MealSlot.DINNER) == [2]            # same goal: start from the previous version
    changed = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.KETO)
    out2 = uc.propose("p", changed, k=1, history=(prev,))
    assert out2.strategy == "case_based_composer"                                                # goal changed: archetype consensus
    out3 = uc.propose("p", same_goal, k=1, history=())
    assert out3.strategy == "case_based_composer"                                                # no history: cold start
    uc_off = ProposeDietUseCase(FakeRetrieval(cases), CaseBasedComposer(CATALOG), DietValidator(CATALOG), FakeRules(), recurrent_strategy=FakeRecurrent(), route_goal_change_to_archetype=False)
    assert uc_off.propose("p", changed, k=1, history=(prev,)).strategy == "fake_rotation"       # routing switch off


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
