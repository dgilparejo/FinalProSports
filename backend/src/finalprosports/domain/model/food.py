from dataclasses import dataclass, field

from .food_group import FoodGroup


@dataclass(frozen=True)
class FoodFlags:
    """Boolean attributes that make the rule constitution and the profile restrictions executable.

    Rule flags:
      is_processed_sugar     sweets, juices, energy gels... (rule "prohibido azúcar / procesados")
      is_soft_drink          flavoured, carbonated or sweetened drinks, sugar-free included (same rule, other clause)
      is_salt                any salt (the rule distinguishes 'sal del himalaya' by canonical name)
      is_fasting_compatible  does not break the fast: water, black coffee, unsweetened tea, herbal infusions
      is_alcohol             beer, wine, spirits
      is_stimulant           caffeine, synephrine and caffeinated products (explainability warning)
    Allergen / intolerance flags (profile restrictions):
      is_peanut, is_tree_nut, contains_lactose, contains_gluten, contains_soy, contains_shellfish,
      contains_egg, contains_fish
    """

    is_processed_sugar: bool = False
    is_soft_drink: bool = False
    is_salt: bool = False
    is_fasting_compatible: bool = False
    is_alcohol: bool = False
    is_stimulant: bool = False
    is_peanut: bool = False
    is_tree_nut: bool = False
    contains_lactose: bool = False
    contains_gluten: bool = False
    contains_soy: bool = False
    contains_shellfish: bool = False
    contains_egg: bool = False
    contains_fish: bool = False


@dataclass(frozen=True)
class Food:
    """Canonical food of the catalogue. ``canonical_name``, ``synonyms`` and ``family`` are Spanish data values.

    ``group`` is the primary nutritional role the trainer's rules reason with; ``secondary_group`` records a
    second role when a food genuinely has two (legumes: CARB + PROTEIN; avocado: FAT + FRUIT; peanuts: FAT + PROTEIN).
    """

    id: int
    canonical_name: str
    group: FoodGroup
    family: str | None = None
    secondary_group: FoodGroup | None = None
    flags: FoodFlags = field(default_factory=FoodFlags)
    synonyms: tuple[str, ...] = ()
    frequency: int = 0
    created_by_professional: bool = False    # S5: added through the application, not mined from the corpus
