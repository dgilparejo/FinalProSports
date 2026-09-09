from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind
from finalprosports.infrastructure.adapter.inbound.rest.dto.profile_dto import FoodDto, ProfileRequestDto, RuleDto


def to_domain(dto: ProfileRequestDto, professional_id: str) -> ClientProfile:
    return ClientProfile(client_code=dto.client_code, professional_id=professional_id, sex=dto.sex, age=dto.age, height_cm=dto.height_cm,
                         activity_level=dto.activity_level, goal=Goal(dto.goal) if dto.goal else None,
                         restrictions=tuple(Restriction(RestrictionKind(r), strict=dto.strict_restrictions) for r in dto.restrictions))


def food_to_dto(f) -> FoodDto:
    return FoodDto(id=f.id, canonical_name=f.canonical_name, family=f.family, group=f.group.value,
                   secondary_group=f.secondary_group.value if f.secondary_group else None, flags=dict(f.flags.__dict__),
                   created_by_professional=f.created_by_professional, synonyms=list(f.synonyms))


def rule_to_dto(r) -> RuleDto:
    return RuleDto(id=r.id, statement=r.statement, scope=r.scope.value, status=r.status.value, confidence=r.confidence.value if r.confidence else None,
                   n_support=r.n_support, lift=r.lift, adjusted=r.adjusted, enabled=r.enabled)
