"""Pydantic DTOs of the intake record and body-composition endpoints (S3). Five blocks transcribed from the professional's sheet."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class IdentificationDto(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)


class PhysiologyDto(BaseModel):
    first_visit: date | None = None
    initial_weight_kg: float | None = Field(default=None, ge=25, le=300)
    height_cm: int | None = Field(default=None, ge=120, le=220)
    wrist_cm: float | None = Field(default=None, ge=10, le=30)
    waist_cm: float | None = Field(default=None, ge=40, le=200)
    neck_cm: float | None = Field(default=None, ge=20, le=70)
    hip_cm: float | None = Field(default=None, ge=50, le=200, description="Not on the original sheet; needed by US Navy for women")
    somatotype: str | None = Field(default=None, pattern="^(ectomorfo|mesomorfo|endomorfo)$")


class MedicalDto(BaseModel):
    allergies: str | None = Field(default=None, max_length=1000)
    intolerances: str | None = Field(default=None, max_length=1000)
    injuries: str | None = Field(default=None, max_length=2000)
    surgeries: str | None = Field(default=None, max_length=2000)


class DietPreferencesDto(BaseModel):
    liked_foods: str | None = Field(default=None, max_length=1000)
    disliked_foods: str | None = Field(default=None, max_length=1000)
    food_vices: str | None = Field(default=None, max_length=1000)
    smokes: bool | None = None
    drinks_alcohol: bool | None = None


class SportsDto(BaseModel):
    training_years: float | None = Field(default=None, ge=0, le=80)
    sports: str | None = Field(default=None, max_length=300)
    achievements: str | None = Field(default=None, max_length=2000)
    goals_text: str | None = Field(default=None, max_length=2000)
    work_schedule: str | None = Field(default=None, max_length=300)
    training_schedule: str | None = Field(default=None, max_length=300)
    supplements_owned: str | None = Field(default=None, max_length=1000)
    first_diet_notes: str | None = Field(default=None, max_length=2000)
    watch_brand: str | None = Field(default=None, max_length=60, description="Brand only: credentials of third-party accounts are neither requested nor stored")


class ClientRecordDto(BaseModel):
    identification: IdentificationDto = Field(default_factory=IdentificationDto)
    physiology: PhysiologyDto = Field(default_factory=PhysiologyDto)
    medical: MedicalDto = Field(default_factory=MedicalDto)
    diet: DietPreferencesDto = Field(default_factory=DietPreferencesDto)
    sports: SportsDto = Field(default_factory=SportsDto)


class ScaleImportDto(BaseModel):
    """The connected scale's export: same structure as the professional's db_*/users and history files."""

    users: list[dict] = Field(default_factory=list, description="rows with isMale, birthdate (epoch ms), height_cm, activity_level, isLifetimeAthlete; name/email ignored")
    history: list[dict] = Field(default_factory=list, description="rows with date (epoch ms) and the eleven magnitudes: weight, percentFat, percentHydration, boneMass, "
                                                                  "muscleMass, physiqueRating, visceralFatRating, metabolicAge, basalMet, height (the `.bin` names; "
                                                                  "the `body_measurements.jsonl` names and the short aliases are accepted too)")


class ManualMeasurementDto(BaseModel):
    """Una lectura a mano, con las MISMAS magnitudes que la báscula exporta: si el profesional las lee en la pantalla
    del aparato, las puede teclear, y la fila resultante es comparable con la importada.

    Los límites no son inventados: son el rango observado en las 1.338 lecturas del corpus, redondeado hacia fuera.
    `muscle_pct` no sale de la báscula (mide kilos) y se queda como campo de entrada a mano; no se convierte."""

    measured_at: datetime | None = None
    weight_kg: float | None = Field(default=None, ge=25, le=300)
    height_cm: int | None = Field(default=None, ge=120, le=220)
    body_fat_pct: float | None = Field(default=None, ge=2, le=70)
    muscle_pct: float | None = Field(default=None, ge=10, le=80, description="Percentage; the scale gives muscle in kilos, use muscle_mass_kg for that")
    muscle_mass_kg: float | None = Field(default=None, ge=10, le=120, description="observed 35,3-87,8")
    water_pct: float | None = Field(default=None, ge=20, le=80, description="observed 31,4-70,3")
    bone_kg: float | None = Field(default=None, ge=0.5, le=10, description="observed 1,9-4,5")
    physique_rating: int | None = Field(default=None, ge=1, le=9, description="the scale's 1-9 physique rating")
    visceral_fat_rating: float | None = Field(default=None, ge=0, le=60, description="observed 0,8-29,9")
    metabolic_age: int | None = Field(default=None, ge=10, le=99, description="observed 12-75")
    basal_met_kcal: int | None = Field(default=None, ge=500, le=8000, description="observed 1.737-5.350")
