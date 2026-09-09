# -*- coding: utf-8 -*-
"""LOS SUPLEMENTOS VAN DONDE HAY QUE TOMARLOS, y la política no puede inventar nada por el camino.

El sistema los ponía en un bloque «SUPLEMENTOS» al final y el cliente leía una lista sin saber cuándo tomarse cada
cosa. Ahora se colocan en la franja correspondiente: primero según lo que hacen los casos recuperados de ese cliente
—con consenso, no por un voto de diferencia—, después según la tabla minada del corpus, y lo que ninguno de los dos
sepa colocar se queda en el bloque.

Lo que este fichero fija, y qué se rompería si dejara de cumplirse:

  1. el suplemento sale del bloque y aparece en su franja          -> el cambio no estaría hecho;
  2. **no se añade, no se quita y no cambia la cantidad**          -> la política estaría inventando dieta;
  3. va AL FINAL de la franja                                      -> el documento leería «1 Omega 3, 250 gr Pescado»;
  4. un voto de 2-1 NO decide: manda el respaldo del corpus        -> ruido con forma de mayoría (caso real: el potasio);
  5. lo que nadie sabe colocar se queda en el bloque               -> se inventaría una franja;
  6. un destino que la propuesta no tiene NO se crea               -> se fabricaría una comida para colgar una cápsula.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.supplement_placement_policy import place  # noqa: E402
from finalprosports.domain.model import (AlternativeGroup, Diet, DietItem, Food, FoodFlags, FoodGroup,  # noqa: E402
                                         ItemEvidence, Meal, MealSlot, ProposedItem, ProposedMeal, Quantity,
                                         RetrievedCase, SimilarityScore, Unit)

POLLO, OMEGA, POTASIO, CALCIO = 1, 2, 3, 4
def _food(fid, nombre, grupo):
    # Por NOMBRE y no por posicion: `Food` es (id, canonical_name, GROUP, FAMILY, ...) y ponerlos al reves dejaba
    # todos los suplementos con `group="suplemento"` en vez de FoodGroup.SUPPLEMENT, asi que la politica no veia
    # ninguno y los cinco tests fallaban por el montaje, no por el codigo.
    return Food(id=fid, canonical_name=nombre, group=grupo, family="x", secondary_group=None,
                flags=FoodFlags(), synonyms=())


CATALOG = {
    POLLO: _food(POLLO, "pollo", FoodGroup.PROTEIN),
    OMEGA: _food(OMEGA, "omega 3", FoodGroup.SUPPLEMENT),
    POTASIO: _food(POTASIO, "potasio", FoodGroup.SUPPLEMENT),
    CALCIO: _food(CALCIO, "calcio", FoodGroup.SUPPLEMENT),
}
VACIA = ItemEvidence(case_ids=(), support=0.0, rules=())


def _item(fid, slot, qty=1.0, unit=Unit.PIECE):
    return DietItem(meal_slot=slot, position=0, component_index=0, food_id=fid,
                    canonical_name=CATALOG[fid].canonical_name, normalized_key=CATALOG[fid].canonical_name,
                    raw_text=CATALOG[fid].canonical_name, quantity=Quantity(qty, unit))


def _meal(slot, fids):
    return ProposedMeal(slot=slot, groups=tuple(
        AlternativeGroup(i, (ProposedItem(_item(f, slot), VACIA),)) for i, f in enumerate(fids)))


def _case(diet_id, por_franja):
    meals = tuple(Meal(slot, tuple(_item(f, slot) for f in fids)) for slot, fids in por_franja.items())
    diet = Diet(id=diet_id, professional_id="p", client_code=diet_id.split("::")[0], goal=None, meals=meals, notes=())
    return RetrievedCase(diet=diet, score=SimilarityScore(0.0, 0.9, 0.9), rank=1, case_profile=None)


def _foods(meals):
    return {m.slot: [o.item.food_id for g in m.groups for o in g.options] for m in meals}


PROPUESTA = [_meal(MealSlot.LUNCH, [POLLO]), _meal(MealSlot.DINNER, [POLLO]),
             _meal(MealSlot.SUPPLEMENTS, [OMEGA, POTASIO, CALCIO])]
# Tres casos ponen omega 3 en la cena: 3-0, consenso claro.
CASOS = [_case(f"C{i}::v01", {MealSlot.DINNER: [POLLO, OMEGA]}) for i in range(1, 4)]


def test_the_supplement_leaves_the_block_and_lands_in_its_slot():
    salida = place(list(PROPUESTA), CASOS, CATALOG, {})
    por_franja = _foods(salida)
    assert OMEGA in por_franja[MealSlot.DINNER], por_franja
    assert OMEGA not in por_franja.get(MealSlot.SUPPLEMENTS, [])


def test_nothing_is_added_removed_or_requantified():
    """La afirmación fuerte: el multiconjunto de (alimento, cantidad, unidad) es EXACTAMENTE el mismo."""
    def firma(meals):
        return sorted((o.item.food_id, o.item.quantity.value, o.item.quantity.unit)
                      for m in meals for g in m.groups for o in g.options)
    salida = place(list(PROPUESTA), CASOS, CATALOG, {CALCIO: "CENA", POTASIO: "CENA"})
    assert firma(salida) == firma(PROPUESTA)


def test_the_supplement_goes_last_in_its_slot():
    salida = place(list(PROPUESTA), CASOS, CATALOG, {})
    cena = next(m for m in salida if m.slot is MealSlot.DINNER)
    ids = [o.item.food_id for g in cena.groups for o in g.options]
    assert ids[-1] == OMEGA and ids[0] == POLLO, ids
    assert [g.position for g in cena.groups] == list(range(len(cena.groups))), "las posiciones no se renumeraron"


def test_a_two_to_one_vote_does_not_decide_and_the_corpus_wins():
    """El caso real que puso el suelo: el potasio salía a «recién levantado» por 2-1 sobre veinte casos."""
    casos = [_case("A::v01", {MealSlot.ON_WAKING: [POTASIO]}), _case("B::v01", {MealSlot.ON_WAKING: [POTASIO]}),
             _case("C::v01", {MealSlot.LUNCH: [POTASIO]})]
    salida = place(list(PROPUESTA), casos, CATALOG, {POTASIO: "CENA"})
    por_franja = _foods(salida)
    assert POTASIO in por_franja[MealSlot.DINNER], ("un 2-1 no es consenso: tenía que mandar el corpus", por_franja)
    assert POTASIO not in por_franja.get(MealSlot.ON_WAKING, [])
    # ...y con un margen de DOS votos (4-2) sí manda el consenso de los casos, o el suelo estaría bloqueándolo todo
    # y la vía principal no serviría para nada. El corte es el margen, no el número: 3-2 tampoco decide.
    casos_claros = casos + [_case(f"{c}::v01", {MealSlot.LUNCH: [POTASIO]}) for c in ("D", "E", "F")]
    salida2 = place([_meal(MealSlot.LUNCH, [POLLO]), _meal(MealSlot.DINNER, [POLLO]),
                     _meal(MealSlot.SUPPLEMENTS, [POTASIO])], casos_claros, CATALOG, {POTASIO: "CENA"})
    assert POTASIO in _foods(salida2)[MealSlot.LUNCH], "con 4-2 a favor de la comida tenían que mandar los casos"


def test_what_nobody_knows_how_to_place_stays_in_the_block():
    salida = place(list(PROPUESTA), CASOS, CATALOG, {})       # calcio y potasio: ni casos ni respaldo
    bloque = next(m for m in salida if m.slot is MealSlot.SUPPLEMENTS)
    quedan = [o.item.food_id for g in bloque.groups for o in g.options]
    assert sorted(quedan) == sorted([POTASIO, CALCIO]), quedan


def test_a_destination_the_proposal_does_not_have_is_never_created():
    """Crear una franja solo para colgar de ella una cápsula sería fabricar estructura que el consenso no respalda."""
    sin_cena = [_meal(MealSlot.LUNCH, [POLLO]), _meal(MealSlot.SUPPLEMENTS, [OMEGA])]
    salida = place(list(sin_cena), CASOS, CATALOG, {})        # los casos mandan omega 3 a la CENA, que no existe
    assert MealSlot.DINNER not in {m.slot for m in salida}, "se inventó la cena"
    bloque = next(m for m in salida if m.slot is MealSlot.SUPPLEMENTS)
    assert [o.item.food_id for g in bloque.groups for o in g.options] == [OMEGA]


def test_the_block_disappears_when_it_empties():
    salida = place(list(PROPUESTA), CASOS, CATALOG, {POTASIO: "CENA", CALCIO: "CENA"})
    assert MealSlot.SUPPLEMENTS not in {m.slot for m in salida}, "el bloque vacío tenía que desaparecer"
    assert sorted(_foods(salida)[MealSlot.DINNER]) == sorted([POLLO, OMEGA, POTASIO, CALCIO])


def test_a_proposal_without_a_block_is_returned_untouched():
    sin_bloque = [_meal(MealSlot.LUNCH, [POLLO])]
    assert place(list(sin_bloque), CASOS, CATALOG, {}) == sin_bloque


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    print(f"OK: {failed} failing")
    sys.exit(1 if failed else 0)
