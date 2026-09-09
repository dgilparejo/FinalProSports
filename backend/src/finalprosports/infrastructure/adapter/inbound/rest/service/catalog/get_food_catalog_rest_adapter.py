from fastapi import APIRouter, status

from finalprosports.domain.model import FoodFlags, FoodGroup
from finalprosports.infrastructure.adapter.inbound.rest.dto.catalog_dto import NewFoodDto
from finalprosports.infrastructure.adapter.inbound.rest.mapper.profile_mapper import food_to_dto


class GetFoodCatalogRestAdapter:
    def __init__(self, root):
        self.router = APIRouter(tags=["catalog"])
        service, current, add_uc = root.get_food_catalog_service, root.current_professional, root.add_food_use_case

        @self.router.get("/catalog/foods", summary="Canonical food catalogue with families, groups and flags (evidence panel)")
        def get_foods():
            return [food_to_dto(f) for f in service.get_catalog(current.current_professional_id())]

        @self.router.post("/catalog/foods", status_code=status.HTTP_201_CREATED, summary="Register a food the catalogue lacks (S5): canonical name, family, group and the 14 mandatory flags")
        def add_food(dto: NewFoodDto):
            food = add_uc.add(current.current_professional_id(), dto.canonical_name, dto.family, FoodGroup(dto.group), FoodFlags(**dto.flags.model_dump()),
                              FoodGroup(dto.secondary_group) if dto.secondary_group else None, tuple(dto.synonyms))
            return food_to_dto(food)
