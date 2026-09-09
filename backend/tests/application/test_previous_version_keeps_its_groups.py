# -*- coding: utf-8 -*-
"""Al leer la versión ANTERIOR de un cliente, sus grupos de alternativas se conservan.

Por qué merece un test propio: el e2e decide qué violación de plausibilidad ha INTRODUCIDO el sistema y cuál ya estaba
en la dieta que él escribió, y para eso reconstruye su versión anterior como si fuera una propuesta. Esa
reconstrucción metía cada ítem en un grupo de uno, y un grupo de uno no mezcla nada: el chequeo
`alternative_groups_mixed` no podía dispararse NUNCA sobre lo suyo, así que el e2e le atribuía al sistema una conducta
del profesional. Medido sobre el cliente del e2e: la propuesta mezcla macrogrupo en 11 de 14 grupos (0,79) y sus dos
versiones anteriores mezclan en 11 de 13 (0,85) — él mezcla MÁS.

El test no necesita base de datos ni corpus: construye dos comidas a mano y comprueba lo único que importa, que dos
ítems con el mismo `alternative_group` acaban en el MISMO grupo y que los que no tienen grupo siguen sueltos.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "e2e"))

from evaluate_real_client import as_proposal  # noqa: E402
from finalprosports.domain.model import ClientProfile, Diet, DietItem, Goal, Meal, MealSlot, Quantity, Unit  # noqa: E402

PERFIL = ClientProfile(client_code="X", professional_id="p", sex="M", age=30, height_cm=180,
                       activity_level=4, goal=Goal.VOLUME, restrictions=())


def item(slot: MealSlot, i: int, food_id: int, grupo: str | None) -> DietItem:
    return DietItem(meal_slot=slot, position=0, component_index=i, food_id=food_id,
                    canonical_name=f"alimento_{food_id}", normalized_key=f"k{food_id}",
                    raw_text=f"100 g de alimento_{food_id}", quantity=Quantity(100.0, Unit.GRAM),
                    alternative_group=grupo)


def diet_de_prueba() -> Diet:
    cena = Meal(slot=MealSlot.DINNER, items=(
        item(MealSlot.DINNER, 0, 1, "g1"), item(MealSlot.DINNER, 1, 2, "g1"), item(MealSlot.DINNER, 2, 3, "g1"),
        item(MealSlot.DINNER, 3, 4, None),
    ))
    comida = Meal(slot=MealSlot.LUNCH, items=(
        item(MealSlot.LUNCH, 0, 5, "g2"), item(MealSlot.LUNCH, 1, 6, "g2"),
        item(MealSlot.LUNCH, 2, 7, None), item(MealSlot.LUNCH, 3, 8, None),
    ))
    return Diet(id="X::v01", professional_id="p", client_code="X", goal=Goal.VOLUME, meals=(cena, comida),
                notes=(), diet_version=1)


def test_items_sharing_a_group_end_up_in_one_group():
    prop = as_proposal(diet_de_prueba(), PERFIL)
    cena = next(m for m in prop.meals if m.slot is MealSlot.DINNER)
    tamanos = sorted(len(g.options) for g in cena.groups)
    assert tamanos == [1, 3], f"la cena debería ser un grupo de tres y uno de uno, y es {tamanos}"
    grande = next(g for g in cena.groups if len(g.options) == 3)
    assert {o.item.food_id for o in grande.options} == {1, 2, 3}


def test_items_without_a_group_stay_on_their_own():
    prop = as_proposal(diet_de_prueba(), PERFIL)
    comida = next(m for m in prop.meals if m.slot is MealSlot.LUNCH)
    tamanos = sorted(len(g.options) for g in comida.groups)
    assert tamanos == [1, 1, 2], f"la comida debería ser un grupo de dos y dos de uno, y es {tamanos}"


def test_nothing_is_lost_and_the_slots_survive():
    diet = diet_de_prueba()
    prop = as_proposal(diet, PERFIL)
    antes = sum(len(m.items) for m in diet.meals)
    despues = sum(len(g.options) for m in prop.meals for g in m.groups)
    assert antes == despues == 8, (antes, despues)
    assert {m.slot for m in prop.meals} == {MealSlot.DINNER, MealSlot.LUNCH}


def test_the_flattened_reconstruction_would_not_have_caught_it():
    """La prueba de que el defecto era real: aplanando, ningún grupo tiene más de un elemento y `mixed` nunca salta."""
    prop = as_proposal(diet_de_prueba(), PERFIL)
    multi = [g for m in prop.meals for g in m.groups if len(g.options) > 1]
    assert multi, "sin grupos de más de un elemento, el chequeo de macrogrupo mezclado es inaplicable"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
