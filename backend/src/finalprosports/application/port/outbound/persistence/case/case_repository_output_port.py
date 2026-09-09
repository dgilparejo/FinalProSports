"""Outbound port: cases (prescribed diets) retrieved for a query profile.

Four strategies implement it (see application.strategy.retrieval_strategy); the service does not know which one is wired.
`requires_embedding` tells the service whether to vectorise the query text (the attribute-only strategy needs no model call).
"""
from typing import Protocol

from finalprosports.domain.composition.policy.gap_policy import CandidateCounts
from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class CaseRepositoryOutputPort(Protocol):
    requires_embedding: bool

    def find_similar(self, professional_id: str, query: CaseQuery, k: int, exclude_diet_ids: frozenset[str]) -> tuple[RetrievedCase, ...]: ...

    def get(self, professional_id: str, diet_id: str) -> Diet: ...

    def all_ids(self, professional_id: str) -> tuple[str, ...]: ...

    def diet_ids_of_client(self, professional_id: str, client_code: str) -> frozenset[str]: ...

    def diet_ids_sharing_template_with(self, professional_id: str, client_code: str) -> frozenset[str]: ...

    def candidate_counts(self, professional_id: str, profile: ClientProfile, exclude_diet_ids: frozenset[str]) -> CandidateCounts: ...
