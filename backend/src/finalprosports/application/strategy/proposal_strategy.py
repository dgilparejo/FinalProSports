"""The seam of v2: a proposal strategy receives the profile and the retrieved cases and returns a proposal.
CaseBasedComposer is the v1 implementation; an LLM fallback proposer (v2) implements the same Protocol."""
from typing import Protocol

from finalprosports.domain.model import ClientProfile, DietProposal, RetrievedCase, Rule


class ProposalStrategy(Protocol):
    name: str

    def propose(self, profile: ClientProfile, cases: tuple[RetrievedCase, ...], rules: tuple[Rule, ...], params=None, **kwargs) -> DietProposal: ...
