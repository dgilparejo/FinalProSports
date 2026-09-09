"""Outbound port: proposals accepted or edited by the professional (saved diets), stored whole with their evidence and validation."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class ProposalRepositoryOutputPort(Protocol):
    def save(self, professional_id: str, proposal: DietProposal, edited: bool, original: DietProposal | None = None, diff=None) -> str: ...

    def get_detail(self, professional_id: str, diet_id: str) -> dict | None: ...

    def get(self, professional_id: str, diet_id: str) -> DietProposal | None: ...

    def list_for_client(self, professional_id: str, client_code: str) -> tuple[dict, ...]: ...

    def delete_for_corpus_clients(self, professional_id: str) -> int: ...
