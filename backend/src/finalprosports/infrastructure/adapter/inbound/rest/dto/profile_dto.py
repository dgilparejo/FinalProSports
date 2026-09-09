"""Pydantic DTOs live ONLY in this package (import-linter contract)."""
from pydantic import BaseModel, Field


class ProfileRequestDto(BaseModel):
    """Ad-hoc profile for /similar-cases (retrieval only, nothing is stored): ``client_code`` is just a label for the query."""

    client_code: str = Field(default="consulta", pattern=r"^[A-Za-z0-9_-]{1,40}$")
    sex: str | None = Field(default=None, pattern="^[MF]$")
    age: int | None = Field(default=None, ge=14, le=80)
    height_cm: int | None = Field(default=None, ge=140, le=210)
    activity_level: int | None = Field(default=None, ge=1, le=6)
    goal: str | None = None
    restrictions: list[str] = []
    strict_restrictions: bool = True
    k: int = Field(default=5, ge=1, le=20)


class FoodDto(BaseModel):
    id: int
    canonical_name: str
    family: str | None
    group: str
    secondary_group: str | None
    flags: dict[str, bool]
    created_by_professional: bool = False
    synonyms: list[str] = []


class RuleDto(BaseModel):
    id: str
    statement: str
    scope: str
    status: str
    confidence: str | None
    n_support: int | None
    lift: float | None
    adjusted: float | None
    enabled: bool
