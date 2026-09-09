from dataclasses import dataclass

from .diet_item import DietItem
from .meal_slot import MealSlot


@dataclass(frozen=True)
class Meal:
    slot: MealSlot
    items: tuple[DietItem, ...]

    @property
    def food_ids(self) -> frozenset[int]:
        return frozenset(i.food_id for i in self.items if i.food_id is not None)
