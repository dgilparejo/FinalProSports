"""Inbound use case: persist a diet edited by the professional."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class SaveEditedDietInputPort(Protocol):
    def save(self, diet: Diet) -> Diet: ...
