"""Outbound port: the professional's measured rotation statistics (persistence / lift per food, family persistence, renewal rates)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class RotationStatsOutputPort(Protocol):
    def load(self, professional_id: str) -> RotationStats: ...
