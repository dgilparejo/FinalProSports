"""Quantity of a proposed item: the median of the quantities of the k retrieved cases for the same food and slot.

Countable units carry a ceiling. A quantity is written by the professional in grams far more often than in pieces, and the
document parser sometimes lands a gram figure on a countable unit: the corpus holds «250 unidades de pavo», «300 unidades de
ternera», «200 unidades de patata». They are gram quantities that lost their unit, and because the composer takes the median
of the (food, unit) pair those values reached the proposals — measured on the delivered configuration, 156 impossible
quantities across the 738 leave-one-out diets, roughly one diet in five. His own diets never do this with a catalogued food.

`sane` is the choke point every composed quantity passes through, so a parse error upstream cannot become a line of a
prescription. It repairs rather than deletes: a count above its ceiling is read back as the gram quantity it was, which is
what the number meant. Only when even that is impossible does the item lose its amount — a food without a quantity is
incomplete, a food with an impossible one is wrong.
"""
from statistics import median

from finalprosports.domain.model import Quantity, Unit

# What a count can plausibly be. Human criterion (physical facts about the unit, not statistics of the corpus: the corpus is
# precisely what carries the error). GRAM and MILLILITER are bounded far above any real portion, only to catch a stray zero.
UNIT_CEILING: dict[Unit, float] = {
    Unit.PIECE: 20,
    Unit.TABLESPOON: 12,
    Unit.TEASPOON: 12,
    Unit.SLICE: 12,
    Unit.CLOVE: 10,
    Unit.HANDFUL: 6,
    Unit.SCOOP: 6,
    Unit.CAPSULE: 12,
    Unit.CAN: 4,
    Unit.DASH: 6,
    Unit.GRAM: 2000,
    Unit.MILLILITER: 3000,
}
COUNTABLE = (Unit.PIECE, Unit.TABLESPOON, Unit.TEASPOON, Unit.SLICE, Unit.CLOVE, Unit.HANDFUL, Unit.SCOOP, Unit.CAPSULE, Unit.CAN, Unit.DASH)
GRAM_FLOOR = 20.0          # below this a stray number is not a gram quantity either, so the amount is dropped instead of invented
GRID = 5.0                 # his rounding grid: 97,0 % of the 20.773 gram quantities in the corpus are multiples of 5
GRID_UNITS = (Unit.GRAM, Unit.MILLILITER)


def is_impossible(q: Quantity) -> bool:
    """A quantity no prescription can carry: more of a countable unit than the unit admits."""
    ceiling = UNIT_CEILING.get(q.unit)
    return q.value is not None and ceiling is not None and q.value > ceiling


def sane(q: Quantity) -> Quantity:
    """The quantity as it can be written. A count above its ceiling is a gram figure that lost its unit and is restored as
    grams; anything still impossible loses its amount rather than being printed wrong."""
    if not is_impossible(q):
        return q
    if q.unit in COUNTABLE and q.value >= GRAM_FLOOR and q.value <= UNIT_CEILING[Unit.GRAM]:
        return Quantity(q.value, Unit.GRAM, raw_unit=q.raw_unit)
    return Quantity(None, Unit.NONE, raw_unit=q.raw_unit)


def on_his_grid(q: Quantity) -> Quantity:
    """Rounded the way he writes it. A median of the k neighbours lands on 186 g or 23 g; he writes 185 and 25. Measured over
    the corpus: 97,0 % of his gram quantities are multiples of 5 (17,2 % of 100, 37,5 % of 20, 16,7 % of 10). Only COMPUTED
    quantities go through this — a quantity carried verbatim from the client's own previous version is his and is left alone."""
    if q.value is None or q.unit not in GRID_UNITS or q.value < GRID:
        return q
    return Quantity(round(q.value / GRID) * GRID, q.unit, raw_unit=q.raw_unit)


def median_quantity(quantities: list[Quantity]) -> Quantity:
    by_unit: dict[Unit, list[float]] = {}
    for q in quantities:
        s = sane(q)                                  # a mis-parsed value must not vote for its wrong unit either
        if s.value is not None:
            by_unit.setdefault(s.unit, []).append(s.value)
    if not by_unit:
        return Quantity(None)
    unit = max(by_unit, key=lambda u: len(by_unit[u]))
    return on_his_grid(sane(Quantity(round(median(by_unit[unit]), 2), unit)))
