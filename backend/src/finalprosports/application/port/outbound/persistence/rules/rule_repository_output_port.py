"""Outbound port: validated rules."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class RuleRepositoryOutputPort(Protocol):
    def all(self, professional_id: str) -> tuple[Rule, ...]: ...
