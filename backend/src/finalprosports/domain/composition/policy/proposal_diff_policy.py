"""ProposalDiffPolicy (S5): how much did the professional correct what the system proposed?

When a diet is saved, the ORIGINAL proposal (as the engine returned it) and the EDITED one (as the professional left it) are compared
food by food, slot by slot, note by note. The result is traceability of the professional's criterion — what he adds, removes, moves or
re-quantifies — and evaluation material: the edit ratio is the share of proposed items he did not keep as they were. Pure function.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from finalprosports.domain.model import DietProposal, MealSlot, ProposedItem


@dataclass(frozen=True)
class ItemChange:
    slot: str
    food_id: int | None
    canonical_name: str | None
    change: str                       # added | removed | quantity | unit | moved
    before: str | None = None
    after: str | None = None


@dataclass(frozen=True)
class ProposalDiff:
    items_added: tuple[ItemChange, ...] = ()
    items_removed: tuple[ItemChange, ...] = ()
    items_changed: tuple[ItemChange, ...] = ()        # quantity / unit changes of a food kept in its slot
    items_moved: tuple[ItemChange, ...] = ()          # same food, different slot
    slots_added: tuple[str, ...] = ()
    slots_removed: tuple[str, ...] = ()
    notes_added: tuple[str, ...] = ()
    notes_removed: tuple[str, ...] = ()
    proposed_items: int = 0
    kept_unchanged: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def edit_ratio(self) -> float:
        """Share of the proposed items the professional did NOT keep as proposed (removed, moved or re-quantified)."""
        return round(1 - self.kept_unchanged / self.proposed_items, 3) if self.proposed_items else 0.0

    @property
    def is_edited(self) -> bool:
        return bool(self.items_added or self.items_removed or self.items_changed or self.items_moved or self.notes_added or self.notes_removed)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["edit_ratio"], d["is_edited"] = self.edit_ratio, self.is_edited
        d["summary"] = {"added": len(self.items_added), "removed": len(self.items_removed), "changed": len(self.items_changed), "moved": len(self.items_moved),
                        "notes_added": len(self.notes_added), "notes_removed": len(self.notes_removed), "slots_added": len(self.slots_added), "slots_removed": len(self.slots_removed)}
        return d


def _index(p: DietProposal) -> dict[tuple[str, int], ProposedItem]:
    out: dict[tuple[str, int], ProposedItem] = {}
    for m in p.meals:
        for o in m.items:
            if o.item.food_id is not None:
                out.setdefault((m.slot.value, o.item.food_id), o)
    return out


def _qty(o: ProposedItem) -> str:
    q = o.item.quantity
    return f"{q.value:g} {q.unit.value}".strip() if q.value is not None else "—"


def diff_proposals(original: DietProposal, edited: DietProposal) -> ProposalDiff:
    a, b = _index(original), _index(edited)
    slots_a, slots_b = {m.slot.value for m in original.meals}, {m.slot.value for m in edited.meals}
    foods_a = {f for (_, f) in a}
    foods_b = {f for (_, f) in b}
    added, removed, changed, moved = [], [], [], []
    kept = 0
    for key, o in a.items():
        slot, fid = key
        if key in b:
            e = b[key]
            if o.item.quantity.value != e.item.quantity.value or o.item.quantity.unit != e.item.quantity.unit:
                kind = "unit" if o.item.quantity.unit != e.item.quantity.unit else "quantity"
                changed.append(ItemChange(slot, fid, e.item.canonical_name or o.item.canonical_name, kind, _qty(o), _qty(e)))
            else:
                kept += 1
        elif fid in foods_b:
            new_slot = next(s for (s, f) in b if f == fid)
            moved.append(ItemChange(new_slot, fid, o.item.canonical_name, "moved", slot, new_slot))
        else:
            removed.append(ItemChange(slot, fid, o.item.canonical_name, "removed", _qty(o), None))
    for key, e in b.items():
        slot, fid = key
        if key not in a and fid not in foods_a:
            added.append(ItemChange(slot, fid, e.item.canonical_name, "added", None, _qty(e)))
    notes_a, notes_b = [n.strip() for n in original.notes], [n.strip() for n in edited.notes]
    order = list(MealSlot)
    return ProposalDiff(tuple(added), tuple(removed), tuple(changed), tuple(moved),
                        tuple(sorted(slots_b - slots_a, key=lambda s: order.index(MealSlot(s)) if s in MealSlot.__members__.values() or s in {x.value for x in MealSlot} else 99)),
                        tuple(sorted(slots_a - slots_b, key=lambda s: order.index(MealSlot(s)) if s in {x.value for x in MealSlot} else 99)),
                        tuple(n for n in notes_b if n not in notes_a), tuple(n for n in notes_a if n not in notes_b), len(a), kept)
