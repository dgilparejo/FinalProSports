"""Inbound query port: the food catalogue."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class GetFoodCatalogInputPort(Protocol):
    def get_catalog(self, professional_id: str) -> tuple[Food, ...]: ...
