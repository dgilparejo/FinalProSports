from dataclasses import dataclass, field

from .goal import Goal
from .meal import Meal
from .meal_slot import MealSlot


@dataclass(frozen=True)
class Diet:
    """A diet as prescribed by the professional (a case) or as composed by the system."""

    id: str                              # CLIENTE_NNN::vNN
    professional_id: str
    client_code: str
    goal: Goal
    meals: tuple[Meal, ...]
    notes: tuple[str, ...] = ()
    goal_inferred: bool = False
    diet_version: int | None = None
    template_group_id: str | None = None
    goal_text: str | None = None
    goals: tuple[str, ...] = field(default_factory=tuple)

    def meal(self, slot: MealSlot) -> Meal | None:
        return next((m for m in self.meals if m.slot == slot), None)

    @property
    def slots(self) -> frozenset[MealSlot]:
        return frozenset(m.slot for m in self.meals)

    @property
    def food_ids(self) -> frozenset[int]:
        return frozenset(f for m in self.meals for f in m.food_ids)
