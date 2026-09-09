"""AddFoodUseCase (S5): the professional registers a food the catalogue does not have.

The 14 flags are MANDATORY at the boundary: without allergen flags the validator cannot protect a client from it, and without the rule
flags (processed sugar, soft drink, salt, fasting-compatible, alcohol, stimulant) the constitution cannot be evaluated on it. The food is
stamped ``created_by_professional`` so that the evaluation can tell the mined catalogue (220 canonicals) from the hand-added one. The
in-memory catalogue shared by the composer, the rotation policy, the validator and the matcher is updated in place: the new food is
usable in the very next proposal."""
from __future__ import annotations

from finalprosports.application.exception.catalog.food_already_exists_error import FoodAlreadyExistsError
from finalprosports.application.port.outbound.persistence.catalog.food_catalog_output_port import FoodCatalogOutputPort
from finalprosports.application.service.catalog.food_matcher import FoodMatcher, normalise
from finalprosports.domain.model import Food, FoodFlags, FoodGroup


class AddFoodUseCase:
    def __init__(self, repository: FoodCatalogOutputPort, catalog: dict[int, Food], matcher: FoodMatcher | None = None):
        self._repo, self._catalog, self._matcher = repository, catalog, matcher

    def add(self, professional_id: str, canonical_name: str, family: str, group: FoodGroup, flags: FoodFlags, secondary_group: FoodGroup | None = None,
            synonyms: tuple[str, ...] = ()) -> Food:
        name = " ".join(canonical_name.strip().lower().split())
        if not name or not family.strip():
            raise ValueError("canonical_name and family are required")
        key = normalise(name)
        for f in self._catalog.values():
            if normalise(f.canonical_name) == key or any(normalise(s) == key for s in f.synonyms):
                raise FoodAlreadyExistsError(name, f.id)
        food = Food(id=max(self._catalog, default=0) + 1, canonical_name=name, group=group, family=family.strip().lower(), secondary_group=secondary_group, flags=flags,
                    synonyms=tuple(" ".join(s.strip().lower().split()) for s in synonyms if s.strip()), frequency=0, created_by_professional=True)
        saved = self._repo.add(professional_id, food)
        self._catalog[saved.id] = saved                                     # the same dict the composer / validator / rotation hold
        if self._matcher is not None:
            self._matcher.add(saved)
        return saved
