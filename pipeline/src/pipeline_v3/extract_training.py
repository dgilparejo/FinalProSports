"""F3 -- training plans, follow-up sheets and the scale screenshots.

Three small extractions the brief asks for, kept together because each is a handful of fields:

* **training**: weekly frequency and the kind of work, from the plan documents. Frequency is counted as the number
  of distinct day headings the plan actually uses, which is what the professional writes; the type comes from the
  exercise vocabulary present.
* **follow-up sheets**: where they carry weights or measurements they go into the same schema as the scale export,
  with ``source: seguimiento`` so the two are never confused.
* **scale screenshots**: NOT read (no OCR, by instruction). What is reported is whether the clients who have them
  already have a trajectory in the scale export -- redundant -- or not, which is the data owner's decision to make.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import convert, paths
else:
    from . import convert, paths

_DAYS = ("LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO")
_DAY_RE = re.compile(r"\b(" + "|".join(_DAYS) + r")\b")
_SESSION_RE = re.compile(r"^\s*(?:DIA|D[IÍ]A|SESION|SESI[OÓ]N|RUTINA)\s*([A-Z]|\d{1,2})\b", re.M)
_WEEK_FREQ = re.compile(r"(\d)\s*(?:D[IÍ]AS?|SESIONES?|VECES)\s*(?:POR|A LA|/)\s*SEMANA", re.I)

TRAINING_TYPES = {
    "fuerza": re.compile(r"\b(FUERZA|HIPERTROFIA|PESAS|MUSCULACION|SERIES|REPETICIONES|REPS)\b"),
    "cardio": re.compile(r"\b(CARDIO|CINTA|ELIPTICA|CARRERA|CORRER|BICI|REMO ERGOMETRO|CAMINAR)\b"),
    "hiit": re.compile(r"\b(HIIT|INTERVALOS|TABATA|SPRINTS?)\b"),
    "crossfit": re.compile(r"\b(CROSSFIT|WOD|AMRAP|EMOM)\b"),
    "movilidad": re.compile(r"\b(MOVILIDAD|ESTIRAMIENTOS?|FLEXIBILIDAD|YOGA|PILATES)\b"),
}
MUSCLE_GROUPS = ("PECHO", "ESPALDA", "PIERNA", "PIERNAS", "HOMBRO", "HOMBROS", "BICEPS", "TRICEPS",
                 "GEMELOS", "ABDOMEN", "ABDOMINALES", "GLUTEO", "GLUTEOS", "DORSAL")

_WEIGHT_ROW = re.compile(r"(?:PESO|KG)\D{0,12}(\d{2,3}[.,]?\d?)\s*(?:KG)?", re.I)
_FAT_ROW = re.compile(r"(?:GRASA|%\s*GRASA)\D{0,12}(\d{1,2}[.,]?\d?)\s*%?", re.I)
_DATE = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})(?!\d)")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


def parse_training(text: str) -> dict:
    folded = fold(text)
    days = sorted({d for d in _DAY_RE.findall(folded)}, key=_DAYS.index)
    sessions = {m.group(1) for m in _SESSION_RE.finditer(folded)}
    stated = _WEEK_FREQ.search(folded)
    frequency = int(stated.group(1)) if stated else (len(days) or len(sessions) or None)
    types = sorted(name for name, pattern in TRAINING_TYPES.items() if pattern.search(folded))
    groups = sorted({g for g in MUSCLE_GROUPS if re.search(rf"\b{g}\b", folded)})
    return {
        "weekly_frequency": frequency,
        "frequency_source": "stated" if stated else ("day_headings" if days else
                                                     ("session_headings" if sessions else None)),
        "days_named": days,
        "session_count": len(sessions) or None,
        "training_types": types,
        "muscle_groups": groups,
    }


def parse_followup(text: str) -> list[dict]:
    """Weights and fat percentages from a follow-up sheet, one record per dated row."""
    out = []
    for line in text.split("\n"):
        date_match = _DATE.search(line)
        if not date_match:
            continue
        weight = _WEIGHT_ROW.search(line)
        fat = _FAT_ROW.search(line)
        if not weight and not fat:
            continue
        day, month, year = (int(g) for g in date_match.groups())
        year += 2000 if year < 70 else 1900 if year < 100 else 0
        if not (1990 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31):
            continue
        record = {"date": f"{year:04d}-{month:02d}-{day:02d}", "source": "seguimiento"}
        if weight:
            value = float(weight.group(1).replace(",", "."))
            if 30 <= value <= 250:
                record["weight_kg"] = value
        if fat:
            value = float(fat.group(1).replace(",", "."))
            if 3 <= value <= 70:
                record["fat_pct"] = value
        if len(record) > 2:
            out.append(record)
    return out


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    manifest = [json.loads(l) for l in (out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip()]

    plans: list[dict] = []
    for row in manifest:
        if row.get("label") != "training" or row.get("status") != "ok" or not row.get("client_code"):
            continue
        parsed = parse_training(convert.cached_text(row["sha1"]))
        parsed.update({"client_code": row["client_code"], "source_sha1": row["sha1"],
                       "doc_date": row.get("name_date")})
        plans.append(parsed)
    plans.sort(key=lambda p: (p["client_code"], p["doc_date"] or ""))
    with open(out_dir / "training_plans.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for plan in plans:
            handle.write(json.dumps(plan, ensure_ascii=False) + "\n")

    followups: list[dict] = []
    followup_docs = 0
    for row in manifest:
        if row.get("label") != "followup" or row.get("status") != "ok" or not row.get("client_code"):
            continue
        followup_docs += 1
        for record in parse_followup(convert.cached_text(row["sha1"])):
            record["client_code"] = row["client_code"]
            followups.append(record)
    if followups:
        with open(out_dir / "body_measurements_followup.jsonl", "w", encoding="utf-8", newline="\n") as handle:
            for record in sorted(followups, key=lambda r: (r["client_code"], r["date"])):
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Scale screenshots: counted, never read.
    image_clients = collections.Counter()
    bean_images = 0
    for row in manifest:
        if row.get("status") != "skipped_media" or row.get("detected") != "image":
            continue
        if row.get("unit") == "bean":
            bean_images += 1
            continue
        if row.get("client_code"):
            image_clients[row["client_code"]] += 1

    scale_clients = set()
    scale_path = out_dir / "body_measurements.jsonl"
    if scale_path.exists():
        for line in scale_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                scale_clients.add(json.loads(line)["client_code"])
    covered = {c for c in image_clients if c in scale_clients}

    summary = {
        "training_plans": len(plans),
        "training_clients": len({p["client_code"] for p in plans}),
        "with_a_weekly_frequency": sum(1 for p in plans if p["weekly_frequency"]),
        "frequency_histogram": dict(sorted(collections.Counter(
            p["weekly_frequency"] for p in plans if p["weekly_frequency"]).items())),
        "type_histogram": dict(collections.Counter(t for p in plans for t in p["training_types"]).most_common()),
        "followup_documents": followup_docs,
        "followup_measurement_rows": len(followups),
        "followup_clients": len({r["client_code"] for r in followups}),
        "screenshot_images": sum(image_clients.values()),
        "screenshot_clients": len(image_clients),
        "screenshot_clients_already_in_the_scale_export": len(covered),
        "screenshot_clients_NOT_in_the_scale_export": sorted(set(image_clients) - covered),
        "screenshot_note": ("no OCR was run, by instruction. The clients not covered by the scale export are the "
                            "only ones where reading the images could add a trajectory; that is the owner's call"),
    }
    (out_dir / "training_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                               encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    argparse.ArgumentParser(description="F3: training plans, follow-up sheets, screenshot census").parse_args()
    summary = build()
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "screenshot_clients_NOT_in_the_scale_export"}, ensure_ascii=False, indent=1))
    print(f"\nscreenshot clients NOT covered by the scale export: "
          f"{len(summary['screenshot_clients_NOT_in_the_scale_export'])}")


if __name__ == "__main__":
    main()
