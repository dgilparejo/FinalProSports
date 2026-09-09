"""Intake endpoints (S3): the client's record (five blocks of the professional's sheet), the body-composition import (scale export
with the db_*/users + history structure, or a manual reading), the estimates (US Navy body fat, BMI, frame) and the completeness
indicator that distinguishes RECORD from ALGORITHM INPUT. Portfolio only, like every client endpoint."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, status

from finalprosports.domain.composition.policy.profile_completeness_policy import ALGORITHM_INPUTS, RECORD_FIELDS, label
from finalprosports.domain.model.client_record import BodyMeasurement, ClientRecord, DietPreferences, Identification, MedicalHistory, Physiology, Somatotype, SportsProfile
from finalprosports.infrastructure.adapter.inbound.rest.dto.record_dto import ClientRecordDto, ManualMeasurementDto, ScaleImportDto
from finalprosports.infrastructure.adapter.inbound.rest.service.client.get_clients_rest_adapter import client_to_dict


def record_from_dto(dto: ClientRecordDto, client_id: str, professional_id: str) -> ClientRecord:
    i, p, m, d, s = dto.identification, dto.physiology, dto.medical, dto.diet, dto.sports
    return ClientRecord(client_id, professional_id,
                        Identification(i.full_name, i.birth_date, i.phone, i.email),
                        Physiology(p.first_visit, p.initial_weight_kg, p.height_cm, p.wrist_cm, p.waist_cm, p.neck_cm, p.hip_cm, Somatotype(p.somatotype) if p.somatotype else None),
                        MedicalHistory(m.allergies, m.intolerances, m.injuries, m.surgeries),
                        DietPreferences(d.liked_foods, d.disliked_foods, d.food_vices, d.smokes, d.drinks_alcohol),
                        SportsProfile(s.training_years, s.sports, s.achievements, s.goals_text, s.work_schedule, s.training_schedule, s.supplements_owned, s.first_diet_notes, s.watch_brand))


def record_to_dict(r: ClientRecord) -> dict:
    d = {"client_id": r.client_code, "identification": asdict(r.identification), "physiology": asdict(r.physiology), "medical": asdict(r.medical),
         "diet": asdict(r.diet), "sports": asdict(r.sports), "updated_at": r.updated_at.isoformat() if r.updated_at else None}
    d["physiology"]["somatotype"] = r.physiology.somatotype.value if r.physiology.somatotype else None
    for block in ("identification", "physiology"):
        for k, v in d[block].items():
            if hasattr(v, "isoformat"):
                d[block][k] = v.isoformat()
    return d


def measurement_to_dict(m: BodyMeasurement) -> dict:
    """Las once magnitudes. Salían seis: las cinco de la hoja de S3 más la altura, y las cinco que abrió la 0015
    (músculo en kilos, complexión, grasa visceral, edad metabólica y metabolismo basal) se quedaban en la tabla."""
    return {"measured_at": m.measured_at.isoformat(), "weight_kg": m.weight_kg, "height_cm": m.height_cm, "body_fat_pct": m.body_fat_pct,
            "muscle_pct": m.muscle_pct, "muscle_mass_kg": m.muscle_mass_kg, "water_pct": m.water_pct, "bone_kg": m.bone_kg,
            "physique_rating": m.physique_rating, "visceral_fat_rating": m.visceral_fat_rating, "metabolic_age": m.metabolic_age,
            "basal_met_kcal": m.basal_met_kcal, "source": m.source}


def completeness_to_dict(c) -> dict:
    return {"algorithm": {"ratio": c.algorithm_ratio, "present": [{"key": k, "label": label(k)} for k in c.algorithm_present],
                          "missing": [{"key": k, "label": label(k)} for k in c.algorithm_missing], "total": len(ALGORITHM_INPUTS)},
            "record": {"ratio": c.record_ratio, "present": [{"key": k, "label": label(k)} for k in c.record_present],
                       "missing": [{"key": k, "label": label(k)} for k in c.record_missing], "total": len(RECORD_FIELDS)}}


class ClientRecordRestAdapter:
    def __init__(self, root):
        self.router = APIRouter(tags=["intake"])
        current, service, update_uc, import_uc = root.current_professional, root.get_client_record_service, root.update_client_record_use_case, root.import_body_composition_use_case
        catalog = root.catalog
        names = type("LiveNames", (), {"get": staticmethod(lambda i, d=None: catalog[i].canonical_name if i in catalog else d)})()   # live catalogue (S5)

        def view_to_dict(v) -> dict:
            e = v.body_composition
            return {"client": client_to_dict(v.profile, v.record.identification) | {"sport": v.profile.sport, "disliked_foods": [{"food_id": i, "canonical_name": names.get(i)} for i in v.profile.disliked_food_ids],
                                                          "supplements_owned": [{"food_id": i, "canonical_name": names.get(i)} for i in v.profile.owned_supplement_ids]},
                    "record": record_to_dict(v.record), "measurements": [measurement_to_dict(m) for m in v.measurements], "latest_weight_kg": v.latest_weight_kg,
                    "body_composition": {"body_fat_pct": e.body_fat_pct, "method": e.body_fat_method, "note": e.body_fat_note, "bmi": e.bmi, "frame_index": e.frame_index,
                                         "somatotype_hint": e.somatotype_hint.value if e.somatotype_hint else None},
                    "completeness": completeness_to_dict(v.completeness)}

        @self.router.get("/clients/{client_id}/record", summary="Intake record, measurements, body-composition estimates and completeness (record vs algorithm input)")
        def get_record(client_id: str):
            return view_to_dict(service.get(current.current_professional_id(), client_id))

        @self.router.put("/clients/{client_id}/record", summary="Save the intake questionnaire (five blocks); syncs age, height, sport, disliked foods and owned supplements into the profile")
        def put_record(client_id: str, dto: ClientRecordDto):
            pid = current.current_professional_id()
            _, _, matches = update_uc.update(pid, record_from_dto(dto, client_id, pid))
            out = view_to_dict(service.get(pid, client_id))
            out["matching"] = {k: {"matched": [{"text": t, "food_id": i, "canonical_name": n} for t, i, n in m.matched], "unmatched": list(m.unmatched)} for k, m in matches.items()}
            return out

        @self.router.get("/clients/{client_id}/body-composition", summary="Measurements (scale or manual) and estimates")
        def get_body(client_id: str):
            v = service.get(current.current_professional_id(), client_id)
            d = view_to_dict(v)
            return {"measurements": d["measurements"], "latest_weight_kg": d["latest_weight_kg"], "body_composition": d["body_composition"]}

        @self.router.post("/clients/{client_id}/body-composition/import", status_code=status.HTTP_201_CREATED,
                          summary="Import the connected scale's export (same structure as db_*/users + history); names in the dump are ignored")
        def import_scale(client_id: str, dto: ScaleImportDto):
            pid = current.current_professional_id()
            r = import_uc.import_scale(pid, client_id, dto.users, dto.history)
            return {"measurements_added": r["measurements_added"], "users_seen": r["users_seen"], "birth_date": r["birth_date"].isoformat() if r["birth_date"] else None,
                    **view_to_dict(service.get(pid, client_id))}

        @self.router.post("/clients/{client_id}/body-composition", status_code=status.HTTP_201_CREATED,
                          summary="Manual reading: weight and, optionally, any of the other ten magnitudes the scale measures")
        def add_manual(client_id: str, dto: ManualMeasurementDto):
            pid = current.current_professional_id()
            m = BodyMeasurement(dto.measured_at or datetime.now(timezone.utc), dto.weight_kg, dto.height_cm, dto.body_fat_pct, dto.muscle_pct,
                                dto.water_pct, dto.bone_kg, "manual", muscle_mass_kg=dto.muscle_mass_kg, physique_rating=dto.physique_rating,
                                visceral_fat_rating=dto.visceral_fat_rating, metabolic_age=dto.metabolic_age, basal_met_kcal=dto.basal_met_kcal)
            r = import_uc.add_manual(pid, client_id, m)
            return {"measurements_added": r["measurements_added"], **view_to_dict(service.get(pid, client_id))}
