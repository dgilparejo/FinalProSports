"""F3 -- questionnaires: every labelled field, each in its own column (``profiles.jsonl``).

The v2 profile had 24 fields and most were empty: sex and height 76 %, age 70 %, activity level 43 %, sport 25 %,
liked foods 23 %, disliked foods 21 %, plus 93 empty profiles. The cause was upstream -- the questionnaires are
mostly ``.doc`` files that v2 read as raw bytes -- and the labels that were never read at all (OPERACIONES, GUSTOS,
VICIOS ALIMENTICIOS, FUMA, BEBE ALCOHOL, TIEMPO ENTRENANDO, LOGROS DEPORTIVOS, HORARIOS) are exactly the ones the
enumeration in :mod:`pipeline_v3.vocab` finds in over a hundred documents each.

Field policy, following the v2 split that the tree audit enforces:

* public ``profiles.jsonl`` carries demographics, measurements, preferences and **booleans** for health;
* health free text (surgeries, injuries, allergies, intolerances, medication) goes to
  ``_private/health_profiles.jsonl``, never to the public file;
* a label that no rule claims is kept verbatim in ``extra_fields`` with its own name, so an unknown question is
  counted and readable instead of dropped (principle 4).

Values stay in Spanish exactly as written; only field names are English.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import convert, identity, paths, vocab
else:
    from . import convert, identity, paths, vocab

# label pattern -> (dataset field, kind). ``kind`` decides where the value may be written.
#   public      -> profiles.jsonl verbatim
#   health      -> a boolean in profiles.jsonl, the text only in the private file
#   identity    -> never stored at all (it is the person's name, phone, e-mail, login)
_FIELD_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"^(NOMBRE|APELLIDOS?|NOMBRE Y APELLIDOS|USUARIO|CONTRASENA|PASSWORD|TELEFONO|MOVIL|"
                r"CORREO( ELECTRONICO)?|E?-?MAIL|DIRECCION|DNI|FECHA NACIMIENTO|F NACIMIENTO)$"), "-", "identity"),
    (re.compile(r"^(SEXO|GENERO)$"), "sex", "public"),
    (re.compile(r"^EDAD$"), "age", "public"),
    (re.compile(r"^(ALTURA|ESTATURA|TALLA)$"), "height_cm", "public"),
    (re.compile(r"^PESO$"), "weight_kg", "public"),
    (re.compile(r"^PESO INICIAL$"), "initial_weight_kg", "public"),
    (re.compile(r"^PESO (OBJETIVO|DESEADO|IDEAL)$"), "target_weight_kg", "public"),
    (re.compile(r"^CINTURA$"), "waist_cm", "public"),
    (re.compile(r"^CUELLO$"), "neck_cm", "public"),
    (re.compile(r"^(MUNECA|MUNECAS)$"), "wrist_cm", "public"),
    (re.compile(r"^(CADERA|CADERAS)$"), "hip_cm", "public"),
    (re.compile(r"^(TIPO FISIONOMIA|FISIONOMIA|COMPLEXION|SOMATOTIPO)$"), "body_type", "public"),
    (re.compile(r"^(OBJETIVOS?|META)$"), "goals", "public"),
    (re.compile(r"^(TIPO/?S? DE DEPORTE( QUE PRACTICA)?|DEPORTES?( QUE PRACTICA)?|"
                r"QUE DEPORTE PRACTICA)$"), "sport", "public"),
    (re.compile(r"^(TIEMPO ENTRENANDO|CUANTO TIEMPO LLEVA ENTRENANDO|EXPERIENCIA)$"), "training_time", "public"),
    (re.compile(r"^(LOGROS DEPORTIVOS( Y MARCAS)?|MARCAS( PERSONALES)?)$"), "sport_achievements", "public"),
    (re.compile(r"^(NIVEL DE ACTIVIDAD|ACTIVIDAD( FISICA| DIARIA)?)$"), "activity_level", "public"),
    (re.compile(r"^GUSTOS POSITIVOS$"), "liked_foods", "public"),
    (re.compile(r"^GUSTOS NEGATIVOS$"), "disliked_foods", "public"),
    (re.compile(r"^VICIOS ALIMENTICIOS$"), "food_vices", "public"),
    (re.compile(r"^(FUMA|FUMADOR)$"), "smokes", "public"),
    (re.compile(r"^(BEBE ALCOHOL|ALCOHOL)$"), "drinks_alcohol", "public"),
    (re.compile(r"^HORARIOS? (DE )?TRABAJO$"), "work_schedule", "public"),
    (re.compile(r"^HORARIOS? (DE )?ENTRENAMIENTO$"), "training_schedule", "public"),
    (re.compile(r"^(HORAS DE SUENO|SUENO|DESCANSO NOCTURNO)$"), "sleep_hours", "public"),
    (re.compile(r"^FECHA (DE )?PRIMERA CONSULTA$"), "first_consultation_date", "public"),
    (re.compile(r"^(SUPLEMENTOS( QUE TOMA)?|SUPLEMENTACION)$"), "own_supplements", "public"),
    # health: boolean in public, text in private
    (re.compile(r"^(OPERACIONES|OPERAC IONES|CIRUGIAS?|INTERVENCIONES)$"), "surgeries", "health"),
    (re.compile(r"^(LESIONES( O MOLESTIAS( FRECUENTES)?)?|MOLESTIAS)$"), "injuries", "health"),
    (re.compile(r"^ALERGIAS?$"), "allergies", "health"),
    (re.compile(r"^INTOLERANCIAS?$"), "intolerances", "health"),
    (re.compile(r"^(MEDICACION|MEDICAMENTOS|TRATAMIENTO( MEDICO)?|PATOLOGIAS?|ENFERMEDADES?)$"),
     "medical_restrictions", "health"),
]

HEALTH_FIELDS = ("surgeries", "injuries", "allergies", "intolerances", "medical_restrictions")
PUBLIC_FIELDS = [
    "client_code", "sex", "age", "age_bucket", "height_cm", "weight_kg", "initial_weight_kg", "target_weight_kg",
    "waist_cm", "neck_cm", "wrist_cm", "hip_cm", "body_type", "activity_level", "activity_level_reported",
    "is_athlete", "goals", "sport", "training_time", "sport_achievements", "liked_foods", "disliked_foods",
    "food_vices", "smokes", "drinks_alcohol", "work_schedule", "training_schedule", "sleep_hours",
    "own_supplements", "first_consultation_date",
    "has_allergies", "has_intolerances", "has_medical_restrictions", "has_medication_or_pathology",
    "has_surgeries", "has_injuries",
    "diet_count", "diet_count_raw", "diet_count_stored", "empty_profile", "unmapped",
    "suspicious_demographics", "field_carryover_suspected", "carryover_fields", "redacted_public_fields",
    "extra_fields", "questionnaire_count", "has_scale_trajectory", "scale_reading_count", "lab_report_count",
    "field_sources",
]

_NUM = re.compile(r"(\d+(?:[.,]\d+)?)")
_YESNO_YES = re.compile(r"^\s*(SI|SÍ|S|YES|A VECES|OCASIONAL|POCO|BASTANTE|MUCHO|SOCIAL|FIN DE SEMANA)", re.I)
_YESNO_NO = re.compile(r"^\s*(NO|N|NUNCA|NINGUNA|NINGUNO|NADA|-|N/?A)\s*[.]?\s*$", re.I)
_EMPTY = re.compile(r"^[\s.\-_/]*$|^(NO|NINGUNA|NINGUNO|NADA|N/?A|-{1,}|SIN|SIN NADA)[.\s]*$", re.I)


def _number(value: str, low: float, high: float) -> float | None:
    for match in _NUM.finditer(value.replace(",", ".")):
        try:
            number = float(match.group(1))
        except ValueError:
            continue
        if low <= number <= high:
            return number
    return None


def _tristate(value: str) -> bool | None:
    if not value or _EMPTY.match(value):
        return None
    if _YESNO_NO.match(value):
        return False
    if _YESNO_YES.match(value):
        return True
    return None


def _has_content(value) -> bool:
    return bool(value) and isinstance(value, str) and not _EMPTY.match(value)


def _sex(value: str) -> str | None:
    folded = vocab.fold(value)
    if re.search(r"\bMUJER\b|\bFEMENIN|\bF\b|\bCHICA\b", folded):
        return "F"
    if re.search(r"\bHOMBRE\b|\bMASCULIN|\bM\b|\bVARON\b|\bCHICO\b", folded):
        return "M"
    return None


def _age_bucket(age: float | None) -> str:
    if age is None:
        return "edad_NA"
    for low, high in ((0, 25), (25, 35), (35, 45), (45, 55), (55, 200)):
        if low <= age < high:
            return f"edad_{low}_{high}" if high < 200 else "edad_55_mas"
    return "edad_NA"


# Several labelled fields on one line: "Nombre: X   Sexo: Masculino   Edad: 25" is the header of every lab report
# and of many questionnaire tables. Reading only the first colon per line loses every field but the first.
_INLINE_PAIR = re.compile(
    r"(?P<label>[A-Za-zÁÉÍÓÚÑÜáéíóúñü][A-Za-zÁÉÍÓÚÑÜáéíóúñü /]{1,30}?)\s*:\s*"
    r"(?P<value>(?:(?!\s{2,}[A-Za-zÁÉÍÓÚÑÜáéíóúñü][A-Za-zÁÉÍÓÚÑÜáéíóúñü /]{1,30}?\s*:)[^\n])*)"
)


def _label_value_pairs(line: str):
    """Yield every ``label: value`` pair on the line, not just the first."""
    first = vocab.split_header(line)
    if first is None:
        return
    matches = list(_INLINE_PAIR.finditer(line))
    if len(matches) <= 1:
        yield first[0], first[1]
        return
    for match in matches:
        yield match.group("label").strip(), match.group("value").strip()


def parse_questionnaire(text: str) -> tuple[dict, dict, dict]:
    """Return ``(public, health_text, extra)`` for one questionnaire document."""
    public: dict = {}
    health: dict = {}
    extra: dict = {}
    for line in text.split("\n"):
        for head, rest in _label_value_pairs(line):
            normalised = vocab.normalise_header(head)
            value = rest.strip()
            if not value or _EMPTY.match(value):
                continue
            matched = False
            for pattern, field, kind in _FIELD_RULES:
                if not pattern.match(normalised):
                    continue
                matched = True
                if kind == "identity":
                    break                       # never stored
                if kind == "health":
                    health.setdefault(field, value)
                else:
                    public.setdefault(field, value)
                break
            if not matched:
                extra.setdefault(normalised, value)
    return public, health, extra


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    manifest = [json.loads(line) for line in (out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()]
    registry = identity.load_or_build_registry(paths.sources_root())

    questionnaires: dict[str, list[dict]] = collections.defaultdict(list)
    for row in manifest:
        if row.get("label") == "questionnaire" and row.get("status") == "ok" and row.get("client_code"):
            questionnaires[row["client_code"]].append(row)

    diet_counts = collections.Counter()
    diets_path = out_dir / "diets.jsonl"
    if diets_path.exists():
        for line in diets_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                diet_counts[json.loads(line)["meta"]["client_code"]] += 1

    scale_counts = collections.Counter()
    scale_path = out_dir / "body_measurements.jsonl"
    if scale_path.exists():
        for line in scale_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                scale_counts[json.loads(line)["client_code"]] += 1

    scale_demo_path = out_dir / "scale_demographics.json"
    scale_demographics = json.loads(scale_demo_path.read_text(encoding="utf-8")) if scale_demo_path.exists() else {}

    lab_counts = collections.Counter()
    for row in manifest:
        if row.get("label") in ("lab_clinical", "lab_bioanalyzer") and row.get("client_code"):
            lab_counts[row["client_code"]] += 1

    profiles: list[dict] = []
    private_rows: list[dict] = []
    extra_freq: collections.Counter = collections.Counter()

    # The same labels turn up outside the questionnaire: diets often open with a small profile block, and every lab
    # report states sex and age in its header. Those documents are a lower-priority source for the demographic
    # fields only -- preferences and health belong to the questionnaire, where the professional actually asked.
    DEMOGRAPHIC_FALLBACK = {"sex", "age", "height_cm", "weight_kg", "waist_cm", "neck_cm", "wrist_cm",
                            "hip_cm", "body_type", "initial_weight_kg"}
    other_docs: dict[str, list[dict]] = collections.defaultdict(list)
    for row in manifest:
        if (row.get("status") == "ok" and row.get("client_code")
                and row.get("label") in ("diet", "lab_clinical", "lab_bioanalyzer", "followup")):
            other_docs[row["client_code"]].append(row)

    for code in sorted(registry.codes.values()):
        merged_public: dict = {}
        merged_health: dict = {}
        merged_extra: dict = {}
        for row in questionnaires.get(code, []):
            public, health, extra = parse_questionnaire(convert.cached_text(row["sha1"]))
            for key, value in public.items():
                merged_public.setdefault(key, value)
            for key, value in health.items():
                merged_health.setdefault(key, value)
            for key, value in extra.items():
                merged_extra.setdefault(key, value)
        for row in other_docs.get(code, []):
            public, _health, _extra = parse_questionnaire(convert.cached_text(row["sha1"]))
            for key, value in public.items():
                if key in DEMOGRAPHIC_FALLBACK:
                    merged_public.setdefault(key, value)
        for key in merged_extra:
            extra_freq[key] += 1

        # The questionnaire is not the only source of demographics, and for these four fields it is the worse one:
        # it carries no SEXO label at all and states an age in under 1 % of documents, while the scale export gives
        # sex, height, activity level and a birthdate for every account it matched. The questionnaire still wins
        # where it has a value; the scale fills the gap, and field_sources records which answered.
        scale_entry = scale_demographics.get(code, {})
        sources: dict[str, str] = {}

        def take(field: str, questionnaire_value, scale_key: str | None = None):
            if questionnaire_value not in (None, ""):
                sources[field] = "questionnaire"
                return questionnaire_value
            value = scale_entry.get(scale_key or field)
            if value not in (None, ""):
                sources[field] = "bascula"
                return value
            return None

        def activity_level(questionnaire_value):
            """0 is a real activity level (sedentary), so it must not double as "absent".

            The scale export writes 0 both for "sedentary" and for "never filled in", and v2 converts a bare 0 to
            null for exactly that reason. Passing it through would corrupt a retrieval feature: 232 diets would
            claim a measured sedentary client where there is no measurement at all.
            """
            value = take("activity_level", questionnaire_value)
            if value in (0, "0", 0.0):
                sources.pop("activity_level", None)
                return None
            return value

        scrub = registry.scrub_for_dataset
        merged_public = {k: (scrub(v) if isinstance(v, str) else v) for k, v in merged_public.items()}
        merged_extra = {k: (scrub(v) if isinstance(v, str) else v) for k, v in merged_extra.items()}
        merged_health = {k: (scrub(v) if isinstance(v, str) else v) for k, v in merged_health.items()}

        age = take("age", _number(merged_public.get("age", ""), 10, 99))
        height = take("height_cm", _number(merged_public.get("height_cm", ""), 120, 220))
        profile = {
            "client_code": code,
            "sex": take("sex", _sex(merged_public.get("sex", ""))),
            "age": age,
            "age_bucket": _age_bucket(age),
            "height_cm": height,
            "weight_kg": _number(merged_public.get("weight_kg", ""), 30, 250),
            "initial_weight_kg": _number(merged_public.get("initial_weight_kg", ""), 30, 250),
            "target_weight_kg": _number(merged_public.get("target_weight_kg", ""), 30, 250),
            "waist_cm": _number(merged_public.get("waist_cm", ""), 40, 200),
            "neck_cm": _number(merged_public.get("neck_cm", ""), 20, 70),
            "wrist_cm": _number(merged_public.get("wrist_cm", ""), 10, 30),
            "hip_cm": _number(merged_public.get("hip_cm", ""), 50, 200),
            "body_type": merged_public.get("body_type"),
            "activity_level": activity_level(merged_public.get("activity_level")),
            "activity_level_reported": "activity_level" in merged_public,
            "is_athlete": take("is_athlete", None),
            "goals": merged_public.get("goals"),
            "sport": merged_public.get("sport"),
            "training_time": merged_public.get("training_time"),
            "sport_achievements": merged_public.get("sport_achievements"),
            "liked_foods": merged_public.get("liked_foods"),
            "disliked_foods": merged_public.get("disliked_foods"),
            "food_vices": merged_public.get("food_vices"),
            "smokes": _tristate(merged_public.get("smokes", "")),
            "drinks_alcohol": _tristate(merged_public.get("drinks_alcohol", "")),
            "work_schedule": merged_public.get("work_schedule"),
            "training_schedule": merged_public.get("training_schedule"),
            "sleep_hours": _number(merged_public.get("sleep_hours", ""), 3, 14),
            "own_supplements": merged_public.get("own_supplements"),
            "first_consultation_date": merged_public.get("first_consultation_date"),
            "has_allergies": _has_content(merged_health.get("allergies")),
            "has_intolerances": _has_content(merged_health.get("intolerances")),
            # v2 defines this as the OR of the four health free-text fields, not as a medication field. Keeping a
            # narrower definition made it read 1,5 % against v2's 47,4 % and looked like catastrophic data loss in
            # the comparison when it was a definition mismatch. The medication field is kept separately.
            "has_medical_restrictions": any(_has_content(merged_health.get(k))
                                            for k in ("surgeries", "injuries", "allergies", "intolerances",
                                                      "medical_restrictions")),
            "has_medication_or_pathology": _has_content(merged_health.get("medical_restrictions")),
            "has_surgeries": _has_content(merged_health.get("surgeries")),
            "has_injuries": _has_content(merged_health.get("injuries")),
            "diet_count": diet_counts.get(code, 0),
            "diet_count_raw": diet_counts.get(code, 0),
            "diet_count_stored": diet_counts.get(code, 0),
            "empty_profile": False,           # computed below, from the RESULT rather than from the inputs
            "unmapped": bool(merged_extra),
            "suspicious_demographics": bool(age and height and (age < 14 or height < 130)),
            "field_carryover_suspected": False,
            "carryover_fields": [],
            "redacted_public_fields": [],
            "extra_fields": merged_extra,
            "questionnaire_count": len(questionnaires.get(code, [])),
            "has_scale_trajectory": scale_counts.get(code, 0) >= 2,
            "scale_reading_count": scale_counts.get(code, 0),
            "lab_report_count": lab_counts.get(code, 0),
            "field_sources": sources,
        }
        # `empty_profile` means the profile carries NO information about the client, and that has to be read off the
        # finished profile: a field can arrive from the scale export or from the diets after the questionnaire
        # blocks were merged, and judging emptiness by the inputs alone marked 19 profiles empty while they
        # already had a sex and a goal. The bookkeeping fields are excluded -- they are always present.
        _BOOKKEEPING = ("client_code", "empty_profile", "unmapped", "suspicious_demographics",
                        "field_carryover_suspected", "carryover_fields", "redacted_public_fields",
                        "diet_count", "diet_count_raw", "diet_count_stored", "questionnaire_count",
                        "scale_reading_count", "lab_report_count", "has_scale_trajectory", "field_sources",
                        "activity_level_reported", "age_bucket")
        profile["empty_profile"] = not any(v for k, v in profile.items() if k not in _BOOKKEEPING)

        profiles.append(profile)
        if merged_health:
            private_rows.append({"client_code": code, **merged_health})

    with open(out_dir / "profiles.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for record in profiles:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    private = out_dir / "_private"
    private.mkdir(parents=True, exist_ok=True)
    with open(private / "health_profiles.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for record in private_rows:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    total = len(profiles)
    coverage = {}
    for field in PUBLIC_FIELDS:
        if field in ("client_code", "extra_fields", "carryover_fields", "redacted_public_fields", "field_sources"):
            continue
        filled = sum(1 for p in profiles if p.get(field) not in (None, "", False, [], {}, 0))
        coverage[field] = round(100 * filled / total, 1) if total else 0.0

    summary = {
        "clients": total,
        "clients_with_a_questionnaire": sum(1 for p in profiles if p["questionnaire_count"]),
        "questionnaire_documents": sum(len(v) for v in questionnaires.values()),
        "empty_profiles": sum(1 for p in profiles if p["empty_profile"]),
        "profiles_with_extra_fields": sum(1 for p in profiles if p["extra_fields"]),
        "coverage_pct": coverage,
        "extra_field_labels": extra_freq.most_common(60),
        "private_health_rows": len(private_rows),
        "field_source_counts": {
            field: dict(collections.Counter(p["field_sources"].get(field) for p in profiles
                                            if p["field_sources"].get(field)))
            for field in ("sex", "age", "height_cm", "activity_level", "is_athlete")
        },
    }
    (out_dir / "extract_profiles_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                       encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    argparse.ArgumentParser(description="F3: extract profiles from the questionnaires").parse_args()
    summary = build()
    printable = {k: v for k, v in summary.items() if k != "extra_field_labels"}
    print(json.dumps(printable, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
