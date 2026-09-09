from finalprosports.domain.model import Rule, RuleConfidence, RuleNature, RuleScope, RuleStatus
from finalprosports.infrastructure.adapter.outbound.persistence.entity.rule_entity import RuleEntity


def to_domain(e: RuleEntity) -> Rule:
    return Rule(id=e.id, statement=e.statement, scope=RuleScope(e.kind), status=RuleStatus(e.status), evaluation_level=e.evaluation_level,
                condition=tuple(e.condition or ()), confidence=RuleConfidence(e.confidence) if e.confidence else None,
                n_support=e.n_support, prevalence=float(e.prevalence_in_group) if e.prevalence_in_group is not None else None,
                lift=float(e.lift) if e.lift is not None else None,
                adjusted=float(e.adjusted) if e.adjusted is not None else None, enabled=e.enabled,
                nature=RuleNature(e.nature) if e.nature else None)
