from dataclasses import dataclass

from .meal_slot import MealSlot
from .quantity import Quantity


@dataclass(frozen=True)
class DietItem:
    """One food component of a meal. `food_id` is None when the component is not in the catalogue."""

    meal_slot: MealSlot
    position: int
    component_index: int
    food_id: int | None
    canonical_name: str | None
    normalized_key: str
    raw_text: str
    quantity: Quantity
    alternative_group: str | None = None
    compound_group: str | None = None
    generic_assumption: bool = False
    note: str | None = None
    inherited: bool = False
    """This component comes verbatim from the client's PREVIOUS version: the professional wrote it, for this person.

    The invariant it protects: **a value the professional wrote for this client is never overwritten with a statistic of the
    corpus.** The plausibility envelope exists to bound what the system INVENTS, not to correct what it INHERITS. He wrote
    «2 hamburguesas de pollo (290 gr aprox.)»; the envelope had no band for (hamburguesa, unidad) — six observations, below
    its n >= 10 — so the unit-substitution branch replaced his prescription with 160 g, the median of a different role
    («190 gr Pescado Blanco a elegir / 160 gr Hamburguesa» is the burger as an alternative to fish, not as the main protein).
    That the 160 g sits inside his band is irrelevant: the band is not the criterion when there is a value of his."""

    display_name: str | None = None
    """How this component is WRITTEN, when the professional's own wording is more specific than the catalogue's canonical.

    The catalogue collapses «Arroz vaporizado», «Arroz integral» and «Arroz blanco» into one canonical `arroz`, so the
    composer cannot express a distinction he makes in 75,8 % of the times he writes rice. The distinction survives in
    `normalized_key`, which the composer already consensuses across the retrieved cases; this field carries it to the
    document. It is presentation only: `food_id` and `canonical_name` do not change, so the rule engine, the metrics and
    every published figure keep seeing exactly what they saw."""

    @property
    def is_mapped(self) -> bool:
        return self.food_id is not None
