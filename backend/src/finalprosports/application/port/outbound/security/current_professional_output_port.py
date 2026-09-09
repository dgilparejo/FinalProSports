"""Outbound port: identity of the current professional (fixed today, Keycloak in v2)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class CurrentProfessionalOutputPort(Protocol):
    def current_professional_id(self) -> str: ...
