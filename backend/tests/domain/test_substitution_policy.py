# -*- coding: utf-8 -*-
"""Domain tests: the four families of bad substitution the real-client functional test produced, each with its own
criterion. Every case here is a substitution the engine actually proposed before the policy existed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.substitution_policy import (  # noqa: E402
    counts_as_renewal, is_generic, is_preparation, may_substitute, shares_nominal_head,
)
from finalprosports.domain.model import Food, FoodGroup  # noqa: E402


def food(fid, name, group, family):
    return Food(id=fid, canonical_name=name, group=group, family=family)


PLATANO = food(44, "plátano", FoodGroup.FRUIT, "fruta")
FRUTA = food(39, "fruta", FoodGroup.FRUIT, "fruta")
KIWI = food(40, "kiwi", FoodGroup.FRUIT, "fruta")
ATUN = food(12, "atún", FoodGroup.PROTEIN, "pescado_azul")
PESCADO_AZUL = food(46, "pescado azul", FoodGroup.PROTEIN, "pescado_azul")
CABALLA = food(47, "caballa", FoodGroup.PROTEIN, "pescado_azul")
PAN = food(24, "pan integral", FoodGroup.CARB, "pan")
SANDWICH = food(58, "sándwich", FoodGroup.CARB, "pan")
PATATA = food(29, "patata", FoodGroup.CARB, "tuberculo")
PURE = food(179, "puré de patata", FoodGroup.CARB, "tuberculo")
BONIATO = food(61, "boniato", FoodGroup.CARB, "tuberculo")
ENSALADA = food(13, "ensalada", FoodGroup.VEGETABLE, "verdura")
CEBOLLA = food(54, "cebolla", FoodGroup.VEGETABLE, "verdura")
ESPINACAS = food(38, "espinacas", FoodGroup.VEGETABLE, "verdura")
POLLO = food(1, "pollo", FoodGroup.PROTEIN, "ave")
MEDIANS = {(13, "g"): 150.0, (54, "g"): 20.0, (38, "g"): 130.0, (29, "g"): 162.5, (44, "unidad"): 1.0, (39, "unidad"): 1.0}


def test_the_generic_of_the_family_never_replaces_a_concrete_food():
    assert is_generic(FRUTA) and is_generic(PESCADO_AZUL) and not is_generic(PLATANO) and not is_generic(ATUN)
    ok, why = may_substitute(PLATANO, FRUTA, MEDIANS)
    assert not ok and "genérico" in why
    ok, why = may_substitute(ATUN, PESCADO_AZUL, MEDIANS)
    assert not ok and "genérico" in why
    assert may_substitute(FRUTA, PLATANO, MEDIANS)[0]                 # the other way round is a gain, not a loss
    assert may_substitute(ATUN, CABALLA, MEDIANS)[0]


def test_another_preparation_of_the_same_food_is_not_a_renewal():
    assert shares_nominal_head(PATATA, PURE) and not shares_nominal_head(PATATA, BONIATO)
    ok, why = may_substitute(PATATA, PURE, MEDIANS)
    assert not ok and "cabeza nominal" in why
    assert not counts_as_renewal(PATATA, PURE) and counts_as_renewal(PATATA, BONIATO)
    assert may_substitute(PATATA, BONIATO, MEDIANS)[0]


def test_the_substitute_must_play_the_same_role_in_the_meal():
    ok, why = may_substitute(ENSALADA, CEBOLLA, MEDIANS)              # 150 g vs 20 g: same family, not the same role
    assert not ok and "escala" in why
    assert may_substitute(ENSALADA, ESPINACAS, MEDIANS)[0]            # 150 g vs 130 g
    assert may_substitute(ENSALADA, CEBOLLA, None)[0]                 # with no medians the check cannot fire (declared)


def test_a_preparation_is_never_offered_as_a_substitute():
    assert is_preparation(SANDWICH) and not is_preparation(PAN)
    ok, why = may_substitute(PAN, SANDWICH, MEDIANS)
    assert not ok and "preparación" in why


def test_group_and_family_still_gate_the_substitution():
    assert not may_substitute(PLATANO, POLLO, MEDIANS)[0]             # different group
    assert not may_substitute(ATUN, POLLO, MEDIANS)[0]                # same group, different family
    assert not may_substitute(KIWI, KIWI, MEDIANS)[0]                 # the same food is not a substitution


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
