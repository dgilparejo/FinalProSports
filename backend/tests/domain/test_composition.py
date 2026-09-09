# -*- coding: utf-8 -*-
"""Domain tests of E4: composition policy (alternative groups, thresholds, median quantities by unit, notes), rule engine
(item and note level, phases, low-confidence switch), restriction modes, rule support evidence. Pure Python."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.factory.proposal_factory import build_proposal, to_diet  # noqa: E402
from finalprosports.domain.composition.policy.composition_policy import MIN_NOTE_SUPPORT, CompositionParams, compose_meals, compose_notes  # noqa: E402
from finalprosports.domain.composition.policy.degradation_policy import select_cases  # noqa: E402
from finalprosports.domain.composition.policy.restriction_policy import vetoed, warnings  # noqa: E402
from finalprosports.domain.composition.policy.rule_applicability import applies, phase_of, with_low_confidence_enabled  # noqa: E402
from finalprosports.domain.composition.policy.rule_engine import RuleEngine  # noqa: E402
from finalprosports.domain.composition.policy.rule_support import attach_rule_support  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    ClientProfile, Diet, DietItem, Food, FoodFlags, FoodGroup, Goal, Meal, MealSlot, Quantity, Restriction, RestrictionKind, RestrictionMode,
    RetrievedCase, Rule, RuleConfidence, RuleScope, RuleStatus, SimilarityScore, Unit,
)

CATALOG = {
    1: Food(1, "pollo", FoodGroup.PROTEIN, "ave"), 2: Food(2, "pavo", FoodGroup.PROTEIN, "ave"), 3: Food(3, "arroz", FoodGroup.CARB, "cereal_grano"),
    4: Food(4, "brócoli", FoodGroup.VEGETABLE, "verdura"), 5: Food(5, "avena", FoodGroup.CARB, "cereal"), 6: Food(6, "plátano", FoodGroup.FRUIT, "fruta"),
    7: Food(7, "yogur", FoodGroup.DAIRY, "lacteo", flags=FoodFlags(contains_lactose=True)), 8: Food(8, "galletas", FoodGroup.CARB, "bolleria", flags=FoodFlags(is_processed_sugar=True)),
    9: Food(9, "creatina", FoodGroup.SUPPLEMENT, "suplemento"), 10: Food(10, "sal del himalaya", FoodGroup.CONDIMENT, "sal", flags=FoodFlags(is_salt=True)),
}


def item(slot, pos, comp, fid, q=None, unit=Unit.GRAM, alt=None, generic=False):
    f = CATALOG[fid]
    return DietItem(slot, pos, comp, fid, f.canonical_name, f.canonical_name, f.canonical_name, Quantity(q, unit if q is not None else Unit.NONE),
                    alternative_group=alt, generic_assumption=generic)


def diet(i, slots: dict, notes=(), goal=Goal.VOLUME, version=None):
    return Diet(id=i, professional_id="p", client_code=i.split("::")[0], goal=goal, notes=tuple(notes), diet_version=version,
                meals=tuple(Meal(s, tuple(items)) for s, items in slots.items()))


def case(d, rank):
    return RetrievedCase(d, SimilarityScore(0, 1, 1), rank)


PROFILE = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.VOLUME)
CASES = (
    case(diet("A::v01", {MealSlot.LUNCH: [item(MealSlot.LUNCH, 0, 0, 1, 150, alt="g"), item(MealSlot.LUNCH, 0, 1, 2, 160, alt="g"), item(MealSlot.LUNCH, 1, 0, 3, 80)],
                         MealSlot.DINNER: [item(MealSlot.DINNER, 0, 0, 1, 200), item(MealSlot.DINNER, 1, 0, 4, 150)]}, ["Beber 2,5 litros de agua", "Comer despacio"]), 1),
    case(diet("B::v01", {MealSlot.LUNCH: [item(MealSlot.LUNCH, 0, 0, 1, 170, alt="g"), item(MealSlot.LUNCH, 0, 1, 2, 150, alt="g"), item(MealSlot.LUNCH, 1, 0, 3, 100)],
                         MealSlot.DINNER: [item(MealSlot.DINNER, 0, 0, 2, 180), item(MealSlot.DINNER, 1, 0, 4, 200)]}, ["beber 2,5 litros de agua", "Nada de azúcar"]), 2),
    case(diet("C::v01", {MealSlot.LUNCH: [item(MealSlot.LUNCH, 0, 0, 1, 1, Unit.PIECE), item(MealSlot.LUNCH, 1, 0, 6, 1, Unit.PIECE)],
                         MealSlot.BREAKFAST: [item(MealSlot.BREAKFAST, 0, 0, 5, 60)]}, ["Beber 2,5 litros de agua"]), 3),
)


def test_alternatives_thresholds_and_median_by_unit():
    meals = compose_meals(CASES, CompositionParams(k=3, inclusion_threshold=0.5), CATALOG)
    by_slot = {m.slot: m for m in meals}
    assert MealSlot.BREAKFAST not in by_slot                               # 1/3 cases < slot threshold 0.5
    lunch = by_slot[MealSlot.LUNCH]
    leader = lunch.groups[0]
    assert [o.item.food_id for o in leader.options] == [1, 2]              # pollo / pavo written as alternatives in 2 of 2 pavo cases
    assert leader.options[0].item.quantity == Quantity(160, Unit.GRAM)     # median of 150/170 (1 pieza is another unit: dropped, grams dominate)
    assert leader.options[0].evidence.support == 1.0 and leader.options[1].evidence.support == round(2 / 3, 4)
    assert [o.item.food_id for g in lunch.groups[1:] for o in g.options] == [3]   # arroz 2/3 >= 0.5; plátano 1/3 excluded
    assert lunch.groups[0].options[0].item.alternative_group == "COMIDA-0" and lunch.groups[1].options[0].item.alternative_group is None


def test_threshold_controls_size():
    small = compose_meals(CASES, CompositionParams(k=3, inclusion_threshold=0.9), CATALOG)
    big = compose_meals(CASES, CompositionParams(k=3, inclusion_threshold=0.2), CATALOG)
    n = lambda ms: sum(len(m.items) for m in ms)  # noqa: E731
    # 8 before the support floor: with MIN_CASE_SUPPORT the foods only one of the three cases carries drop out, which is the
    # point of the floor — a low threshold buys recall, never evidence.
    assert n(small) < n(big) and n(big) == 4


def test_notes_by_frequency_and_the_single_source_floor():
    notes = compose_notes(CASES, CompositionParams(k=3, inclusion_threshold=0.5, min_notes=2))
    assert notes[0].lower() == "beber 2,5 litros de agua"
    # min_notes asks for two, but "Comer despacio" and "Nada de azúcar" were each written by ONE client: emitting either would
    # copy that person's own sentence into a stranger's diet. The floor wins over the top-up; the proposal comes back shorter.
    assert len(notes) == 1


def test_a_note_only_one_retrieved_client_wrote_is_never_emitted():
    for k, t, mn in ((3, 0.5, 5), (1, 0.0, 3), (2, 0.35, 3)):                     # top-up branch, tiny k, threshold branch
        for n in compose_notes(CASES[:k], CompositionParams(k=k, inclusion_threshold=t, min_notes=mn)):
            support = sum(1 for c in CASES[:k] if any(x.strip().lower() == n.strip().lower() for x in c.diet.notes))
            assert support >= MIN_NOTE_SUPPORT, f"note emitted with support {support} (k={k}, note_t={t})"


def test_rule_engine_item_note_phase_and_switch():
    rules = (Rule("sin_hidratos_cena", "", RuleScope.GOAL, RuleStatus.KEPT, "item", ("cetosis_keto",), RuleConfidence.HIGH),
             Rule("hidratos_en_cena", "", RuleScope.GOAL, RuleStatus.KEPT, "item", ("volumen_masa",), RuleConfidence.MEDIUM),
             Rule("agua_2.5L", "", RuleScope.GLOBAL, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH),
             Rule("comer_despacio", "", RuleScope.GLOBAL, RuleStatus.RETIRED, "note", (), RuleConfidence.LOW, enabled=False),
             Rule("saltarse_comidas_fases_tempranas", "", RuleScope.PHASE, RuleStatus.KEPT, "note", ("v1", "v2-4"), RuleConfidence.MEDIUM))
    engine = RuleEngine(CATALOG)
    d = diet("Z::v02", {MealSlot.DINNER: [item(MealSlot.DINNER, 0, 0, 1, 200), item(MealSlot.DINNER, 1, 0, 3, 80)]}, ["Beber 2,5 litros de agua", "comer despacio"], version=2)
    checks = {c.rule_id: c for c in engine.check(rules, d, PROFILE)}
    assert "sin_hidratos_cena" not in checks                              # keto rule does not apply to a volume profile
    assert checks["hidratos_en_cena"].satisfied is True and checks["agua_2.5L"].satisfied is True
    assert "comer_despacio" not in checks                                 # low confidence: disabled by default
    assert checks["saltarse_comidas_fases_tempranas"].applicable and checks["saltarse_comidas_fases_tempranas"].satisfied is False   # phase v2-4 applies; note absent
    with_low = with_low_confidence_enabled(rules, True)
    assert {c.rule_id: c.satisfied for c in engine.check(with_low, d, PROFILE)}["comer_despacio"] is True
    assert phase_of(1) == "v1" and phase_of(4) == "v2-4" and phase_of(9) == "v5+" and phase_of(None) is None
    keto = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.KETO)
    assert applies(rules[0], keto) and not applies(rules[0], PROFILE)
    assert engine.compliance(rules, d, PROFILE, only={"hidratos_en_cena"}) == (1.0, 1)


def test_restriction_modes_lactose():
    yogur, galletas = CATALOG[7], CATALOG[8]
    intolerant = ClientProfile("Q", "p", "F", 30, 165, 3, has_intolerances=True, restrictions=(Restriction(RestrictionKind.LACTOSE),))
    assert vetoed(yogur, intolerant, RestrictionMode.STRICT)
    assert not vetoed(yogur, intolerant, RestrictionMode.PROFESSIONAL) and warnings(yogur, intolerant, RestrictionMode.PROFESSIONAL) == ("contains_lactose:yogur",)
    assert not vetoed(galletas, intolerant, RestrictionMode.STRICT)
    gluten = ClientProfile("Q", "p", "F", 30, 165, 3, restrictions=(Restriction(RestrictionKind.GLUTEN),))
    assert not vetoed(yogur, gluten, RestrictionMode.PROFESSIONAL)         # only lactose is tolerated in PROFESSIONAL mode


def test_a_slot_backed_by_a_single_case_is_not_a_consensus():
    """MIN_CASE_SUPPORT, the floor swept onto every threshold expressed as a share of k. With three cases a slot present in
    one of them scores 0,33: enough for a low inclusion threshold, never enough to call it a consensus."""
    meals = compose_meals(CASES, CompositionParams(k=3, inclusion_threshold=0.1, slot_threshold=0.1), CATALOG)
    assert not [m for m in meals if m.slot is MealSlot.BREAKFAST]
    # ... but the declared copy_top1 degradation still works: with one case, one case IS all the support there is
    one = compose_meals(CASES[:1], CompositionParams(k=1, inclusion_threshold=0.1, slot_threshold=0.1), CATALOG)
    assert [m.slot for m in one]


def test_rule_support_and_to_diet_roundtrip():
    rules = [Rule("hidratos_en_cena", "", RuleScope.GOAL, RuleStatus.KEPT, "item", ("volumen_masa",), RuleConfidence.MEDIUM, prevalence=0.61, lift=1.4),
             Rule("desayuno_avena_cereales", "", RuleScope.PLACEMENT, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH, prevalence=0.8, lift=1.1)]
    meals = compose_meals(CASES, CompositionParams(k=3, inclusion_threshold=0.2), CATALOG)
    meals = attach_rule_support(meals, rules, CATALOG)
    # BREAKFAST is in ONE of the three cases: below the share threshold it would already be out, and below MIN_CASE_SUPPORT
    # it is out whatever the share says. A slot backed by a single client is that client's diet, not a consensus.
    assert not [m for m in meals if m.slot is MealSlot.BREAKFAST]
    lunch = next(m for m in meals if m.slot is MealSlot.LUNCH)
    assert all(o.evidence.rules == () for g in lunch.groups for o in g.options if o.item.food_id in (1, 2))   # protein at lunch: no rule backs it
    prop = build_proposal(PROFILE, meals, ["nota"], ["A::v01"], "case_based_composer", {"k": 3})
    d = to_diet(prop)
    assert d.goal is Goal.VOLUME and d.notes == ("nota",) and {m.slot for m in d.meals} == {m.slot for m in meals}
    assert sum(len(m.items) for m in d.meals) == sum(len(m.items) for m in meals)


def test_degradation_copies_best_same_goal_case_when_goals_are_mixed():
    keto = case(diet("K::v01", {MealSlot.DINNER: [item(MealSlot.DINNER, 0, 0, 1, 200)]}, goal=Goal.KETO), 4)
    mixed = CASES + (keto,)
    volume = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.VOLUME)
    used, mode, p = select_cases(mixed, volume, CompositionParams(k=4, inclusion_threshold=0.35))
    assert mode == "copy_top1" and [c.diet.id for c in used] == ["A::v01"] and p.inclusion_threshold == 0.0     # best same-goal case, threshold 0 -> copy
    used, mode, p = select_cases(mixed, volume, CompositionParams(k=4, inclusion_threshold=0.35, degradation="reduce_k", min_cases_to_compose=3))
    assert mode == "reduce_k" and [c.diet.id for c in used] == ["A::v01", "B::v01", "C::v01"] and p.inclusion_threshold == 0.35
    used, mode, _ = select_cases(mixed, volume, CompositionParams(k=4, inclusion_threshold=0.35, degradation="none"))
    assert mode == "none" and len(used) == 4
    used, mode, _ = select_cases(CASES, volume, CompositionParams(k=3, inclusion_threshold=0.35))
    assert mode == "none" and len(used) == 3                                                                   # every case shares the goal: no degradation
    keto_profile = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.KETO)
    used, mode, _ = select_cases(mixed, keto_profile, CompositionParams(k=4, inclusion_threshold=0.35))
    assert mode == "copy_top1" and [c.diet.id for c in used] == ["K::v01"]
    copied = compose_meals(used, CompositionParams(k=1, inclusion_threshold=0.0), CATALOG)
    assert [o.item.food_id for m in copied for o in m.items] == [1]                                             # copy reproduces the case



def test_the_avocado_may_go_in_dinner_and_dessert_fruit_may_not():
    """`fruta_no_en_cena` reads the PRIMARY food group, never the secondary one.

    Measured on dataset-v3 BEFORE changing anything: the three foods whose secondary group is FRUIT while their
    primary group is not are ones the professional serves at dinner constantly -- aguacate 25,6 % of its 661 uses,
    guacamole 31,7 % of 164, aceitunas 57,4 % of 47 -- whereas every food whose PRIMARY group is FRUIT sits between
    0,0 % and 1,4 % (the highest, limón at 4,8 %, is a dressing). The rule was never wrong; the predicate was,
    because it convicted a food of its botany instead of its culinary role. The fix is the predicate, not a list of
    exceptions, which is why the engine names no food and this test builds the two shapes instead.
    """
    catalog = {**CATALOG,
               11: Food(11, "aguacate", FoodGroup.FAT, "grasa", secondary_group=FoodGroup.FRUIT),
               12: Food(12, "merluza", FoodGroup.PROTEIN, "pescado_blanco")}
    engine = RuleEngine(catalog)
    rule = Rule("fruta_no_en_cena", "", RuleScope.PLACEMENT, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH)

    def dinner_of(*fids):
        return Diet(id="X::v01", professional_id="p", client_code="X", goal=Goal.VOLUME, notes=(), diet_version=1,
                    meals=(Meal(MealSlot.DINNER, tuple(
                        DietItem(MealSlot.DINNER, 0, i, fid, catalog[fid].canonical_name, catalog[fid].canonical_name,
                                 catalog[fid].canonical_name, Quantity(100, Unit.GRAM))
                        for i, fid in enumerate(fids))),))

    assert engine.evaluate(rule, dinner_of(12, 11)) is True, "el aguacate debe poder ir en la cena"
    assert engine.evaluate(rule, dinner_of(12, 6)) is False, "la fruta de postre (plátano) sigue vetada"

if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
