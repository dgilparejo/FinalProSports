from finalprosports.domain.model import Food, FoodFlags, FoodGroup
from finalprosports.infrastructure.adapter.outbound.persistence.entity.food_entity import FLAGS, FoodEntity


def to_domain(e: FoodEntity) -> Food:
    return Food(id=e.id, canonical_name=e.canonical_name, group=FoodGroup(e.food_group), family=e.family,
                secondary_group=FoodGroup(e.secondary_group) if e.secondary_group else None,
                flags=FoodFlags(**{f: bool(getattr(e, f)) for f in FLAGS}), synonyms=tuple(e.synonyms or ()), frequency=e.frequency,
                created_by_professional=bool(getattr(e, "created_by_professional", False)))
