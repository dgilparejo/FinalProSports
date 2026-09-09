"""Profile completeness (S3): what is missing in a client, split into what the ALGORITHM consumes and what is only RECORD.

The professional sees two numbers, not one: a record can be 40 % complete and still give the engine everything it uses. The
algorithm inputs are exactly what reaches POST /diets/propose through ClientProfile: sex, age, height, activity level, goal, sport,
structured restrictions, disliked foods and supplements already owned. Everything else (name, phone, measurements, injuries,
schedules ...) is record: useful for the professional, the PDF and the follow-up, but no retrieval or composition step reads it.
Weight is record too: the corpus has no weight, so nothing can be matched on it (structural limitation, declared).
"""
from __future__ import annotations

from dataclasses import dataclass

from finalprosports.domain.model.client_profile import ClientProfile
from finalprosports.domain.model.client_record import ClientRecord

ALGORITHM_INPUTS: tuple[tuple[str, str], ...] = (            # (field key, Spanish label for the UI)
    ("sex", "sexo"), ("age", "edad"), ("height_cm", "altura"), ("activity_level", "nivel de actividad"), ("goal", "objetivo"),
    ("sport", "deporte"), ("restrictions", "restricciones estructuradas (alergias / intolerancias)"), ("disliked_foods", "gustos negativos"),
    ("supplements_owned", "suplementos que ya tiene"),
)
RECORD_FIELDS: tuple[tuple[str, str], ...] = (
    ("full_name", "nombre"), ("birth_date", "fecha de nacimiento"), ("phone", "teléfono"), ("email", "correo"),
    ("first_visit", "fecha de primera consulta"), ("initial_weight_kg", "peso inicial"), ("wrist_cm", "muñeca"), ("waist_cm", "cintura"), ("neck_cm", "cuello"),
    ("somatotype", "tipo de fisionomía"), ("allergies", "alergias (texto)"), ("intolerances", "intolerancias (texto)"), ("injuries", "lesiones o molestias"),
    ("surgeries", "operaciones"), ("liked_foods", "gustos positivos"), ("food_vices", "vicios alimenticios"), ("smokes", "fuma"), ("drinks_alcohol", "bebe alcohol"),
    ("training_years", "tiempo entrenando"), ("achievements", "logros y marcas"), ("goals_text", "objetivos (texto)"), ("work_schedule", "horario de trabajo"),
    ("training_schedule", "horario de entrenamiento"), ("first_diet_notes", "notas de la primera dieta"), ("watch_brand", "marca del reloj deportivo"),
)


@dataclass(frozen=True)
class Completeness:
    algorithm_present: tuple[str, ...]
    algorithm_missing: tuple[str, ...]
    record_present: tuple[str, ...]
    record_missing: tuple[str, ...]

    @property
    def algorithm_ratio(self) -> float:
        n = len(self.algorithm_present) + len(self.algorithm_missing)
        return round(len(self.algorithm_present) / n, 3) if n else 1.0

    @property
    def record_ratio(self) -> float:
        n = len(self.record_present) + len(self.record_missing)
        return round(len(self.record_present) / n, 3) if n else 1.0


def _present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (tuple, list, set, frozenset)):
        return len(v) > 0
    return True


def _algorithm_values(profile: ClientProfile, record: ClientRecord | None) -> dict[str, object]:
    return {"sex": profile.sex, "age": profile.age, "height_cm": profile.height_cm, "activity_level": profile.activity_level, "goal": profile.goal,
            "sport": profile.sport or (record.sports.sports if record else None),
            "restrictions": profile.restrictions or (record is not None and (_present(record.medical.allergies) or _present(record.medical.intolerances))) or None,
            "disliked_foods": profile.disliked_food_ids or (record.diet.disliked_foods if record else None),
            "supplements_owned": profile.owned_supplement_ids or (record.sports.supplements_owned if record else None)}


def _record_values(record: ClientRecord | None) -> dict[str, object]:
    if record is None:
        return {k: None for k, _ in RECORD_FIELDS}
    i, p, m, d, s = record.identification, record.physiology, record.medical, record.diet, record.sports
    return {"full_name": i.full_name, "birth_date": i.birth_date, "phone": i.phone, "email": i.email, "first_visit": p.first_visit,
            "initial_weight_kg": p.initial_weight_kg, "wrist_cm": p.wrist_cm, "waist_cm": p.waist_cm, "neck_cm": p.neck_cm, "somatotype": p.somatotype,
            "allergies": m.allergies, "intolerances": m.intolerances, "injuries": m.injuries, "surgeries": m.surgeries, "liked_foods": d.liked_foods,
            "food_vices": d.food_vices, "smokes": d.smokes, "drinks_alcohol": d.drinks_alcohol, "training_years": s.training_years, "achievements": s.achievements,
            "goals_text": s.goals_text, "work_schedule": s.work_schedule, "training_schedule": s.training_schedule, "first_diet_notes": s.first_diet_notes,
            "watch_brand": s.watch_brand}


def completeness(profile: ClientProfile, record: ClientRecord | None) -> Completeness:
    a, r = _algorithm_values(profile, record), _record_values(record)
    return Completeness(tuple(k for k, _ in ALGORITHM_INPUTS if _present(a[k])), tuple(k for k, _ in ALGORITHM_INPUTS if not _present(a[k])),
                        tuple(k for k, _ in RECORD_FIELDS if _present(r[k])), tuple(k for k, _ in RECORD_FIELDS if not _present(r[k])))


def label(key: str) -> str:
    return dict(ALGORITHM_INPUTS + RECORD_FIELDS).get(key, key)
