"""ClientRecord / BodyMeasurement <-> plain rows of client_records / body_measurements (one mapper for the record repository)."""
from __future__ import annotations

from datetime import date, datetime

from finalprosports.domain.model.client_record import BodyMeasurement, ClientRecord, DietPreferences, Identification, MedicalHistory, Physiology, Somatotype, SportsProfile

RECORD_COLUMNS = ("full_name", "birth_date", "phone", "email",
                  "first_visit", "initial_weight_kg", "height_cm", "wrist_cm", "waist_cm", "neck_cm", "hip_cm", "somatotype",
                  "allergies", "intolerances", "injuries", "surgeries",
                  "liked_foods", "disliked_foods", "food_vices", "smokes", "drinks_alcohol",
                  "training_years", "sports", "achievements", "goals_text", "work_schedule", "training_schedule", "supplements_owned", "first_diet_notes", "watch_brand")


def record_to_row(r: ClientRecord) -> dict:
    i, p, m, d, s = r.identification, r.physiology, r.medical, r.diet, r.sports
    return {"client_code": r.client_code, "professional_id": r.professional_id,
            "full_name": i.full_name, "birth_date": i.birth_date, "phone": i.phone, "email": i.email,
            "first_visit": p.first_visit, "initial_weight_kg": p.initial_weight_kg, "height_cm": p.height_cm, "wrist_cm": p.wrist_cm, "waist_cm": p.waist_cm,
            "neck_cm": p.neck_cm, "hip_cm": p.hip_cm, "somatotype": p.somatotype.value if p.somatotype else None,
            "allergies": m.allergies, "intolerances": m.intolerances, "injuries": m.injuries, "surgeries": m.surgeries,
            "liked_foods": d.liked_foods, "disliked_foods": d.disliked_foods, "food_vices": d.food_vices, "smokes": d.smokes, "drinks_alcohol": d.drinks_alcohol,
            "training_years": s.training_years, "sports": s.sports, "achievements": s.achievements, "goals_text": s.goals_text, "work_schedule": s.work_schedule,
            "training_schedule": s.training_schedule, "supplements_owned": s.supplements_owned, "first_diet_notes": s.first_diet_notes, "watch_brand": s.watch_brand}


def _f(v) -> float | None:
    return float(v) if v is not None else None


def record_from_row(row) -> ClientRecord:
    g = row._mapping.get if hasattr(row, "_mapping") else row.get
    return ClientRecord(
        client_code=g("client_code"), professional_id=g("professional_id"),
        identification=Identification(g("full_name"), g("birth_date"), g("phone"), g("email")),
        physiology=Physiology(g("first_visit"), _f(g("initial_weight_kg")), g("height_cm"), _f(g("wrist_cm")), _f(g("waist_cm")), _f(g("neck_cm")), _f(g("hip_cm")),
                              Somatotype(g("somatotype")) if g("somatotype") else None),
        medical=MedicalHistory(g("allergies"), g("intolerances"), g("injuries"), g("surgeries")),
        diet=DietPreferences(g("liked_foods"), g("disliked_foods"), g("food_vices"), g("smokes"), g("drinks_alcohol")),
        sports=SportsProfile(_f(g("training_years")), g("sports"), g("achievements"), g("goals_text"), g("work_schedule"), g("training_schedule"),
                             g("supplements_owned"), g("first_diet_notes"), g("watch_brand")),
        updated_at=g("updated_at"))


def measurement_from_row(row) -> BodyMeasurement:
    g = row._mapping.get if hasattr(row, "_mapping") else row.get
    return BodyMeasurement(g("measured_at"), _f(g("weight_kg")), g("height_cm"), _f(g("body_fat_pct")), _f(g("muscle_pct")), _f(g("water_pct")), _f(g("bone_kg")), g("source"),
                           _f(g("muscle_mass_kg")), g("physique_rating"), _f(g("visceral_fat_rating")), g("metabolic_age"), g("basal_met_kcal"))


def measurement_to_row(professional_id: str, client_code: str, m: BodyMeasurement) -> dict:
    return {"professional_id": professional_id, "client_code": client_code, "measured_at": m.measured_at, "weight_kg": m.weight_kg, "height_cm": m.height_cm,
            "body_fat_pct": m.body_fat_pct, "muscle_pct": m.muscle_pct, "water_pct": m.water_pct, "bone_kg": m.bone_kg, "source": m.source,
            "muscle_mass_kg": m.muscle_mass_kg, "physique_rating": m.physique_rating, "visceral_fat_rating": m.visceral_fat_rating,
            "metabolic_age": m.metabolic_age, "basal_met_kcal": m.basal_met_kcal}


def date_or_none(v) -> date | None:
    return v if isinstance(v, date) and not isinstance(v, datetime) else (v.date() if isinstance(v, datetime) else None)
