"""Client RECORD (S3): the professional's intake questionnaire («HOJA DATOS PERSONALES CLIENTES»), transcribed block by block, plus
the body-composition measurements (scale import or manual entry).

The record is the EXPEDIENTE: what the professional keeps about a client. Only a subset feeds the algorithm (sex, age, height,
activity, goal, sport, structured restrictions, disliked foods, supplements already owned) — see profile_completeness_policy. Health
free text (allergies, intolerances, injuries, surgeries) stays in the record for the professional; the engine only ever sees the
STRUCTURED restrictions of ClientProfile. Nothing here is ever logged or printed by the application.

Deliberate exclusion: the questionnaire's sports-watch block asked for the account's user name and password. Only the watch BRAND is
kept; third-party credentials are neither requested nor stored (storing them in clear in an unauthenticated health application is
not defensible; if ever needed it is OAuth and v2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Somatotype(StrEnum):
    ECTOMORPH = "ectomorfo"
    MESOMORPH = "mesomorfo"
    ENDOMORPH = "endomorfo"


@dataclass(frozen=True)
class Identification:
    full_name: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class Physiology:
    first_visit: date | None = None
    initial_weight_kg: float | None = None
    height_cm: int | None = None
    wrist_cm: float | None = None
    waist_cm: float | None = None
    neck_cm: float | None = None
    hip_cm: float | None = None            # US Navy needs the hip for women; the original sheet does not ask for it (declared)
    somatotype: Somatotype | None = None


@dataclass(frozen=True)
class MedicalHistory:
    allergies: str | None = None           # free text of the sheet; the ENGINE uses ClientProfile.restrictions (structured), never this text
    intolerances: str | None = None
    injuries: str | None = None
    surgeries: str | None = None


@dataclass(frozen=True)
class DietPreferences:
    liked_foods: str | None = None
    disliked_foods: str | None = None      # matched against the catalogue -> ClientProfile.disliked_food_ids (soft exclusions applied by the validator)
    food_vices: str | None = None
    smokes: bool | None = None
    drinks_alcohol: bool | None = None


@dataclass(frozen=True)
class SportsProfile:
    training_years: float | None = None
    sports: str | None = None
    achievements: str | None = None
    goals_text: str | None = None
    work_schedule: str | None = None
    training_schedule: str | None = None
    supplements_owned: str | None = None   # matched against the catalogue -> ClientProfile.owned_supplement_ids (shown, never vetoed)
    first_diet_notes: str | None = None
    watch_brand: str | None = None         # brand only; no credentials by design


@dataclass(frozen=True)
class ClientRecord:
    client_code: str
    professional_id: str
    identification: Identification = field(default_factory=Identification)
    physiology: Physiology = field(default_factory=Physiology)
    medical: MedicalHistory = field(default_factory=MedicalHistory)
    diet: DietPreferences = field(default_factory=DietPreferences)
    sports: SportsProfile = field(default_factory=SportsProfile)
    updated_at: datetime | None = None

    def age_on(self, today: date) -> int | None:
        b = self.identification.birth_date
        if b is None:
            return None
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


@dataclass(frozen=True)
class BodyMeasurement:
    """One reading of the connected scale (import) or a manual entry.

    El corpus SÍ lleva composición corporal medida, y conviene decirlo porque el CUESTIONARIO engaña: ahí el peso
    está anotado en pocos perfiles, y de ahí salió la idea de que no lo hubiera. La exportación de la báscula del
    profesional son 3.250 lecturas, de las que 1.338 casan con un cliente del corpus (171 clientes), y con la regla
    temporal aplicada cubren 617 de las 815 consultas del arnés (75,7 %), con antigüedad mediana de 13 días. No es una
    limitación estructural del corpus: es un dato que hay que cargar.

    Las cuatro magnitudes de abajo y el músculo en KILOS son lo que la báscula exporta y la hoja de S3 no recogía."""

    measured_at: datetime
    weight_kg: float | None = None
    height_cm: int | None = None
    body_fat_pct: float | None = None
    muscle_pct: float | None = None
    water_pct: float | None = None
    bone_kg: float | None = None
    source: str = "manual"                 # 'scale' | 'manual'
    muscle_mass_kg: float | None = None
    physique_rating: int | None = None
    visceral_fat_rating: float | None = None
    metabolic_age: int | None = None
    basal_met_kcal: int | None = None
