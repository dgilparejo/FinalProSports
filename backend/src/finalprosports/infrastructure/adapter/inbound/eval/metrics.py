"""Overlap metrics reported as floor / system / ceiling + normalised score (see NORMALIZATION_REPORT §7)."""
from dataclasses import dataclass


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


@dataclass(frozen=True)
class Triplet:
    floor: float
    system: float
    ceiling: float

    @property
    def normalised(self) -> float | None:
        return None if self.ceiling == self.floor else (self.system - self.floor) / (self.ceiling - self.floor)


def per_slot_jaccard(q_slots: dict[str, set], o_slots: dict[str, set]) -> float:
    if not q_slots:
        return 0.0
    return sum(jaccard(q_slots[s], o_slots.get(s, set())) for s in q_slots) / len(q_slots)
