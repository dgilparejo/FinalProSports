# -*- coding: utf-8 -*-
"""Construye un fixture SINTÉTICO para el e2e, con la misma forma que el real y ninguna persona dentro.

El e2e vale por lo que recorre —alta por nombre, expediente, importación de báscula, analíticas, historial de dos
versiones, propuesta y aserciones automáticas— y eso no depende de que los datos sean de nadie. Pero el fixture que
había ES de un cliente REAL del preparador: identidad inventada, sí, pero sus 481 parámetros de laboratorio, sus tres
pesajes y sus dos dietas anteriores. En el árbol privado se queda (se carga por `FPS_E2E_FIXTURE`); el público lleva
este, generado.

Las dos «dietas anteriores» se producen pidiéndoselas al MOTOR contra la base de casos que esté cargada, y se guardan
con el mismo serializador que usa la aplicación (`proposal_to_dict`), así que el test no distingue una de otra: recibe
dos versiones previas coherentes con el catálogo y con las reglas.

Uso (desde backend/, con DATABASE_URL y FPS_DATASET_DIR apuntando a la base sintética):
  python ../backend/tests/e2e/build_synthetic_fixture.py --out tests/e2e/fixtures/client_recurrent_volume_synthetic.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind  # noqa: E402
from finalprosports.infrastructure.adapter.inbound.cli.seed_demo import lab_panel, scale_export  # noqa: E402
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.proposal_mapper import proposal_to_dict  # noqa: E402
from finalprosports.infrastructure.composition_root import CompositionRoot  # noqa: E402

REFERENCE_DAY = date(2026, 9, 1)
# El cliente inventado del e2e: recurrente, volumen, con una intolerancia dura para que el validador tenga trabajo.
SPEC = {
    "tag": "e2e", "full_name": "Ibai Sintético Demo", "birth_date": date(1996, 4, 17),
    "phone": "+34 000 000 099", "email_parts": ["ibai.sintetico", "demo.invalid"],
    "sex": "M", "height_cm": 179, "activity_level": 5, "goal": Goal.VOLUME,
    "restrictions": (RestrictionKind.LACTOSE,),
}
RECORD = {
    "first_visit": "2026-03-02", "initial_weight_kg": 74.5, "height_cm": 179, "wrist_cm": 17.2,
    "waist_cm": 80.0, "neck_cm": 38.5, "hip_cm": None, "somatotype": "mesomorfo",
    "allergies": "ninguna", "intolerances": "lactosa", "injuries": "ninguna", "surgeries": "ninguna",
    "liked_foods": "arroz, pavo, plátano", "disliked_foods": "coliflor", "food_vices": "refrescos",
    "smokes": False, "drinks_alcohol": False,
    "training_years": 4, "sports": "gimnasio (fuerza)", "achievements": "primer torneo amateur",
    "goals_text": "subir masa muscular sin ensuciar la dieta", "work_schedule": "9:00-18:00",
    "training_schedule": "19:00-20:30", "supplements_owned": "creatina, batido de proteínas",
    "first_diet_notes": None, "watch_brand": "Garmin",
}
LABS = {"Glucosa": 91, "Hemoglobina glicosilada": 5.1, "Colesterol total": 181, "HDL": 57, "LDL": 104,
        "Triglicéridos": 96, "Ferritina": 112, "Hierro": 98, "Vitamina D": 27, "Vitamina B12": 386,
        "TSH": 1.8, "Creatinina": 1.02}


def build(root: CompositionRoot, versions: int = 2) -> dict:
    pid = root.configured_professional_id
    profile = ClientProfile(client_code="", professional_id=pid, sex=SPEC["sex"],
                            age=REFERENCE_DAY.year - SPEC["birth_date"].year, height_cm=SPEC["height_cm"],
                            activity_level=SPEC["activity_level"], goal=SPEC["goal"],
                            restrictions=tuple(Restriction(k) for k in SPEC["restrictions"]),
                            has_intolerances=True)
    previas = []
    historia: tuple = ()
    for v in range(1, versions + 1):
        prop = root.propose_diet_use_case.propose(pid, profile, k=20, history=historia)
        previas.append({"date": (REFERENCE_DAY - timedelta(days=45 * (versions - v + 1))).isoformat(),
                        "payload": proposal_to_dict(prop)})
    users, history = scale_export({**SPEC, "sex": SPEC["sex"]}, (78.4, 14.6, +0.6, 3))
    scale = [{"measured_at": h["date"], "weight_kg": h["weight"], "fat_pct": h["percentFat"],
              "muscle_mass_kg": h["muscleMass"], "hydration_pct": h["percentHydration"],
              "bone_mass_kg": h["boneMass"], "visceral_fat_rating": h["visceralFatRating"],
              "metabolic_age": h["metabolicAge"], "basal_met_kcal": h["basalMet"], "source": "scale"}
             for h in history]
    labs = [{"marker": r.marker, "value": r.value, "unit": r.unit, "ref_low": r.ref_low, "ref_high": r.ref_high,
             "measured_at": r.measured_at.isoformat(), "note": None, "source": "file"}
            for r in lab_panel(date(2026, 7, 8), LABS)]
    return {
        "_synthetic": True, "generated_by": "build_synthetic_fixture.py",
        "_note": ("Cliente INVENTADO. Ni un dato de una persona real: las dos versiones previas las compuso el motor "
                  "contra la base de casos sintética, la báscula y la analítica están generadas."),
        "full_name": SPEC["full_name"], "birth_date": SPEC["birth_date"].isoformat(), "phone": SPEC["phone"],
        "email_parts": SPEC["email_parts"], "sex": SPEC["sex"], "height_cm": SPEC["height_cm"],
        "activity_level": SPEC["activity_level"], "goal": SPEC["goal"].value,
        "restrictions": [k.value for k in SPEC["restrictions"]],
        "record": RECORD, "scale": scale, "labs": labs, "previous": previas,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--versions", type=int, default=2)
    args = ap.parse_args()
    fixture = build(CompositionRoot.from_env(), args.versions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"escrito {args.out} ({args.out.stat().st_size / 1024:.1f} KB): "
          f"{len(fixture['labs'])} parámetros, {len(fixture['scale'])} lecturas, {len(fixture['previous'])} versiones previas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
