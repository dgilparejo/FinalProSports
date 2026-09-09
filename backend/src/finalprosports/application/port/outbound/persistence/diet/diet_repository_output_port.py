"""Outbound port: diets (cases and edited proposals)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class DietRepositoryOutputPort(Protocol):
    def history(self, professional_id: str, client_code: str) -> tuple[Diet, ...]: ...

    def save(self, diet: Diet) -> Diet: ...
