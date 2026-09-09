# -*- coding: utf-8 -*-
"""The meal-slot taxonomy: order of the day, printed header, and the five slots dataset-v3 added."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.domain.model import MealSlot  # noqa: E402
from finalprosports.domain.composition.policy.composition_policy import (  # noqa: E402
    NON_COMPOSABLE_SLOTS, SLOT_ORDER, MAIN_SLOTS, CompositionParams, compose_meals)
from finalprosports.domain.composition.policy.document_template_policy import SLOT_LABEL  # noqa: E402

V3_ADDED = ("RECIEN LEVANTADO", "MEDIA TARDE", "ANTES DE DORMIR", "SUPLEMENTOS", "AGUA")


def test_every_slot_has_a_printed_header():
    """A slot the engine can compose into must be printable, or the document silently loses it."""
    missing = [s.value for s in MealSlot if s not in SLOT_LABEL or not SLOT_LABEL[s]]
    assert not missing, missing


def test_slot_order_is_the_order_of_the_day():
    """SLOT_ORDER is tuple(MealSlot), so declaration order IS the printed order."""
    order = [s.value for s in SLOT_ORDER]
    assert order.index("RECIEN LEVANTADO") < order.index("DESAYUNO")
    assert order.index("DESAYUNO") < order.index("MEDIA MAÑANA") < order.index("COMIDA")
    assert order.index("COMIDA") < order.index("MERIENDA") < order.index("MEDIA TARDE") < order.index("CENA")
    assert order.index("CENA") < order.index("RECENA") < order.index("ANTES DE DORMIR")
    assert order.index("ANTES DE ENTRENAR") < order.index("MITAD DE ENTRENAMIENTO") < order.index("DESPUES DE ENTRENAR")
    assert order[-1] == "OTHER", "the generic bucket goes last"


def test_the_five_slots_dataset_v3_added_are_present():
    values = {s.value for s in MealSlot}
    assert set(V3_ADDED) <= values, sorted(set(V3_ADDED) - values)


def test_relative_order_of_the_original_twelve_is_unchanged():
    """Inserting the new slots must not reorder the old ones, or every golden snapshot moves for no reason."""
    original = ["DESAYUNO", "MEDIA MAÑANA", "ALMUERZO", "COMIDA", "MERIENDA", "CENA", "RECENA",
                "ANTES DE ENTRENAR", "MITAD DE ENTRENAMIENTO", "DESPUES DE ENTRENAR", "BATIDO", "OTHER"]
    order = [s.value for s in SLOT_ORDER]
    positions = [order.index(v) for v in original]
    assert positions == sorted(positions), "the original twelve changed relative order"


def test_merienda_prints_as_merienda():
    """Until dataset-v3 the template printed MERIENDA under the label "MEDIA TARDE", because the model had no
    MEDIA TARDE. With both slots real, that relabelling would put the wrong header on a real MERIENDA."""
    assert SLOT_LABEL[MealSlot.SNACK] == "MERIENDA"
    assert SLOT_LABEL[MealSlot.MID_AFTERNOON] == "MEDIA TARDE"
    assert SLOT_LABEL[MealSlot.ON_WAKING].lower().startswith("recién levantado")


def test_meals_a_person_reads_as_meals():
    """MEDIA TARDE is a meal (the repeat penalty applies); water and supplements are intake occasions."""
    assert MealSlot.MID_AFTERNOON in MAIN_SLOTS
    for slot in (MealSlot.WATER, MealSlot.SUPPLEMENTS, MealSlot.ON_WAKING, MealSlot.PRE_WORKOUT):
        assert slot not in MAIN_SLOTS, slot


def test_the_generic_bucket_is_never_composed_into_a_proposal():
    """OTHER holds the header shapes the vocabulary could not map, so its contents are heterogeneous BETWEEN cases.

    Composing consensus over it produced 24 distinct foods in a single slot and one proposal that WAS a single
    OTHER slot. The bucket stays in the data with its raw label; it may not appear in a proposal. Checked against
    cases that have nothing else, so the only slot on offer is the one that must be refused.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Item:
        food_id: int = 1
        canonical_name: str = "avena"
        normalized_key: str = "avena"
        generic_assumption: bool = False

    @dataclass(frozen=True)
    class _Meal:
        slot: MealSlot
        items: tuple

    class _Diet:
        def __init__(self, slot):
            self.meals = (_Meal(slot, (_Item(),)),)

        def meal(self, slot):
            return next((m for m in self.meals if m.slot is slot), None)

    @dataclass(frozen=True)
    class _Case:
        diet: object
        score: float = 1.0

    assert MealSlot.OTHER in NON_COMPOSABLE_SLOTS
    cases = tuple(_Case(_Diet(MealSlot.OTHER)) for _ in range(20))
    meals = compose_meals(cases, CompositionParams(k=20, inclusion_threshold=0.35), catalog={})
    assert [m for m in meals if m.slot is MealSlot.OTHER] == [], "the generic bucket reached a proposal"
    assert meals == [], "nothing but the bucket was on offer, so nothing may be proposed"

if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS  {name}")
        except AssertionError as exc:
            failed += 1; print(f"FAIL  {name}: {exc}")
    print(f"\n{'FAILED' if failed else 'OK'}: {failed} failing")
    sys.exit(1 if failed else 0)
