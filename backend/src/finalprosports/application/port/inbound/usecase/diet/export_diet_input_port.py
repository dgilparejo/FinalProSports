"""Inbound use case: export a diet (PDF)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class ExportDietInputPort(Protocol):
    def export(self, professional_id: str, diet_id: str) -> bytes: ...
