# -*- coding: utf-8 -*-
"""
Phase 4 — Client profiles with a uniform schema and health data separated.

Inputs (never modified):
  --profiles   _meta/perfiles.json                       (source; Spanish fields, sparse keys)
  --diets      _dataset/diets.jsonl                      (clean diets -> diet_count)
  --raw-diets  _dataset/anonymized/structured_diets.json (all 1.183 parsed diets -> diet_count_raw)

Outputs:
  <out-dir>/profiles.jsonl                 one record per client, EVERY field always present (null when unknown)
  <private-dir>/health_profiles.jsonl      GDPR art. 9 free text: surgeries, injuries, allergies, intolerances (raw)
  <out-dir>/build_profiles_log.json        counts

profiles.jsonl schema (English identifiers, Spanish values):
  client_code, sex, age, age_bucket, height_cm, activity_level, activity_level_reported, is_athlete,
  goals, sport, liked_foods, disliked_foods,
  has_allergies, has_intolerances, has_medical_restrictions,
  diet_count (clean corpus), diet_count_raw (all parsed diets), diet_count_stored (value in perfiles.json),
  empty_profile, unmapped (no match in the scale database -> no sex/age/height),
  suspicious_demographics (age outside 14-80 or height outside 140-210),
  field_carryover_suspected (parse_datos lookahead swallowed neighbouring fields), carryover_fields,
  redacted_public_fields (public free-text fields moved to the private file because they contained a clinical term)

Any public free-text field (goals, sport, liked_foods, disliked_foods) that contains a clinical term is set to null in
profiles.jsonl and stored in health_profiles.jsonl under `redacted_public_text`, so the indexable dataset carries no
GDPR art. 9 residue at all.

Field carry-over heuristic: a free-text value is suspected of carrying neighbouring fields when it hits
the 120-character truncation cap of perfiles.py or contains another form label (GUSTOS, TRABAJO, PUESTO,
DEPORTE, OBJETIVO, HORARIO, VICIOS, FUMA, BEBE, LOGROS, TIEMPO, ALERG, INTOLER, LESION, OPERAC, PESO,
ALTURA, EDAD, USUARIO, CONTRASE). Documented, not fixed (requires re-parsing DATOS__*.md).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pii_common import HEALTH_FIELDS_ES, MEDICAL_RE, load_records, require_file, write_json, write_jsonl  # noqa: E402
from sanitize import clean_rtf, nfc  # noqa: E402  (same RTF/NFC cleaning as the diets)

LABEL_RE = re.compile(r"\b(GUSTOS|TRABAJO|PUESTO|DEPORTE|OBJETIVO|HORARIO|VICIOS|FUMA|BEBE|LOGROS|TIEMPO|ALERG|INTOLER|"
                      r"LESION|OPERAC|PESO|ALTURA|EDAD|USUARIO|CONTRASE)", re.I)
TRUNCATION_CAP = 120
FREE_TEXT_ES = ("objetivos", "deporte", "gustos_pos", "gustos_neg") + HEALTH_FIELDS_ES
FREE_TEXT_EN = {"objetivos": "goals", "deporte": "sport", "gustos_pos": "liked_foods", "gustos_neg": "disliked_foods",
                "operaciones": "surgeries", "lesiones": "injuries", "alergias": "allergies", "intolerancias": "intolerances"}
SCHEMA = ["client_code", "sex", "age", "age_bucket", "height_cm", "activity_level", "activity_level_reported", "is_athlete",
          "goals", "sport", "liked_foods", "disliked_foods",
          "has_allergies", "has_intolerances", "has_medical_restrictions",
          "diet_count", "diet_count_raw", "diet_count_stored",
          "empty_profile", "unmapped", "suspicious_demographics", "field_carryover_suspected", "carryover_fields",
          "redacted_public_fields"]


def age_bucket(e):
    if e is None:
        return None
    return "<25" if e < 25 else "25-39" if e < 40 else "40-54" if e < 55 else "55+"


def carryover(value: str) -> bool:
    return len(value) >= TRUNCATION_CAP or bool(LABEL_RE.search(value))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profiles", required=True, type=Path)
    ap.add_argument("--diets", required=True, type=Path)
    ap.add_argument("--raw-diets", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--private-dir", required=True, type=Path)
    args = ap.parse_args()

    src = load_records(require_file(args.profiles))
    clean_counts = Counter(r["meta"]["client_code"] for r in load_records(require_file(args.diets)))
    raw_counts = Counter(d["client_code"] for d in load_records(require_file(args.raw_diets)))

    log = Counter()
    carry_by_field = Counter()
    medical_in_public = Counter()
    out, health = [], []
    for p in src:
        code = p["code"]
        empty = set(p) <= {"code", "n_dietas"}
        unmapped = p.get("sexo") is None
        act = p.get("nivel_actividad")
        act_reported = act not in (None, 0)
        age, height = p.get("edad"), p.get("altura_cm")
        suspicious = (age is not None and not 14 <= age <= 80) or (height is not None and not 140 <= height <= 210)
        carry_fields = [FREE_TEXT_EN[k] for k in FREE_TEXT_ES if p.get(k) and carryover(p[k])]
        for f in carry_fields:
            carry_by_field[f] += 1
        for k in ("objetivos", "deporte", "gustos_pos", "gustos_neg"):
            if p.get(k) and MEDICAL_RE.search(p[k]):
                medical_in_public[FREE_TEXT_EN[k]] += 1
        redacted: dict[str, str] = {}

        def txt(k):
            v = p.get(k)
            if not v:
                return None
            v2, changed = clean_rtf(nfc(v))
            if changed:
                log["rtf_residue_cleaned_public_text"] += 1
            if MEDICAL_RE.search(v2):
                redacted[FREE_TEXT_EN[k]] = v2      # moved to the private health file
                return None
            return v2

        rec = {
            "client_code": code,
            "sex": p.get("sexo"),
            "age": age,
            "age_bucket": age_bucket(age),
            "height_cm": height,
            "activity_level": act if act_reported else None,
            "activity_level_reported": act_reported,
            "is_athlete": p.get("atleta"),
            "goals": txt("objetivos"),
            "sport": txt("deporte"),
            "liked_foods": txt("gustos_pos"),
            "disliked_foods": txt("gustos_neg"),
            "has_allergies": bool(p.get("alergias")),
            "has_intolerances": bool(p.get("intolerancias")),
            "has_medical_restrictions": any(bool(p.get(k)) for k in HEALTH_FIELDS_ES),
            "diet_count": clean_counts.get(code, 0),
            "diet_count_raw": raw_counts.get(code, 0),
            "diet_count_stored": p.get("n_dietas"),
            "empty_profile": empty,
            "unmapped": unmapped,
            "suspicious_demographics": suspicious,
            "field_carryover_suspected": bool(carry_fields),
            "carryover_fields": carry_fields,
            "redacted_public_fields": sorted(redacted),
        }
        assert list(rec) == SCHEMA
        out.append(rec)
        if redacted:
            log["profiles_with_redacted_public_fields"] += 1
        if rec["has_medical_restrictions"] or redacted:
            health.append({"client_code": code,
                           "surgeries": p.get("operaciones"), "injuries": p.get("lesiones"),
                           "allergies": p.get("alergias"), "intolerances": p.get("intolerancias"),
                           "redacted_public_text": redacted,
                           "medical_terms_count": sum(len(MEDICAL_RE.findall(p[k])) for k in HEALTH_FIELDS_ES if p.get(k)),
                           "field_carryover_suspected": bool(carry_fields), "carryover_fields": carry_fields})
        log["profiles"] += 1
        log["empty_profile"] += empty
        log["unmapped"] += unmapped
        log["activity_level_zero_to_null"] += (act == 0)
        log["activity_level_absent"] += (act is None)
        log["suspicious_demographics"] += suspicious
        log["has_allergies"] += rec["has_allergies"]
        log["has_intolerances"] += rec["has_intolerances"]
        log["has_medical_restrictions"] += rec["has_medical_restrictions"]
        log["field_carryover_suspected"] += bool(carry_fields)
        log["diet_count_stored_ne_raw"] += (p.get("n_dietas") != raw_counts.get(code, 0))
        log["diet_count_raw_ne_clean"] += (raw_counts.get(code, 0) != clean_counts.get(code, 0))
        log["clients_with_clean_diets"] += clean_counts.get(code, 0) > 0
        log["clients_with_raw_diets"] += raw_counts.get(code, 0) > 0
        log["clients_with_stored_diets"] += (p.get("n_dietas") or 0) > 0

    write_jsonl(args.out_dir / "profiles.jsonl", out)
    write_jsonl(args.private_dir / "health_profiles.jsonl", health)
    profiles_with_free_text = sum(1 for p in src if any(p.get(k) for k in FREE_TEXT_ES))
    report = {"counts": dict(log), "health_profiles_written": len(health),
              "carryover_by_field": dict(carry_by_field.most_common()),
              "profiles_with_free_text": profiles_with_free_text,
              "medical_terms_in_public_free_text": dict(medical_in_public),
              "sex_distribution": dict(Counter(r["sex"] for r in out)),
              "schema": SCHEMA}
    write_json(args.out_dir / "build_profiles_log.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
