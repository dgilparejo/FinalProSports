# -*- coding: utf-8 -*-
"""Domain tests of the rotation policy (2.3): anchors by persistence or by lift are kept, rotatory species are replaced within
their family from the consensus (then from the repertoire), the renewal budget follows the professional's measured rate, foods
without evidence are kept, and RotationStats can be re-derived without one client (leave-one-client-out)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.rotation_policy import RotationParams, is_anchor, rotate  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    AlternativeGroup, Diet, DietItem, Food, FoodGroup, Goal, ItemEvidence, Meal, MealSlot, ProposedItem, ProposedMeal, Quantity, RotationStats, Unit,
)

CATALOG = {1: Food(1, "pollo", FoodGroup.PROTEIN, "ave"), 2: Food(2, "pavo", FoodGroup.PROTEIN, "ave"), 3: Food(3, "arroz", FoodGroup.CARB, "arroz"),
           4: Food(4, "brócoli", FoodGroup.VEGETABLE, "verdura"), 5: Food(5, "espinacas", FoodGroup.VEGETABLE, "verdura"), 6: Food(6, "calabacín", FoodGroup.VEGETABLE, "verdura"),
           7: Food(7, "creatina", FoodGroup.SUPPLEMENT, "aminoacidos"), 8: Food(8, "salmón", FoodGroup.PROTEIN, "pescado_azul"), 9: Food(9, "caballa", FoodGroup.PROTEIN, "pescado_azul")}
# persistence: pollo 0.9 (anchor), arroz 0.9 (anchor), creatina 0.6 with prevalence 0.2 -> lift 3 (anchor by lift), brócoli 0.3 (rotatory), salmón 0.2 (rotatory), espinacas n<10
STATS = RotationStats(food_n={1: 100, 3: 100, 7: 50, 4: 40, 8: 40, 5: 5}, food_kept={1: 90, 3: 90, 7: 30, 4: 12, 8: 8, 5: 1},
                      food_prevalence={1: 0.9, 3: 0.9, 7: 0.2, 4: 0.3, 8: 0.2, 5: 0.1}, family_persistence={"ave": 0.96, "verdura": 0.96, "pescado_azul": 0.79},
                      renewal_same_goal=0.5, renewal_goal_change=0.75, per_client={"A": {4: (10, 8)}})


def item(slot, pos, fid, comp=0, alt=None):
    f = CATALOG[fid]
    return DietItem(slot, pos, comp, fid, f.canonical_name, f.canonical_name, f.canonical_name, Quantity(100, Unit.GRAM), alternative_group=alt)


PREVIOUS = Diet("A::v03", "p", "A", Goal.VOLUME, (Meal(MealSlot.LUNCH, (item(MealSlot.LUNCH, 0, 1), item(MealSlot.LUNCH, 1, 3), item(MealSlot.LUNCH, 2, 4))),
                                                 Meal(MealSlot.DINNER, (item(MealSlot.DINNER, 0, 8), item(MealSlot.DINNER, 1, 5))),
                                                 Meal(MealSlot.POST_WORKOUT, (item(MealSlot.POST_WORKOUT, 0, 7),))), notes=("nota",), diet_version=3)


def pitem(slot, fid):
    return ProposedItem(item(slot, 0, fid), ItemEvidence(("X::v01",), 0.8))


CONSENSUS = [ProposedMeal(MealSlot.LUNCH, (AlternativeGroup(0, (pitem(MealSlot.LUNCH, 2),)), AlternativeGroup(1, (pitem(MealSlot.LUNCH, 6),)))),
             ProposedMeal(MealSlot.DINNER, (AlternativeGroup(0, (pitem(MealSlot.DINNER, 9),)),))]


def foods(meals):
    return {m.slot: [o.item.food_id for o in m.items] for m in meals}


def test_anchor_by_persistence_or_by_lift():
    p = RotationParams()
    assert is_anchor(1, STATS, p) and is_anchor(3, STATS, p)           # persistence 0.9
    assert is_anchor(7, STATS, p)                                      # persistence 0.6 but lift 3.0 >= 2.0
    assert not is_anchor(4, STATS, p) and not is_anchor(8, STATS, p)   # rotatory
    assert not is_anchor(5, STATS, p)                                  # n < min_n: no evidence


def test_rotate_keeps_anchors_and_replaces_rotatory_within_family_up_to_budget():
    meals, changes, _ = rotate(PREVIOUS, CONSENSUS, goal_changed=False, stats=STATS, catalog=CATALOG, params=RotationParams(use_repertoire=False))
    f = foods(meals)
    assert f[MealSlot.LUNCH][:2] == [1, 3]                              # pollo and arroz kept (anchors)
    assert f[MealSlot.POST_WORKOUT] == [7]                              # creatina kept (anchor by lift)
    assert set(f[MealSlot.LUNCH][2:]) | set(f[MealSlot.DINNER]) >= {6, 9} or (f[MealSlot.LUNCH][2] == 6 and f[MealSlot.DINNER][0] == 9)
    # budget: renewal 0.5 of 6 items = 3, but only two rotatory items with evidence -> 2 changes; espinacas (n<10) kept
    assert len(changes) == 2 and {c.removed_food_id for c in changes} == {4, 8} and {c.added_food_id for c in changes} == {6, 9}
    assert all(CATALOG[c.removed_food_id].family == CATALOG[c.added_food_id].family for c in changes)
    assert f[MealSlot.DINNER][1] == 5
    assert sum(len(v) for v in f.values()) == 6                         # structure and size preserved


def test_budget_limits_rotation_and_repertoire_fills_when_consensus_has_nothing():
    small = RotationParams(renewal_target=0.17, use_repertoire=False)   # 0.17 * 6 = 1 replacement
    _, changes, _ = rotate(PREVIOUS, CONSENSUS, False, STATS, CATALOG, small)
    assert len(changes) == 1 and changes[0].removed_food_id == 8       # lowest persistence first (salmón 0.2 < brócoli 0.3)
    _, none, _ = rotate(PREVIOUS, [], False, STATS, CATALOG, RotationParams(use_repertoire=False))
    assert none == []                                                   # no consensus, no repertoire: nothing rotates
    _, rep, _ = rotate(PREVIOUS, [], False, STATS, CATALOG, RotationParams(use_repertoire=True), repertoire={"verdura": [4, 6, 5], "pescado_azul": [8, 9]})
    assert {c.added_food_id for c in rep} == {6, 9}                     # repertoire skips foods already in the previous version (4, 8, 5)


def test_goal_change_uses_the_higher_renewal_target():
    _, same, _ = rotate(PREVIOUS, CONSENSUS, False, STATS, CATALOG, RotationParams(use_repertoire=True), repertoire={"verdura": [6], "pescado_azul": [9]})
    _, changed, _ = rotate(PREVIOUS, CONSENSUS, True, STATS, CATALOG, RotationParams(use_repertoire=True), repertoire={"verdura": [6], "pescado_azul": [9]})
    assert len(changed) >= len(same)


def test_stats_without_client_removes_its_contribution():
    s2 = STATS.without_client("A")
    assert s2.n(4) == 30 and abs(s2.persistence(4) - 4 / 30) < 1e-9     # 40-10 pairs, 12-8 kept
    assert STATS.n(4) == 40 and STATS.without_client("nobody") is STATS


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
