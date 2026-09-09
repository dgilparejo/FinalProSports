"""Inbound use case: propose a diet for a profile."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class ProposeDietInputPort(Protocol):
    def propose(self, professional_id: str, profile: ClientProfile, k: int = 5, exclude_diet_ids: frozenset[str] = frozenset()) -> DietProposal: ...
