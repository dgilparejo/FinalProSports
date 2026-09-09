"""Inbound query port: the validated constitution."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class GetRulesInputPort(Protocol):
    def get_rules(self, professional_id: str, include_low_confidence: bool = False) -> tuple[Rule, ...]: ...
