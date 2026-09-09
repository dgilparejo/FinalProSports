"""Save a proposal the professional accepted or edited: it is re-validated (restrictions first, then the enforceable rules) so that an
edit can never store a diet that violates the client's restrictions, and stored whole with its evidence and validation report. When the
ORIGINAL proposal is given, the diff (added / removed / re-quantified / moved items, notes, slots, edit ratio) is stored with it (S5)."""
from finalprosports.application.port.outbound.persistence.proposal.proposal_repository_output_port import ProposalRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.rules.rule_repository_output_port import RuleRepositoryOutputPort
from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.domain.composition.policy.proposal_diff_policy import ProposalDiff, diff_proposals
from finalprosports.domain.model import DietProposal


class SaveEditedDietUseCase:
    def __init__(self, proposals: ProposalRepositoryOutputPort, validator: DietValidator, rules: RuleRepositoryOutputPort):
        self._proposals, self._validator, self._rules = proposals, validator, rules

    def save(self, professional_id: str, proposal: DietProposal, edited: bool = True, original: DietProposal | None = None) -> dict:
        validated = self._validator.validate(proposal, self._rules.all(professional_id))
        diff: ProposalDiff | None = diff_proposals(original, validated) if original is not None else None      # S5: how much the professional corrected the engine
        edited = edited or (diff.is_edited if diff else False)
        diet_id = self._proposals.save(professional_id, validated, edited, original, diff)
        return {"id": diet_id, "proposal": validated, "diff": diff}
