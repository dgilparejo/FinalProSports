"""Inbound use case: register a client profile."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class RegisterClientInputPort(Protocol):
    def register(self, profile: ClientProfile) -> ClientProfile: ...
