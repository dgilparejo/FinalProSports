from sqlalchemy import select

from finalprosports.domain.model import Rule
from finalprosports.infrastructure.adapter.outbound.persistence.entity.rule_entity import RuleEntity
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.rule_mapper import to_domain


class RuleRepositoryOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    def all(self, professional_id: str) -> tuple[Rule, ...]:
        with self._sf() as s:
            return tuple(to_domain(e) for e in s.execute(select(RuleEntity).where(RuleEntity.professional_id == professional_id).order_by(RuleEntity.section, RuleEntity.id)).scalars())
