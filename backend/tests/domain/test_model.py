# -*- coding: utf-8 -*-
"""Domain unit tests: pure Python, milliseconds, no infrastructure."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.placement_policy import allowed_in_slot  # noqa: E402
from finalprosports.domain.composition.policy.quantity_policy import median_quantity  # noqa: E402
from finalprosports.domain.composition.policy.restriction_policy import vetoed  # noqa: E402
from finalprosports.domain.composition.policy.rule_applicability import applies  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    ClientProfile, Food, FoodFlags, FoodGroup, Goal, MealSlot, Quantity, Restriction, RestrictionKind, Rule, RuleConfidence, RuleScope, RuleStatus, Unit,
)


def test_values_stay_spanish_identifiers_english():
    assert MealSlot.LUNCH == "COMIDA" and MealSlot.POST_WORKOUT == "DESPUES DE ENTRENAR"
    assert Goal.VOLUME == "volumen_masa" and Unit.TABLESPOON == "cucharada"


def test_median_quantity_picks_dominant_unit():
    q = median_quantity([Quantity(150, Unit.GRAM), Quantity(200, Unit.GRAM), Quantity(1, Unit.PIECE)])
    assert q.unit is Unit.GRAM and q.value == 175


def test_restriction_veto_uses_flag_name():
    salmon = Food(id=1, canonical_name="salmón", group=FoodGroup.PROTEIN, family="pescado_azul", flags=FoodFlags(contains_fish=True))
    profile = ClientProfile("CLIENTE_001", "prof_001", "M", 30, 180, 5, restrictions=(Restriction(RestrictionKind.FISH),))
    assert vetoed(salmon, profile)
    lenient = ClientProfile("CLIENTE_001", "prof_001", "M", 30, 180, 5, restrictions=(Restriction(RestrictionKind.FISH, strict=False),))
    assert not vetoed(salmon, lenient)


def test_rule_applicability_by_goal():
    rule = Rule(id="sin_hidratos_cena", statement="", scope=RuleScope.GOAL, status=RuleStatus.KEPT, evaluation_level="item",
                condition=("cetosis_keto", "ayuno_intermitente"), confidence=RuleConfidence.HIGH)
    keto = ClientProfile("c", "p", "M", 30, 180, 5, goal=Goal.KETO)
    volume = ClientProfile("c", "p", "M", 30, 180, 5, goal=Goal.VOLUME)
    assert applies(rule, keto) and not applies(rule, volume)


def test_placement_policy():
    assert not allowed_in_slot(FoodGroup.FRUIT, MealSlot.DINNER, True)
    assert allowed_in_slot(FoodGroup.CARB, MealSlot.DINNER, True) and not allowed_in_slot(FoodGroup.CARB, MealSlot.DINNER, False)


def test_rule_nature_prescriptive_or_descriptive():
    from finalprosports.domain.model import MAJORITY_PREVALENCE, Rule, RuleNature, RuleScope, RuleStatus
    assert MAJORITY_PREVALENCE == 0.5
    stored = Rule("ayuno_16h", "16 h de ayuno", RuleScope.GOAL, RuleStatus.KEPT, "note", ("ayuno_intermitente",), prevalence=0.76, nature=RuleNature.PRESCRIPTIVE)
    minority = Rule("ansiedad_chocolate_o_gelatina", "chocolate o gelatina", RuleScope.GOAL, RuleStatus.KEPT, "item", ("definicion_grasa",), prevalence=0.268,
                    nature=RuleNature.DESCRIPTIVE)
    assert stored.is_prescriptive and not minority.is_prescriptive
    # constitution loaded without the field (before migration 0009): the prevalence cut decides, retired rules never prescribe
    assert Rule("a", "a", RuleScope.GOAL, RuleStatus.KEPT, "item", prevalence=0.62).is_prescriptive
    assert not Rule("b", "b", RuleScope.GOAL, RuleStatus.KEPT, "item", prevalence=0.27).is_prescriptive
    assert not Rule("c", "c", RuleScope.GOAL, RuleStatus.RETIRED, "item", prevalence=0.94).is_prescriptive
    assert Rule("respetar_intolerancias_alergias", "respetar", RuleScope.POLICY, RuleStatus.POLICY, "item").is_prescriptive is False   # policy: only via the stored nature



if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1; print(f"FAIL  {name}: {e}")
    sys.exit(1 if failed else 0)
