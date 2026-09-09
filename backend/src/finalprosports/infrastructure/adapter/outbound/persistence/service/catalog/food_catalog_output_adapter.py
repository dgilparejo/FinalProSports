from sqlalchemy import select, text

from finalprosports.domain.model import Food
from finalprosports.infrastructure.adapter.outbound.persistence.entity.food_entity import FLAGS, FoodEntity
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.food_mapper import to_domain


class FoodCatalogOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    def all(self, professional_id: str) -> tuple[Food, ...]:
        with self._sf() as s:
            return tuple(to_domain(e) for e in s.execute(select(FoodEntity).where(FoodEntity.professional_id == professional_id).order_by(FoodEntity.id)).scalars())

    def by_id(self, professional_id: str) -> dict[int, Food]:
        return {f.id: f for f in self.all(professional_id)}

    def add(self, professional_id: str, food: Food) -> Food:
        """S5: a food registered by the professional (created_by_professional, frequency 0, keys = normalised name + synonyms)."""
        from finalprosports.application.service.catalog.food_matcher import normalise
        cols = ", ".join(FLAGS)
        marks = ", ".join(f":{f}" for f in FLAGS)
        with self._sf() as s:
            s.execute(text(f"INSERT INTO foods (id, professional_id, canonical_name, family, food_group, secondary_group, frequency, attribute_source, synonyms, keys, "
                           f"created_by_professional, {cols}) VALUES (:id, :p, :name, :family, :grp, :sec, 0, 'professional', :syn, :keys, true, {marks})"),
                      {"id": food.id, "p": professional_id, "name": food.canonical_name, "family": food.family, "grp": food.group.value,
                       "sec": food.secondary_group.value if food.secondary_group else None, "syn": list(food.synonyms),
                       "keys": sorted({normalise(food.canonical_name), *(normalise(x) for x in food.synonyms)}), **{f: bool(getattr(food.flags, f)) for f in FLAGS}})
            s.commit()
        return food
