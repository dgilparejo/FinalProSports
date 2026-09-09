"""Outbound port: the food catalogue."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class FoodCatalogOutputPort(Protocol):
    def all(self, professional_id: str) -> tuple[Food, ...]: ...

    def by_id(self, professional_id: str) -> dict[int, Food]: ...

    def add(self, professional_id: str, food: Food) -> Food: ...
