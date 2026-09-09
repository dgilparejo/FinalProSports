from finalprosports.domain.model import ClientProfile, Restriction, RestrictionKind
from finalprosports.infrastructure.adapter.outbound.persistence.entity.client_profile_entity import ClientProfileEntity


def to_domain(e: ClientProfileEntity) -> ClientProfile:
    return ClientProfile(client_code=e.client_code, professional_id=e.professional_id, sex=e.sex, age=e.age, height_cm=e.height_cm,
                         activity_level=e.activity_level, has_allergies=e.has_allergies, has_intolerances=e.has_intolerances,
                         has_medical_restrictions=e.has_medical_restrictions, is_athlete=e.is_athlete, is_corpus_case=bool(e.is_corpus_case),
                         sport=e.sport, body_type=e.body_type, corpus_alias=e.corpus_alias, training_time=e.training_time, disliked_food_ids=tuple(int(i) for i in (e.disliked_food_ids or ())), liked_food_ids=tuple(int(i) for i in (e.liked_food_ids or ())), owned_supplement_ids=tuple(int(i) for i in (e.owned_supplement_ids or ())),
                         goal=_goal(e.goals), restrictions=tuple(Restriction(RestrictionKind(r)) for r in (e.restrictions or ()) if r in RestrictionKind.__members__.values() or r in {k.value for k in RestrictionKind}))


def _goal(goals):
    from finalprosports.domain.model import Goal
    try:
        return Goal(goals) if goals else None
    except ValueError:
        return None
