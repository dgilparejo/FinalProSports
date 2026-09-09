"""Inbound query port: the k most similar cases for a profile (used by the REST adapter, the use case and the LOO harness)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class RetrieveSimilarCasesInputPort(Protocol):
    def retrieve(self, professional_id: str, profile: ClientProfile, k: int = 5, exclude_diet_ids: frozenset[str] = frozenset()) -> tuple[RetrievedCase, ...]: ...
