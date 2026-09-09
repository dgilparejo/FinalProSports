# -*- coding: utf-8 -*-
"""No prescription may carry an impossible quantity.

The corpus holds «250 unidades de pavo», «300 unidades de ternera», «200 unidades de patata»: gram figures that lost their
unit in the document parser. Because the composer takes the median of the (food, unit) pair, they reached the proposals —
156 impossible quantities across the 738 leave-one-out diets before this guard, about one diet in five. His own diets never
do it with a catalogued food.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.quantity_policy import (  # noqa: E402
    GRAM_FLOOR, UNIT_CEILING, is_impossible, median_quantity, sane,
)
from finalprosports.domain.model import Quantity, Unit  # noqa: E402


def test_a_count_above_its_ceiling_is_read_back_as_grams():
    assert sane(Quantity(250, Unit.PIECE)) == Quantity(250, Unit.GRAM)
    assert sane(Quantity(300, Unit.SLICE)) == Quantity(300, Unit.GRAM)


def test_a_real_count_is_untouched():
    for q in (Quantity(2, Unit.PIECE), Quantity(1, Unit.SCOOP), Quantity(3, Unit.TABLESPOON), Quantity(150, Unit.GRAM), Quantity(None)):
        assert sane(q) == q


def test_what_cannot_be_repaired_loses_its_amount_instead_of_being_printed_wrong():
    assert sane(Quantity(GRAM_FLOOR - 1, Unit.SCOOP)).value is None            # too small to be a gram figure
    assert sane(Quantity(UNIT_CEILING[Unit.GRAM] + 1, Unit.PIECE)).value is None   # too large to be anything


def test_a_mis_parsed_value_does_not_vote_for_its_wrong_unit():
    # three real «1 unidad» and two mis-parsed «250 unidad»: the median must be 1 piece, never 250 of anything
    q = median_quantity([Quantity(1, Unit.PIECE)] * 3 + [Quantity(250, Unit.PIECE)] * 2)
    assert q == Quantity(1, Unit.PIECE), q


def test_the_median_itself_is_checked():
    q = median_quantity([Quantity(250, Unit.PIECE), Quantity(280, Unit.PIECE), Quantity(300, Unit.PIECE)])
    assert not is_impossible(q) and q.unit is Unit.GRAM and q.value == 280


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:300]}")
    sys.exit(1 if failed else 0)
