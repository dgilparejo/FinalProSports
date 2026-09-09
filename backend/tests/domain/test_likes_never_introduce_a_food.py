# -*- coding: utf-8 -*-
"""LOS GUSTOS DESEMPATAN, NO PROPONEN. La condición del bloque 8.2b, con un guarda que puede fallar.

Los «gustos positivos» entran en la composición porque está medido que él los tiene en cuenta: los alimentos que un
cliente declara aparecen en sus dietas **+0,0643 [+0,0120, +0,1211]** por encima de la tasa base del mismo alimento en
el mismo objetivo, y el control negativo sale donde tiene que salir (**−0,0612 [−0,1093, −0,0110]**).

La contrapartida no se negocia: **solo pueden reordenar candidatos que YA vienen de los casos recuperados.** Un
alimento que el consenso no propuso no puede entrar en la dieta porque el cliente lo haya escrito en una casilla del
cuestionario — eso no sería reproducir al profesional, sería tomar una decisión nutricional que nadie ha validado.

Tres comprobaciones:

  1. **la afirmación fuerte**: la propuesta con gustos ⊆ la propuesta sin gustos, alimento a alimento;
  2. **el guarda puede fallar**: se declara como gusto un alimento que NO está en ningún caso y se comprueba que no
     aparece. Sin esta, la 1 se cumpliría sola aunque el desempate estuviera mal escrito;
  3. **el desempate hace algo**: con dos candidatos empatados, gana el que está en los gustos. Si no cambiara nada,
     la 1 y la 2 pasarían por vacío y este fichero no probaría nada.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.composition_policy import CompositionParams, compose_meals  # noqa: E402
from finalprosports.domain.model import (Diet, DietItem, Food, FoodGroup, Meal, MealSlot, Quantity,  # noqa: E402
                                         RetrievedCase, SimilarityScore, Unit)

AVENA, PLATANO, KIWI, INTRUSO = 1, 2, 3, 99
CATALOG = {
    AVENA: Food(AVENA, "avena", "cereal", FoodGroup.CARB, None, (), (), 100, "x"),
    PLATANO: Food(PLATANO, "platano", "fruta", FoodGroup.FRUIT, None, (), (), 100, "x"),
    KIWI: Food(KIWI, "kiwi", "fruta", FoodGroup.FRUIT, None, (), (), 100, "x"),
    INTRUSO: Food(INTRUSO, "salmon ahumado", "pescado", FoodGroup.PROTEIN, None, (), (), 100, "x"),
}
PARAMS = CompositionParams(k=4, inclusion_threshold=0.3)


def _item(food_id: int, name: str) -> DietItem:
    return DietItem(meal_slot=MealSlot.BREAKFAST, position=0, component_index=0, food_id=food_id,
                    canonical_name=name, normalized_key=name, raw_text=f"50 gr {name}",
                    quantity=Quantity(50.0, Unit.GRAM, "gr"))


def _case(diet_id: str, food_ids: list[int]) -> RetrievedCase:
    items = tuple(_item(f, CATALOG[f].canonical_name) for f in food_ids)
    diet = Diet(id=diet_id, professional_id="p", client_code=diet_id.split("::")[0], goal=None,
                meals=(Meal(MealSlot.BREAKFAST, items),), notes=())
    return RetrievedCase(diet=diet, score=SimilarityScore(0.0, 0.9, 0.9), rank=1, case_profile=None)


# Cuatro casos: avena en todos, plátano y kiwi en dos cada uno -> plátano y kiwi EMPATAN en soporte.
CASES = (_case("C1::v01", [AVENA, PLATANO]), _case("C2::v01", [AVENA, PLATANO]),
         _case("C3::v01", [AVENA, KIWI]), _case("C4::v01", [AVENA, KIWI]))


def _foods(meals) -> list[int]:
    return [o.item.food_id for m in meals for g in m.groups for o in g.options]


def test_likes_can_only_reorder_what_the_cases_already_proposed():
    sin = set(_foods(compose_meals(CASES, PARAMS, CATALOG)))
    con = set(_foods(compose_meals(CASES, PARAMS, CATALOG, liked=frozenset({KIWI, INTRUSO}))))
    assert con <= sin, f"los gustos introdujeron alimentos que el consenso no propuso: {sorted(con - sin)}"


def test_a_liked_food_absent_from_every_case_never_appears():
    """El guarda que puede fallar: `INTRUSO` no está en ningún caso y se declara como gusto."""
    con = _foods(compose_meals(CASES, PARAMS, CATALOG, liked=frozenset({INTRUSO})))
    assert INTRUSO not in con, "un gusto metió en la dieta un alimento que ningún caso recuperado contiene"
    assert con, "la composición salió vacía: el montaje no está probando nada"


def test_the_tie_break_actually_does_something():
    """Sin esto, los dos tests de arriba pasarían por vacío aunque el desempate estuviera mal escrito."""
    orden_sin = _foods(compose_meals(CASES, PARAMS, CATALOG))
    orden_kiwi = _foods(compose_meals(CASES, PARAMS, CATALOG, liked=frozenset({KIWI})))
    orden_platano = _foods(compose_meals(CASES, PARAMS, CATALOG, liked=frozenset({PLATANO})))
    assert set(orden_sin) == set(orden_kiwi) == set(orden_platano), "el desempate cambió el CONJUNTO, no solo el orden"
    assert orden_kiwi != orden_platano, (
        "declarar kiwi o plátano como gusto da exactamente el mismo orden: el desempate no está haciendo nada, "
        f"y entonces las otras dos comprobaciones no prueban nada ({orden_kiwi})")
    assert orden_kiwi.index(KIWI) < orden_kiwi.index(PLATANO), orden_kiwi
    assert orden_platano.index(PLATANO) < orden_platano.index(KIWI), orden_platano


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    print(f"OK: {failed} failing")
    sys.exit(1 if failed else 0)
