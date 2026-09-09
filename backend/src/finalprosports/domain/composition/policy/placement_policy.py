"""Placement invariants of the professional: carbohydrates in the first half of the day, no fruit at dinner."""
from finalprosports.domain.model import FoodGroup, MealSlot

FIRST_HALF = frozenset({MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.BRUNCH, MealSlot.LUNCH, MealSlot.SNACK})


def allowed_in_slot(group: FoodGroup, slot: MealSlot, goal_allows_dinner_carbs: bool) -> bool:
    if group is FoodGroup.FRUIT and slot is MealSlot.DINNER:
        return False
    if group is FoodGroup.CARB and slot is MealSlot.DINNER:
        return goal_allows_dinner_carbs
    return True
