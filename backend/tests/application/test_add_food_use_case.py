# -*- coding: utf-8 -*-
"""Application tests (S5): a professional-added food gets the next id, the created_by_professional stamp, enters the shared in-memory catalogue
and the matcher at once, and duplicates (by canonical name or synonym) are refused."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.exception.catalog.food_already_exists_error import FoodAlreadyExistsError  # noqa: E402
from finalprosports.application.service.catalog.food_matcher import FoodMatcher  # noqa: E402
from finalprosports.application.service.validation.diet_validator import DietValidator  # noqa: E402
from finalprosports.application.usecase.catalog.add_food_use_case import AddFoodUseCase  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    AlternativeGroup, ClientProfile, DietItem, DietProposal, Food, FoodFlags, FoodGroup, Goal, ItemEvidence, MealSlot, ProposedItem, ProposedMeal, Quantity,
    Restriction, RestrictionKind, Unit,
)


class FakeRepo:
    def __init__(self):
        self.saved = []

    def add(self, pid, food):
        self.saved.append(food)
        return food


def test_add_food_updates_the_shared_catalogue_and_the_matcher():
    catalog = {1: Food(1, "pollo", FoodGroup.PROTEIN, "ave", synonyms=("pechuga",), frequency=10), 7: Food(7, "arroz", FoodGroup.CARB, "arroz", frequency=10)}
    matcher = FoodMatcher(catalog)
    repo = FakeRepo()
    uc = AddFoodUseCase(repo, catalog, matcher)
    food = uc.add("p", "  Tempeh ", "legumbre", FoodGroup.PROTEIN, FoodFlags(contains_soy=True), secondary_group=FoodGroup.CARB, synonyms=("tempe", ""))
    assert food.id == 8 and food.canonical_name == "tempeh" and food.created_by_professional and food.frequency == 0 and food.synonyms == ("tempe",)
    assert catalog[8] is food and repo.saved == [food]
    assert matcher.match("tempe y arroz").food_ids == (8, 7)
    # the validator sees the new food's flags immediately (same dict)
    soy_free = ClientProfile("X", "p", "M", 30, 178, 4, goal=Goal.VOLUME, restrictions=(Restriction(RestrictionKind.SOY),))
    item = ProposedItem(DietItem(MealSlot.LUNCH, 0, 0, 8, "tempeh", "tempeh", "tempeh", Quantity(150, Unit.GRAM)), ItemEvidence((), 0.0))
    out = DietValidator(catalog).validate(DietProposal(soy_free, (ProposedMeal(MealSlot.LUNCH, (AlternativeGroup(0, (item,)),)),), (), (), "edited"), ())
    assert [f.reason for f in out.validation.forced_changes] == ["restriction:contains_soy"]


def test_duplicates_by_name_or_synonym_are_refused_and_fields_are_required():
    catalog = {1: Food(1, "pollo", FoodGroup.PROTEIN, "ave", synonyms=("pechuga de pollo",))}
    uc = AddFoodUseCase(FakeRepo(), catalog)
    for name in ("Pollo", "pechuga de pollo", "POLLO "):
        try:
            uc.add("p", name, "ave", FoodGroup.PROTEIN, FoodFlags()); raise AssertionError(name)
        except FoodAlreadyExistsError as e:
            assert e.existing_id == 1
    try:
        uc.add("p", "  ", "ave", FoodGroup.PROTEIN, FoodFlags()); raise AssertionError("empty name accepted")
    except ValueError:
        pass
    assert len(catalog) == 1


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
