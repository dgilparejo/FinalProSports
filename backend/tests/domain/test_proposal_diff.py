# -*- coding: utf-8 -*-
"""Domain tests (S5): the diff between the engine's proposal and what the professional saved — added, removed, re-quantified, moved items,
slots and notes — and the edit ratio (share of proposed items not kept as proposed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.proposal_diff_policy import diff_proposals  # noqa: E402
from finalprosports.domain.model import AlternativeGroup, ClientProfile, DietItem, DietProposal, Goal, ItemEvidence, MealSlot, ProposedItem, ProposedMeal, Quantity, Unit  # noqa: E402

P = ClientProfile("X", "p", "M", 30, 178, 4, goal=Goal.VOLUME)
NAMES = {1: "pollo", 2: "arroz", 3: "brócoli", 4: "avena", 5: "salmón"}


def it(slot, pos, fid, qty=100.0, unit=Unit.GRAM):
    return ProposedItem(DietItem(slot, pos, 0, fid, NAMES[fid], NAMES[fid], NAMES[fid], Quantity(qty, unit)), ItemEvidence(("C::v01",), 0.8))


def meal(slot, *items):
    return ProposedMeal(slot, tuple(AlternativeGroup(i, (x,)) for i, x in enumerate(items)))


def proposal(meals, notes=("beber agua",)):
    return DietProposal(P, tuple(meals), tuple(notes), ("C::v01",), "case_based_composer")


ORIGINAL = proposal([meal(MealSlot.LUNCH, it(MealSlot.LUNCH, 0, 1, 200), it(MealSlot.LUNCH, 1, 2, 150), it(MealSlot.LUNCH, 2, 3, 100)),
                     meal(MealSlot.DINNER, it(MealSlot.DINNER, 0, 5, 180))])


def test_unchanged_proposal_has_no_edits():
    d = diff_proposals(ORIGINAL, ORIGINAL)
    assert not d.is_edited and d.edit_ratio == 0.0 and d.proposed_items == 4 and d.kept_unchanged == 4


def test_added_removed_changed_moved_slots_and_notes():
    edited = proposal([meal(MealSlot.LUNCH, it(MealSlot.LUNCH, 0, 1, 180), it(MealSlot.LUNCH, 1, 4, 60)),        # pollo 200 -> 180; arroz removed; avena added; brócoli moved to dinner
                       meal(MealSlot.DINNER, it(MealSlot.DINNER, 0, 5, 180), it(MealSlot.DINNER, 1, 3, 100)),
                       meal(MealSlot.BREAKFAST, it(MealSlot.BREAKFAST, 0, 4, 50))],                                # new slot (avena also here: added once per slot)
                      notes=("beber agua", "masticar despacio"))
    d = diff_proposals(ORIGINAL, edited)
    assert [(c.change, c.canonical_name, c.slot) for c in d.items_changed] == [("quantity", "pollo", "COMIDA")] and d.items_changed[0].before == "200 g" and d.items_changed[0].after == "180 g"
    assert [(c.canonical_name, c.slot) for c in d.items_removed] == [("arroz", "COMIDA")]
    assert sorted((c.canonical_name, c.slot) for c in d.items_added) == [("avena", "COMIDA"), ("avena", "DESAYUNO")]
    assert [(c.canonical_name, c.before, c.after) for c in d.items_moved] == [("brócoli", "COMIDA", "CENA")]
    assert d.slots_added == ("DESAYUNO",) and d.slots_removed == ()
    assert d.notes_added == ("masticar despacio",) and d.notes_removed == ()
    assert d.kept_unchanged == 1 and d.proposed_items == 4 and d.edit_ratio == 0.75 and d.is_edited
    s = d.as_dict()["summary"]
    assert s == {"added": 2, "removed": 1, "changed": 1, "moved": 1, "notes_added": 1, "notes_removed": 0, "slots_added": 1, "slots_removed": 0}


def test_unit_change_is_reported_as_unit():
    edited = proposal([meal(MealSlot.LUNCH, it(MealSlot.LUNCH, 0, 1, 2, Unit.PIECE), it(MealSlot.LUNCH, 1, 2, 150), it(MealSlot.LUNCH, 2, 3, 100)), meal(MealSlot.DINNER, it(MealSlot.DINNER, 0, 5, 180))])
    d = diff_proposals(ORIGINAL, edited)
    assert [c.change for c in d.items_changed] == ["unit"] and d.edit_ratio == 0.25


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
