from finalprosports.application.port.outbound.persistence.rules.rule_repository_output_port import RuleRepositoryOutputPort
from finalprosports.domain.model import Rule, RuleConfidence


class GetRulesService:
    def __init__(self, rules: RuleRepositoryOutputPort):
        self._rules = rules

    def get_rules(self, professional_id: str, include_low_confidence: bool = False) -> tuple[Rule, ...]:
        rules = self._rules.all(professional_id)
        if include_low_confidence:
            return rules
        return tuple(r for r in rules if r.confidence is not RuleConfidence.LOW)
