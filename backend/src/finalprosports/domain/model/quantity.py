from dataclasses import dataclass
from enum import StrEnum


class Unit(StrEnum):
    """Closed set of measurement units. Values are the Spanish short forms used in the corpus
    (``NONE`` has an empty literal: quantity without a unit or item without quantity)."""

    GRAM = "g"
    MILLILITER = "ml"
    PIECE = "unidad"
    TABLESPOON = "cucharada"
    TEASPOON = "cucharadita"
    CAN = "lata"
    SLICE = "loncha"
    HANDFUL = "puñado"
    CLOVE = "diente"
    DASH = "chorrito"
    SCOOP = "cazo"          # supplement scoop (cazo, scoop, medida)
    CAPSULE = "cápsula"     # one unit of a supplement: cápsula, perla, tableta, pastilla, comprimido
    NONE = ""


@dataclass(frozen=True)
class Quantity:
    """Amount attached to a food. ``value`` is None when the item carries no quantity.
    ``raw_unit`` keeps the unit token found in the text when it does not belong to the closed
    set (e.g. "cazo", "vaso"); such cases are reported, never invented into the enum."""

    value: float | None
    unit: Unit = Unit.NONE
    raw_unit: str | None = None

    @property
    def has_amount(self) -> bool:
        return self.value is not None
