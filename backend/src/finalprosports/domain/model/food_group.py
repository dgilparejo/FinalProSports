from enum import StrEnum


class FoodGroup(StrEnum):
    """Macro-nutritional role of a food, used to evaluate the trainer's rules
    (e.g. "no carbohydrates at dinner"). Project taxonomy, not corpus data: English literals."""

    PROTEIN = "PROTEIN"
    CARB = "CARB"
    FAT = "FAT"
    VEGETABLE = "VEGETABLE"
    FRUIT = "FRUIT"
    DAIRY = "DAIRY"
    SUPPLEMENT = "SUPPLEMENT"
    BEVERAGE = "BEVERAGE"
    CONDIMENT = "CONDIMENT"
    OTHER = "OTHER"


