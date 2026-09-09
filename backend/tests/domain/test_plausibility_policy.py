# -*- coding: utf-8 -*-
"""Domain tests of the plausibility policy (S2): the envelope catches quantities outside the professional's observed band, slots with
too many / too few foods, repeated foods, too many mixed-group alternatives, declared restrictions, enforceable prohibitions, missing slot
structure and a rotated version outside the renewal band. No I/O: the envelope is a literal."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope, Violation, check_plausibility, novelty  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    AlternativeGroup, ClientProfile, Diet, DietItem, DietProposal, Food, FoodFlags, FoodGroup, Goal, ItemEvidence, Meal, MealSlot, ProposedItem, ProposedMeal,
    Quantity, Restriction, RestrictionKind, Rule, RuleCheck, RuleScope, RuleStatus, Unit, ValidationReport,
)

CATALOG = {1: Food(1, "pollo", FoodGroup.PROTEIN, "ave"), 2: Food(2, "pavo", FoodGroup.PROTEIN, "ave"), 3: Food(3, "arroz", FoodGroup.CARB, "arroz"),
           4: Food(4, "brócoli", FoodGroup.VEGETABLE, "verdura"), 5: Food(5, "avena", FoodGroup.CARB, "cereal"),
           6: Food(6, "queso", FoodGroup.DAIRY, "lacteo", flags=FoodFlags(contains_lactose=True)), 7: Food(7, "aceite de oliva", FoodGroup.FAT, "aceite"),
           8: Food(8, "ternera", FoodGroup.PROTEIN, "carne")}
ENVELOPE = PlausibilityEnvelope.from_dict({
    "quantities": {"1|g": {"food_id": 1, "unit": "g", "n": 100, "p05": 80, "p50": 200, "p95": 300}, "3|g": {"food_id": 3, "unit": "g", "n": 100, "p05": 50, "p50": 150, "p95": 250},
                   "5|g": {"food_id": 5, "unit": "g", "n": 50, "p05": 30, "p50": 60, "p95": 100}},
    "items_per_slot": {"CENA": {"p05": 2, "p95": 6}, "COMIDA": {"p05": 2, "p95": 6}, "DESAYUNO": {"p05": 1, "p95": 5}},
    "slots_per_diet": {"p05": 2, "p95": 6}, "alternative_groups": {"per_diet_mixed_macro_share": {"p05": 0, "p50": 0.17, "p95": 0.5}}})
PROFILE = ClientProfile("G", "p", "M", 30, 178, 4, goal=Goal.VOLUME)


def item(slot, pos, fid, qty, unit=Unit.GRAM, comp=0, alt=None):
    f = CATALOG[fid]
    return DietItem(slot, pos, comp, fid, f.canonical_name, f.canonical_name, f.canonical_name, Quantity(qty, unit), alternative_group=alt)


def pmeal(slot, *groups):
    return ProposedMeal(slot, tuple(AlternativeGroup(i, tuple(ProposedItem(it, ItemEvidence(("C::v01",), 0.9)) for it in g)) for i, g in enumerate(groups)))


def proposal(meals, profile=PROFILE, checks=()):
    return DietProposal(profile, tuple(meals), ("nota",), ("C::v01",), "case_based_composer", {}, ValidationReport(tuple(checks), ()))


GOOD = [pmeal(MealSlot.BREAKFAST, [item(MealSlot.BREAKFAST, 0, 5, 60)]),
        pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 200), item(MealSlot.LUNCH, 0, 2, 200, comp=1, alt="COMIDA-0")], [item(MealSlot.LUNCH, 1, 3, 150)]),
        pmeal(MealSlot.DINNER, [item(MealSlot.DINNER, 0, 1, 180)], [item(MealSlot.DINNER, 1, 4, 150)], [item(MealSlot.DINNER, 2, 7, 1, Unit.TABLESPOON)])]


def checks_of(v):
    return sorted(x.check for x in v)


def test_plausible_proposal_has_no_violation():
    assert check_plausibility(proposal(GOOD), ENVELOPE, CATALOG) == ()


def test_quantity_outside_the_observed_band_is_named_with_food_value_and_range():
    bad = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 3)], [item(MealSlot.LUNCH, 1, 3, 2000)]),
           pmeal(MealSlot.DINNER, [item(MealSlot.DINNER, 0, 1, 180)], [item(MealSlot.DINNER, 1, 4, 150)])]
    v = [x for x in check_plausibility(proposal(bad), ENVELOPE, CATALOG) if x.check == "quantity_out_of_range"]
    assert [(x.canonical_name, x.slot) for x in v] == [("pollo", "COMIDA"), ("arroz", "COMIDA")]
    assert "3 g fuera de [80, 300] g (n=100)" in str(v[0]) and "2000 g fuera de [50, 250] g" in str(v[1])


def test_unseen_unit_is_reported_only_when_the_food_has_an_envelope():
    meals = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 2, Unit.PIECE)], [item(MealSlot.LUNCH, 1, 3, 150)]),
             pmeal(MealSlot.DINNER, [item(MealSlot.DINNER, 0, 1, 180)], [item(MealSlot.DINNER, 1, 4, 150)])]
    v = check_plausibility(proposal(meals), ENVELOPE, CATALOG)
    assert checks_of(v) == ["unseen_unit"] and v[0].canonical_name == "pollo"


def test_items_per_slot_slot_count_and_repeated_food():
    crowded = pmeal(MealSlot.DINNER, *[[item(MealSlot.DINNER, i, f, 150)] for i, f in enumerate((1, 2, 3, 4, 5, 6, 7))])
    v = check_plausibility(proposal([crowded]), ENVELOPE, CATALOG)
    assert "items_per_slot" in checks_of(v) and "slot_count" in checks_of(v)          # 7 > p95 = 6 foods; 1 slot < p05 = 2
    repeated = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 200)], [item(MealSlot.LUNCH, 1, 1, 200)]), GOOD[2]]
    assert "repeated_food" in checks_of(check_plausibility(proposal(repeated), ENVELOPE, CATALOG))
    assert "slot_count" in checks_of(check_plausibility(proposal(GOOD), ENVELOPE, CATALOG, expected_slots=4))


def test_alternatives_must_share_a_group_and_dinner_needs_protein_and_vegetable():
    mixed = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 200), item(MealSlot.LUNCH, 0, 3, 150, comp=1, alt="COMIDA-0")]),
             pmeal(MealSlot.DINNER, [item(MealSlot.DINNER, 0, 3, 150)])]
    v = check_plausibility(proposal(mixed), ENVELOPE, CATALOG)
    assert "alternative_groups_mixed" in checks_of(v)                                   # 1 of 1 groups mixed (pollo / arroz: PROTEIN vs CARB) > p95 0.5
    across_families = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 200), item(MealSlot.LUNCH, 0, 8, 200, comp=1, alt="COMIDA-0")]), GOOD[2]]
    assert "alternative_groups_mixed" not in checks_of(check_plausibility(proposal(across_families), ENVELOPE, CATALOG))   # pollo / ternera: both PROTEIN
    one_of_three = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 200), item(MealSlot.LUNCH, 0, 3, 150, comp=1, alt="a")], [item(MealSlot.LUNCH, 1, 2, 200), item(MealSlot.LUNCH, 1, 8, 200, comp=1, alt="b")]),
                    pmeal(MealSlot.DINNER, [item(MealSlot.DINNER, 0, 1, 180), item(MealSlot.DINNER, 0, 8, 180, comp=1, alt="c")], [item(MealSlot.DINNER, 1, 4, 150)])]
    assert "alternative_groups_mixed" not in checks_of(check_plausibility(proposal(one_of_three), ENVELOPE, CATALOG))      # 1 of 3 = 0.33 <= p95: his own habit
    structure = [x for x in v if x.check == "slot_structure"]
    assert structure and structure[0].slot == "CENA" and "PROTEIN" in structure[0].detail and "VEGETABLE" in structure[0].detail


def test_declared_restrictions_and_constitution_checks():
    lactose = ClientProfile("G", "p", "F", 30, 165, 3, goal=Goal.KETO, restrictions=(Restriction(RestrictionKind.LACTOSE),))
    meals = GOOD[:2] + [pmeal(MealSlot.DINNER, [item(MealSlot.DINNER, 0, 1, 180)], [item(MealSlot.DINNER, 1, 4, 150)], [item(MealSlot.DINNER, 2, 6, 40)])]
    rules = (Rule("sin_hidratos_cena", "sin hidratos en la cena", RuleScope.GOAL, RuleStatus.KEPT, "item", ("cetosis_keto",)),
             Rule("hidratos_en_cena", "hidratos en la cena", RuleScope.GOAL, RuleStatus.KEPT, "item", ("volumen_masa",), prevalence=0.62))
    checks = (RuleCheck("sin_hidratos_cena", True, False), RuleCheck("hidratos_en_cena", True, False), RuleCheck("agua_2.5L", True, None))
    v = check_plausibility(proposal(meals, lactose, checks), ENVELOPE, CATALOG, rules)
    assert checks_of(v) == ["forbidden_by_constitution", "goal_rule_unsatisfied", "restriction"]
    r = next(x for x in v if x.check == "restriction")
    assert r.canonical_name == "queso" and "contains_lactose" in r.detail


def test_novelty_against_the_previous_version_must_fall_in_the_renewal_band():
    previous = Diet("G::e01", "p", "G", Goal.VOLUME, (Meal(MealSlot.LUNCH, (item(MealSlot.LUNCH, 0, 1, 200), item(MealSlot.LUNCH, 1, 3, 150))),
                                                       Meal(MealSlot.DINNER, (item(MealSlot.DINNER, 0, 2, 180), item(MealSlot.DINNER, 1, 4, 150)))))
    same = proposal(GOOD)
    assert round(novelty(previous, same), 3) == round(1 - 4 / 6, 3)                    # prev {1,2,3,4}, new {5,1,2,3,4,7}
    assert "novelty" in checks_of(check_plausibility(same, ENVELOPE, CATALOG, previous=previous))
    assert "novelty" not in checks_of(check_plausibility(same, ENVELOPE, CATALOG, previous=previous, novelty_band=(0.2, 0.5)))


def test_repeated_food_is_judged_against_the_professionals_p95_per_goal_and_slot():
    """Fase 9: the corpus refuted «no food repeated inside a slot» (he repeats 3.5 times per diet); the limit is his p95 per goal and slot."""
    twice = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 200)], [item(MealSlot.LUNCH, 1, 1, 200)], [item(MealSlot.LUNCH, 2, 3, 150)]), GOOD[0], GOOD[2]]
    assert "repeated_food" in checks_of(check_plausibility(proposal(twice), ENVELOPE, CATALOG))              # not measured -> limit 0 (old behaviour)
    measured = PlausibilityEnvelope.from_dict({
        "quantities": {}, "items_per_slot": {"COMIDA": {"p05": 2, "p95": 6}}, "slots_per_diet": {"p05": 2, "p95": 6},
        "repeats_per_slot": {"COMIDA": {"p05": 0, "p50": 0, "p95": 1}},
        "repeats_per_slot_by_goal": {"volumen_masa": {"COMIDA": {"p05": 0, "p50": 1, "p95": 2}}}})
    assert measured.repeats_limit("volumen_masa", MealSlot.LUNCH) == 2 and measured.repeats_limit("cetosis_keto", MealSlot.LUNCH) == 1
    assert measured.repeats_limit("volumen_masa", MealSlot.DINNER) == 0
    assert "repeated_food" not in checks_of(check_plausibility(proposal(twice), measured, CATALOG))          # 1 repeat <= p95 2 for volumen_masa
    thrice = [pmeal(MealSlot.LUNCH, [item(MealSlot.LUNCH, 0, 1, 200)], [item(MealSlot.LUNCH, 1, 1, 200)], [item(MealSlot.LUNCH, 2, 1, 200)], [item(MealSlot.LUNCH, 3, 1, 200)])]
    v = [x for x in check_plausibility(proposal(thrice), measured, CATALOG) if x.check == "repeated_food"]
    assert v and v[0].canonical_name == "pollo" and "3 repeticiones" in v[0].detail and "p95 (2)" in v[0].detail


def test_violation_string_is_readable():
    v = Violation("quantity_out_of_range", "3 g fuera de [80, 300] g (n=100)", "COMIDA", 1, "pollo")
    assert str(v) == "[quantity_out_of_range] COMIDA · pollo · 3 g fuera de [80, 300] g (n=100)"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
