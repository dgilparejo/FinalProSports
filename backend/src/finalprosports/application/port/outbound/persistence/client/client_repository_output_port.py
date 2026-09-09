"""Outbound port: client profiles."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class ClientRepositoryOutputPort(Protocol):
    """``get`` / ``list`` / ``save`` see ONLY the professional's portfolio (S1); the case base is reachable through
    ``list_case_profiles`` for the retrieval and evaluation adapters."""

    def get(self, professional_id: str, client_code: str) -> ClientProfile | None: ...

    def list(self, professional_id: str) -> tuple[ClientProfile, ...]: ...

    def save(self, profile: ClientProfile) -> ClientProfile: ...

    def list_case_profiles(self, professional_id: str) -> tuple[ClientProfile, ...]: ...
