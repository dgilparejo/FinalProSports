"""Outbound port: archetypes (sex x age bucket x goal)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class ArchetypeOutputPort(Protocol):
    def all(self, professional_id: str) -> tuple[Archetype, ...]: ...
