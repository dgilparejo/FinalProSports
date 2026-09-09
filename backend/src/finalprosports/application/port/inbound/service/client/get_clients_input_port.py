"""Inbound query port: client profiles."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class GetClientsInputPort(Protocol):
    def get_clients(self, professional_id: str) -> tuple[ClientProfile, ...]: ...

    def get_client(self, professional_id: str, client_code: str) -> ClientProfile: ...
