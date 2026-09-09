"""Pydantic DTO of POST /catalog/foods (S5): a new canonical food with its 14 MANDATORY flags."""
from __future__ import annotations

from pydantic import BaseModel, Field


class FoodFlagsDto(BaseModel):
    """Every flag is required: without them the validator cannot protect (allergens) nor the constitution veto (rule flags)."""

    is_processed_sugar: bool
    is_soft_drink: bool
    is_salt: bool
    is_fasting_compatible: bool
    is_alcohol: bool
    is_stimulant: bool
    is_peanut: bool
    is_tree_nut: bool
    contains_lactose: bool
    contains_gluten: bool
    contains_soy: bool
    contains_shellfish: bool
    contains_egg: bool
    contains_fish: bool


class NewFoodDto(BaseModel):
    canonical_name: str = Field(min_length=2, max_length=80, examples=["tempeh"])
    family: str = Field(min_length=2, max_length=60, description="family of the catalogue (e.g. legumbre, pescado_azul, verdura) — free but lower-case")
    group: str = Field(pattern="^(PROTEIN|CARB|FAT|VEGETABLE|FRUIT|DAIRY|SUPPLEMENT|BEVERAGE|CONDIMENT|OTHER)$")
    secondary_group: str | None = Field(default=None, pattern="^(PROTEIN|CARB|FAT|VEGETABLE|FRUIT|DAIRY|SUPPLEMENT|BEVERAGE|CONDIMENT|OTHER)$")
    flags: FoodFlagsDto
    synonyms: list[str] = Field(default_factory=list, max_length=20)
