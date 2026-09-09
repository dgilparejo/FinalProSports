from dataclasses import dataclass
from enum import StrEnum


class RestrictionKind(StrEnum):
    """Structured restriction; each value is the FoodFlags attribute that vetoes a food."""

    LACTOSE = "contains_lactose"
    GLUTEN = "contains_gluten"
    SOY = "contains_soy"
    SHELLFISH = "contains_shellfish"
    EGG = "contains_egg"
    FISH = "contains_fish"
    PEANUT = "is_peanut"
    TREE_NUT = "is_tree_nut"
    ALCOHOL = "is_alcohol"
    STIMULANT = "is_stimulant"


class RestrictionMode(StrEnum):
    """How declared restrictions are applied (constitution rule section 8, `no_restringe_lacteos_intolerantes`):
    STRICT vetoes every food carrying the flag; PROFESSIONAL reproduces the professional's observed behaviour, which does
    not restrict fermented dairy / whey derivatives to lactose-intolerant clients (lactose becomes a warning, not a veto).
    Both are measured in the evaluation; the mode is selected by configuration."""

    STRICT = "restriccion_estricta"
    PROFESSIONAL = "reproducir_criterio_profesional"


@dataclass(frozen=True)
class Restriction:
    kind: RestrictionKind
    strict: bool = True        # strict: veto the food; not strict: reproduce the professional's behaviour (see rule section 8)
    source: str = "profile"
