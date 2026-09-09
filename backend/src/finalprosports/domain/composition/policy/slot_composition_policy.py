"""Which food groups a slot must contain in the professional's style (cena: proteína + verdura (+ grasa); desayuno: cereal)."""
from finalprosports.domain.model import FoodGroup, MealSlot

REQUIRED_GROUPS: dict[MealSlot, frozenset[FoodGroup]] = {
    MealSlot.DINNER: frozenset({FoodGroup.PROTEIN, FoodGroup.VEGETABLE}),
    MealSlot.LUNCH: frozenset({FoodGroup.PROTEIN}),
    MealSlot.BREAKFAST: frozenset({FoodGroup.CARB}),
}


def missing_groups(slot: MealSlot, present: set[FoodGroup]) -> frozenset[FoodGroup]:
    return REQUIRED_GROUPS.get(slot, frozenset()) - present
