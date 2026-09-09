# -*- coding: utf-8 -*-
"""§3 · La variante especifica tambien en lo que ANADE el validador («Arroz» contra «Arroz integral»).

`name_variants` escribe el componente como el lo escribe cuando su formulacion es mas concreta que el canonico del
catalogo: el catalogo aplana «Arroz integral», «Arroz blanco» y «Arroz vaporizado» en `arroz`, y la variante se
recupera del consenso de los vecinos. Corria como ultimo paso de la capa de plausibilidad, es decir ANTES del
validador -- y el validador ANADE alimentos: al retirar «avena» y «cereales integrales» por gluten, la regla
prescriptiva `desayuno_avena_cereales` mete un hidrato en el desayuno. Ese item nace despues de la capa de nombres,
asi que salia con el canonico pelado mientras los del mismo alimento en otras franjas si llevaban la variante. Era
la ultima violacion real de la dieta del cliente real, y la causa era el ORDEN, no el consenso.

La prueba recorre el caso de uso entero con dobles y comprueba las dos mitades: que el item ANADIDO por el validador
sale con la variante, y que no cambia nada mas de el (`food_id`, canonico y cantidad intactos), que es lo que hace
que la correccion no reabra ninguna cifra publicada.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.application.service.validation.diet_validator import DietValidator  # noqa: E402
from finalprosports.application.strategy.case_based_composer import CaseBasedComposer  # noqa: E402
from finalprosports.application.usecase.proposal.propose_diet_use_case import ProposeDietUseCase  # noqa: E402
from finalprosports.domain.composition.policy.composition_policy import CompositionParams  # noqa: E402
from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope, QuantityRange  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    ClientProfile, Diet, DietItem, Food, FoodFlags, FoodGroup, Goal, Meal, MealSlot, Quantity, Restriction, RestrictionKind,
    RestrictionMode, RetrievedCase, Rule, RuleConfidence, RuleNature, RuleScope, RuleStatus, SimilarityScore, Unit,
)

ARROZ, AVENA, POLLO, VERDURA, GRASA = 2, 21, 40, 41, 42
CATALOG = {
    ARROZ: Food(ARROZ, "arroz", FoodGroup.CARB, "cereal"),
    AVENA: Food(AVENA, "avena", FoodGroup.CARB, "cereal", flags=FoodFlags(contains_gluten=True)),
    POLLO: Food(POLLO, "pollo", FoodGroup.PROTEIN, "ave"),
    VERDURA: Food(VERDURA, "ensalada", FoodGroup.VEGETABLE, "verdura"),
    GRASA: Food(GRASA, "aceite de oliva virgen extra", FoodGroup.FAT, "grasa"),
}
# El vecino escribe el arroz del DESAYUNO en su forma especifica; el catalogo lo aplana en `arroz`.
ENVELOPE = PlausibilityEnvelope(
    quantities={(f, "g"): QuantityRange(f, "g", 20.0, 100.0, 300.0, 40) for f in CATALOG},
    items_per_slot={s: (1.0, 8.0) for s in MealSlot},
    slots_per_diet=(1.0, 10.0),
    food_variants={"arroz integral": "Arroz integral"},
)
RULES = (Rule("desayuno_avena_cereales", "", RuleScope.GLOBAL, RuleStatus.KEPT, "item", (), RuleConfidence.HIGH,
              prevalence=0.86, nature=RuleNature.PRESCRIPTIVE),)


def item(slot, pos, fid, key=None, q=150.0):
    f = CATALOG[fid]
    return DietItem(slot, pos, 0, fid, f.canonical_name, key or f.canonical_name, f.canonical_name, Quantity(q, Unit.GRAM))


def case(rank: int) -> RetrievedCase:
    """El escenario real: el UNICO hidrato del DESAYUNO es avena, que el gluten retira; el arroz vive en COMIDA y
    ahi el lo escribe ESPECIFICO. Asi el hidrato del desayuno solo puede venir de lo que ANADE el validador."""
    desayuno = [item(MealSlot.BREAKFAST, 0, AVENA), item(MealSlot.BREAKFAST, 1, POLLO)]
    if rank <= 4:
        # Cuatro de veinte: por debajo del umbral de franja (0,35), asi que el consenso NO lo compone, pero el
        # validador si lo encuentra como candidato -- que es exactamente como llego el arroz al desayuno real.
        desayuno.append(item(MealSlot.BREAKFAST, 2, ARROZ))
    meals = (Meal(MealSlot.BREAKFAST, tuple(desayuno)),
             Meal(MealSlot.LUNCH, (item(MealSlot.LUNCH, 0, ARROZ, "arroz integral"), item(MealSlot.LUNCH, 1, POLLO),
                                   item(MealSlot.LUNCH, 2, VERDURA), item(MealSlot.LUNCH, 3, GRASA))))
    return RetrievedCase(Diet(f"CASO_{rank}::v01", "p", f"CASO_{rank}", Goal.VOLUME, meals), SimilarityScore(0.0, 1.0, 1.0), rank)


CASES = tuple(case(i) for i in range(1, 21))
PROFILE = ClientProfile("Q", "p", "M", 30, 180, 5, goal=Goal.VOLUME,
                        restrictions=(Restriction(RestrictionKind.GLUTEN, True),))


class _Retrieval:
    def retrieve(self, pid, profile, k, exclude=frozenset()):
        return CASES


class _Rules:
    def all(self, pid):
        return RULES


class _Envelope:
    def load(self, pid):
        return ENVELOPE


def _propose():
    uc = ProposeDietUseCase(_Retrieval(), CaseBasedComposer(CATALOG, CompositionParams(k=20)),
                            DietValidator(CATALOG, RestrictionMode.STRICT, True), _Rules(),
                            envelope=_Envelope(), catalog=CATALOG)
    return uc.propose("p", PROFILE, k=20)


def test_the_food_the_validator_adds_is_written_with_his_variant():
    prop = _propose()
    added = [c for c in prop.validation.forced_changes if c.action == "added"]
    assert added and any(c.food_id == ARROZ for c in added), [str(c) for c in added]   # el escenario es el real: el validador mete el arroz
    desayuno = next(m for m in prop.meals if m.slot is MealSlot.BREAKFAST)
    arroces = [o for g in desayuno.groups for o in g.options if o.item.food_id == ARROZ]
    assert arroces, "el desayuno deberia llevar el hidrato que la regla exige"
    assert all(o.item.display_name == "Arroz integral" for o in arroces), [o.item.display_name for o in arroces]


def test_naming_the_variant_changes_the_printed_name_and_nothing_else():
    """Por que puede aplicarse tras el validador sin reabrir la medicion: no toca lo que leen las metricas."""
    prop = _propose()
    for m in prop.meals:
        for g in m.groups:
            for o in g.options:
                f = CATALOG[o.item.food_id]
                assert o.item.canonical_name == f.canonical_name and o.item.quantity is not None
    desayuno = next(m for m in prop.meals if m.slot is MealSlot.BREAKFAST)
    assert not any(o.item.food_id == AVENA for g in desayuno.groups for o in g.options)   # y el gluten sigue fuera


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
