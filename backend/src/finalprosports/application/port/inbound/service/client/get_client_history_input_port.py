"""Inbound query port: a client's diet history."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class GetClientHistoryInputPort(Protocol):
    def get_history(self, professional_id: str, client_code: str) -> tuple[Diet, ...]: ...
