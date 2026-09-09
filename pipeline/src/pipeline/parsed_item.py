from dataclasses import dataclass

from finalprosports.domain.model import Quantity


@dataclass(frozen=True)
class ParsedItem:
    """One food component extracted from a free-text meal item.

    A raw item may yield several components: mutually exclusive alternatives
    ("150 gr Pollo / 160 gr Pavo") share an ``alternative_group``; foods eaten together
    ("2 claras y 1 lata de atún") share a ``compound_group``. Instructions without food
    ("NADA DURANTE 1 HORA") yield a single component with ``is_instruction=True`` and
    ``food_text=None``. Group ids embed diet id, meal slot and position, so members of a
    group always belong to the same diet and slot.
    """

    raw_text: str
    food_text: str | None
    quantity: Quantity
    is_instruction: bool = False
    is_noise: bool = False          # layout residue (signature fragments such as `("`, `tel`, `correos/mail`), not content
    alternative_group: str | None = None
    compound_group: str | None = None
    note: str | None = None

    @property
    def compound_item(self) -> bool:
        return self.compound_group is not None

    @property
    def has_alternatives(self) -> bool:
        return self.alternative_group is not None
