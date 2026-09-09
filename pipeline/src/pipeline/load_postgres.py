# -*- coding: utf-8 -*-
"""
E2.3 — Load the frozen dataset (dataset-v1 + E1 catalogue) into Postgres.

Input:  _dataset/profiles.jsonl, diets.jsonl, meals.jsonl, foods.json, diet_items.jsonl, validated_rules.json,
        rules_evaluability.json, archetypes.json          (never _private/)
Output: rows in client_profiles, foods, diets, meals, diet_items, rules, archetypes (all stamped with professional_id);
        _dataset/load_postgres_log.json (counts only)

Modes:
  --dry-run   build every row in memory and validate it against db/schema.sql (column names, NOT NULL, foreign keys,
              unique keys). Needs only the standard library: it is the test that runs without a database.
  --apply     same, then write to DATABASE_URL (psycopg 3, one transaction). --replace deletes the professional's rows first.

The embedding column is left NULL here; embed_corpus.py fills it (separate step, needs the e5 model).
Plausibility of demographics is a FLAG (suspicious_demographics), not a constraint: the frozen dataset is loaded as is.
Nothing is printed but counts.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import REPO_ROOT, DATASET_DIR, SRC_DIR  # noqa: E402
from pipeline import excluded  # noqa: E402
from pipeline.retrieval_text import build_retrieval_texts  # noqa: E402

SCHEMA_SQL = REPO_ROOT / "backend" / "db" / "schema.sql"
FLAGS = ("is_processed_sugar", "is_soft_drink", "is_salt", "is_fasting_compatible", "is_alcohol", "is_stimulant", "is_peanut",
         "is_tree_nut", "contains_lactose", "contains_gluten", "contains_soy", "contains_shellfish", "contains_egg", "contains_fish")
# keycloak/realm-fps.json -> users[username == "entrenador"].id. Single source of truth checked by
# backend/tests/architecture/test_api_surface_is_guarded.py against the realm and against migration 0011.
DEFAULT_KEYCLOAK_SUBJECT = "11111111-1111-4111-8111-111111111111"

TABLE_ORDER = ("client_profiles", "foods", "diets", "meals", "diet_items", "rules", "archetypes",
               "body_measurements", "lab_results")   # FK order; las dos ultimas se borran antes que sus perfiles


class Table:
    def __init__(self, name: str, columns: tuple[str, ...]):
        self.name, self.columns, self.rows = name, columns, []

    def add(self, **values):
        unknown = set(values) - set(self.columns)
        if unknown:
            raise KeyError(f"{self.name}: unknown columns {sorted(unknown)}")
        self.rows.append(tuple(values.get(c) for c in self.columns))


# ----------------------------------------------------------------------------------------------------------------- schema

def schema_columns(sql: str) -> dict[str, dict[str, dict]]:
    """{table: {column: {"not_null": bool, "default": bool}}} parsed from CREATE TABLE bodies (comments stripped first)."""
    stripped = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    out: dict[str, dict[str, dict]] = {}
    for m in re.finditer(r"CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*;", stripped, flags=re.S):
        table, body = m.group(1), m.group(2)
        cols: dict[str, dict] = {}
        depth, buf, parts = 0, "", []
        for ch in body:
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                parts.append(buf); buf = ""
            else:
                buf += ch
        parts.append(buf)
        for part in parts:
            tokens = part.split()
            if not tokens or tokens[0].upper() in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"):
                continue
            up = part.upper()
            cols[tokens[0]] = {"not_null": "NOT NULL" in up or "PRIMARY KEY" in up, "default": "DEFAULT" in up or "SERIAL" in up}
        out[table] = cols
    return out


def validate_against_schema(tables: dict[str, Table], schema: dict[str, dict[str, dict]]) -> list[str]:
    problems = []
    for t in tables.values():
        cols = schema[t.name]
        for c in t.columns:
            if c not in cols:
                problems.append(f"{t.name}.{c}: not in schema.sql")
        for c, spec in cols.items():
            if spec["not_null"] and not spec["default"] and c not in t.columns:
                problems.append(f"{t.name}.{c}: NOT NULL without DEFAULT but not loaded")
        for c, spec in cols.items():
            if spec["not_null"] and c in t.columns:
                i = t.columns.index(c)
                nulls = sum(r[i] is None for r in t.rows)
                if nulls:
                    problems.append(f"{t.name}.{c}: {nulls} NULL values in a NOT NULL column")
    return problems


# ------------------------------------------------------------------------------------------------------------------- rows

def jl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def jf(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def guard_text(text: str | None) -> str | None:
    """The pharmacological exclusion applied at the LOADING boundary, line by line.

    The v3 extractor already drops and redacts, but the guard cannot live only there: the frozen v2 dataset was
    built before it existed, and the contingency plan for the whole rebuild is "point ``FPS_DATASET_DIR`` back at
    v2". A guard that only runs at construction time makes that rollback reintroduce the defect -- the same shape
    as the ContextVar problem, where the protection sat in one place and the data left by another. Here nothing
    reaches the database, and therefore nothing reaches the composer's note consensus or the printed PDF, whichever
    dataset is active. The frozen files are not touched: this filters on the way in.

    Line by line because a rendered diet mixes two registers. "OBJETIVO: mejorar la resistencia a la insulina" is
    prose about the client's physiology and survives; "CENA: 2 PROVIRON | ensalada" is an instruction and does not.
    ``excluded.must_drop`` is what tells them apart.
    """
    if not text or not excluded.contains(text):
        return text
    return "\n".join(excluded.redact(line) if excluded.must_drop(line) else line for line in text.split("\n"))


def guard_report(dataset: Path) -> dict:
    """What the guard would change on this dataset, for the load log. Counts only -- never the offending text."""
    diets = jl(dataset / "diets.jsonl")
    meals = jl(dataset / "meals.jsonl")
    notes = [n for d in diets for n in d["notes"]]
    return {
        "notes_total": len(notes),
        "notes_mentioning_an_excluded_substance": sum(1 for n in notes if excluded.contains(n)),
        "notes_dropped": sum(1 for n in notes if excluded.must_drop(n)),
        "notes_dropped_with_a_dose": sum(1 for n in notes if excluded.prescribes(n)),
        "diet_texts_redacted": sum(1 for d in diets if guard_text(d["text"]) != d["text"]),
        "meal_texts_redacted": sum(1 for m in meals if guard_text(m["text"]) != m["text"]),
        "goal_texts_redacted": sum(1 for d in diets if guard_text(d["meta"]["goal_text"]) != d["meta"]["goal_text"]),
    }


def build_rows(dataset: Path, pid: str) -> dict[str, Table]:
    profiles, diets, meals, items = jl(dataset / "profiles.jsonl"), jl(dataset / "diets.jsonl"), jl(dataset / "meals.jsonl"), jl(dataset / "diet_items.jsonl")
    foods = jf(dataset / "foods.json")["foods"]
    rules = jf(dataset / "validated_rules.json")["rules"]
    evaluability = {e["id"]: e for e in jf(dataset / "rules_evaluability.json")}
    archetypes = jf(dataset / "archetypes.json")

    T = {
        "client_profiles": Table("client_profiles", ("client_code", "professional_id", "sex", "age", "age_bucket", "height_cm", "activity_level",
                                 "activity_level_reported", "is_athlete", "goals", "sport", "liked_foods", "disliked_foods", "has_allergies",
                                 "has_intolerances", "has_medical_restrictions", "body_type", "training_time", "diet_count", "diet_count_raw", "diet_count_stored", "empty_profile",
                                 "unmapped", "suspicious_demographics", "field_carryover_suspected", "carryover_fields", "redacted_public_fields", "is_corpus_case",
                                 "liked_food_ids")),
        "foods": Table("foods", ("id", "professional_id", "canonical_name", "family", "food_group", "secondary_group", "frequency", "attribute_source",
                       "synonyms", "keys") + FLAGS),
        "diets": Table("diets", ("id", "professional_id", "client_code", "goal", "goals", "goal_inferred", "goal_text", "method", "methods", "diet_version", "template_group_id",
                       "shared_diet", "shared_diet_signals", "template_clients", "has_intolerances", "notes", "text", "retrieval_text", "doc_date")),
        "meals": Table("meals", ("professional_id", "diet_id", "meal_slot", "position", "text", "item_count")),
        "diet_items": Table("diet_items", ("professional_id", "diet_id", "meal_slot", "position", "component_index", "food_id", "normalized_key", "raw_text",
                            "food_text", "quantity", "unit", "raw_unit", "alternative_group", "compound_item", "compound_group", "unmapped",
                            "unmapped_reason", "generic_assumption", "note")),
        "rules": Table("rules", ("id", "professional_id", "section", "kind", "statement", "condition", "n_group", "n_support", "prevalence_in_group",
                       "prevalence_global", "lift", "adjusted", "adjusted_method", "criteria", "confidence", "status", "evaluation_level", "enabled", "nature", "detail")),
        "archetypes": Table("archetypes", ("professional_id", "sex", "age_bucket", "goal", "diet_count", "client_count", "client_codes")),
        # 0015: the scale series of the CASE BASE. It was extracted in F3 and never loaded, so nothing downstream could
        # see it. The unique key is (professional, client, measured_at, source), so two readings of the same client on
        # the same instant and from the same device collapse into one -- that is the export's own identity, not a choice.
        "body_measurements": Table("body_measurements", ("professional_id", "client_code", "measured_at", "source", "weight_kg", "height_cm",
                                   "body_fat_pct", "water_pct", "bone_kg", "muscle_mass_kg", "physique_rating",
                                   "visceral_fat_rating", "metabolic_age", "basal_met_kcal")),
        # 0016: las mediciones analiticas del corpus. `source_type` es OBLIGATORIO para que un indice de dispositivo no
        # se pueda comparar con una magnitud de laboratorio creyendo que son lo mismo.
        "lab_results": Table("lab_results", ("professional_id", "client_code", "measured_at", "marker", "value", "unit",
                                             "ref_low", "ref_high", "note", "source", "source_type", "report_sha1",
                                             "values_unreliable")),
    }

    # 0017: los «gustos positivos» del cuestionario, resueltos contra el catalogo. Se guardan como texto libre en
    # `profiles.jsonl` y hasta ahora no salian de ahi. La resolucion es la misma idea que la de `FoodMatcher` en la
    # cartera, hecha aqui porque el corpus no pasa por el caso de uso del expediente.
    resolver = _food_resolver(foods)
    for p in profiles:                                                             # S1: the corpus is the CASE BASE, never the portfolio
        fijos = {c: p[c] for c in T["client_profiles"].columns
                 if c not in ("professional_id", "is_corpus_case", "liked_food_ids")}
        T["client_profiles"].add(professional_id=pid, is_corpus_case=True,
                                 liked_food_ids=sorted(resolver(p.get("liked_foods"))), **fijos)
    for f in foods:
        T["foods"].add(id=f["id"], professional_id=pid, canonical_name=f["canonical_name"], family=f["family"], food_group=f["group"],
                       secondary_group=f.get("secondary_group"), frequency=f["frequency"], attribute_source=f["attribute_source"],
                       synonyms=list(f["synonyms"]), keys=list(f["keys"]), **{k: bool(f["flags"][k]) for k in FLAGS})
    retrieval = build_retrieval_texts(diets, items)                                # E3.1: structured text that gets embedded
    slot_position: dict[tuple[str, str], int] = {}
    for d in diets:
        m = d["meta"]
        T["diets"].add(id=d["id"], professional_id=pid, client_code=m["client_code"], goal=m["goal"], goals=list(m["goals"]), goal_inferred=m["goal_inferred"],
                       goal_text=guard_text(m["goal_text"]), method=m.get("method"), methods=list(m.get("methods") or ()),
                       diet_version=m["diet_version"], template_group_id=m["template_group_id"], shared_diet=m["shared_diet"],
                       shared_diet_signals=list(m["shared_diet_signals"]), template_clients=list(m["template_clients"]), has_intolerances=m["has_intolerances"],
                       notes=[n for n in d["notes"] if not excluded.must_drop(n)], text=guard_text(d["text"]),
                       retrieval_text=guard_text(retrieval[d["id"]]["retrieval_text"]), doc_date=m.get("doc_date"))
        for pos, slot in enumerate(d["meals"]):                                  # dict preserves the order in which slots appear
            slot_position[(d["id"], slot)] = pos
    for m in meals:
        meta = m["meta"]
        T["meals"].add(professional_id=pid, diet_id=meta["diet_id"], meal_slot=meta["meal_slot"], position=slot_position[(meta["diet_id"], meta["meal_slot"])],
                       text=guard_text(m["text"]), item_count=meta["item_count"])
    for i in items:
        T["diet_items"].add(professional_id=pid, **{c: i[c] for c in T["diet_items"].columns if c != "professional_id"})
    for r in rules:
        ev = evaluability[r["id"]]
        detail = {k: r[k] for k in ("n_match", "by_group", "per_food", "n_support_adjusted", "n_group_adjusted") if k in r}
        detail["evaluability"] = {"evaluable": ev["evaluable"], "attributes": ev["attributes"]}
        T["rules"].add(id=r["id"], professional_id=pid, section=r["section"], kind=r["kind"], statement=r["statement"], condition=list(r["condition"] or ()),
                       n_group=r["n_group"], n_support=r["n_support"], prevalence_in_group=r.get("prevalence_in_group"), prevalence_global=r.get("prevalence_global"),
                       lift=r["lift"], adjusted=r["adjusted"], adjusted_method=r["adjusted_method"], criteria=r["criteria"], confidence=r["confidence"],
                       status=r["status"], evaluation_level=ev["level"], nature=r.get("nature"),             # prescriptive | descriptive (build_validated_rules)
                       enabled=(r["status"] == "kept" and r["confidence"] in ("high", "medium")),      # low confidence: off by default, switchable
                       detail=detail)
    for a in archetypes:
        T["archetypes"].add(professional_id=pid, sex=a["sex"], age_bucket=a["age_bucket"], goal=a["goal"], diet_count=a["diet_count"],
                            client_count=a["client_count"], client_codes=list(a["clients"]))
    known = {p["client_code"] for p in profiles}
    for row in body_measurement_rows(dataset, pid, known):
        T["body_measurements"].add(**row)
    for row in lab_result_rows(dataset, pid, known):
        T["lab_results"].add(**row)
    return T


def _food_resolver(foods: list[dict]):
    """Texto libre del cuestionario -> ids del catalogo. Conservador: nombre canonico o sinonimo exacto, o el nombre
    canonico contenido en el trozo cuando tiene al menos cinco letras. Lo que no resuelve, no se inventa."""
    por_nombre: dict[str, int] = {}
    for f in foods:
        por_nombre[f["canonical_name"].lower()] = f["id"]
        for syn in f.get("synonyms") or ():
            por_nombre.setdefault(str(syn).lower(), f["id"])
    largos = [(n, i) for n, i in por_nombre.items() if len(n) >= 5]

    def resolve(text) -> set[int]:
        if not text:
            return set()
        if isinstance(text, (list, tuple)):
            text = " , ".join(str(x) for x in text)
        out: set[int] = set()
        for trozo in str(text).replace(";", ",").replace("/", ",").split(","):
            t = trozo.strip().lower()
            if not t:
                continue
            if t in por_nombre:
                out.add(por_nombre[t])
                continue
            for nombre, fid in largos:
                if nombre in t:
                    out.add(fid)
                    break
        return out
    return resolve


def lab_result_rows(dataset: Path, pid: str, known_clients: set[str]) -> list[dict]:
    """Los valores de `lab_results.jsonl`, uno por fila.

    Un informe SIN fecha se carga igual pero con `measured_at` a NULL: no se puede afirmar que precediera a ninguna
    dieta, asi que la regla temporal lo deja fuera del motor por si sola. Inventarle una fecha seria la unica forma de
    que se colara. Un valor sin cliente conocido se descarta: la clave ajena lo rechazaria.
    """
    path = dataset / "lab_results.jsonl"
    if not path.exists():
        return []
    out, seen = [], set()
    for report in jl(path):
        code = report.get("client_code")
        if not code or code not in known_clients:
            continue
        for v in report.get("values") or ():
            name = v.get("indicator") or v.get("analyte")
            if not name or v.get("value") is None:
                continue
            key = (code, report.get("report_date"), report["report_sha1"], name)
            if key in seen:                       # el mismo parametro dos veces en el mismo informe: se queda el primero
                continue
            seen.add(key)
            out.append(dict(professional_id=pid, client_code=code, measured_at=report.get("report_date"),
                            marker=name[:200], value=float(v["value"]), unit=v.get("unit"),
                            ref_low=v.get("range_low"), ref_high=v.get("range_high"), note=None,
                            source="file", source_type=report["source_type"], report_sha1=report["report_sha1"],
                            values_unreliable=bool(report.get("values_unreliable"))))
    return out


def _num(value):
    """The scale export writes `basalMet` as a STRING. Anything unparseable becomes NULL, never zero."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def body_measurement_rows(dataset: Path, pid: str, known_clients: set[str]) -> list[dict]:
    """The scale series and the follow-up sheets, deduplicated on the table's own unique key.

    A reading whose client is not in `profiles.jsonl` is DROPPED, not invented: the foreign key would reject it and a
    measurement without a case is not usable by anything. The count of what is dropped goes to the log.
    """
    out, seen = [], set()
    for name, source in (("body_measurements.jsonl", None), ("body_measurements_followup.jsonl", None)):
        path = dataset / name
        if not path.exists():
            continue
        for row in jl(path):
            code, when = row.get("client_code"), row.get("date")
            if not code or not when or code not in known_clients:
                continue
            src = source or row.get("source") or "bascula"
            if (code, when, src) in seen:
                continue
            seen.add((code, when, src))
            out.append(dict(professional_id=pid, client_code=code, measured_at=when, source=src,
                            weight_kg=_num(row.get("weight_kg")), height_cm=row.get("height_cm"),
                            body_fat_pct=_num(row.get("fat_pct")), water_pct=_num(row.get("hydration_pct")),
                            bone_kg=_num(row.get("bone_mass_kg")), muscle_mass_kg=_num(row.get("muscle_mass_kg")),
                            physique_rating=row.get("physique_rating"), visceral_fat_rating=_num(row.get("visceral_fat_rating")),
                            metabolic_age=row.get("metabolic_age"), basal_met_kcal=int(_num(row.get("basal_met_kcal")))
                            if _num(row.get("basal_met_kcal")) is not None else None))
    return out


def validate_integrity(T: dict[str, Table]) -> list[str]:
    def col(t: str, c: str):
        i = T[t].columns.index(c)
        return [r[i] for r in T[t].rows]
    problems = []
    codes, diet_ids, food_ids = set(col("client_profiles", "client_code")), set(col("diets", "id")), set(col("foods", "id"))
    bad = sum(c not in codes for c in col("diets", "client_code"));                bad and problems.append(f"diets.client_code not in client_profiles: {bad}")
    bad = sum(d not in diet_ids for d in col("meals", "diet_id"));                 bad and problems.append(f"meals.diet_id not in diets: {bad}")
    bad = sum(d not in diet_ids for d in col("diet_items", "diet_id"));            bad and problems.append(f"diet_items.diet_id not in diets: {bad}")
    bad = sum(f is not None and f not in food_ids for f in col("diet_items", "food_id")); bad and problems.append(f"diet_items.food_id not in foods: {bad}")
    meal_keys = list(zip(col("meals", "diet_id"), col("meals", "meal_slot")))
    len(set(meal_keys)) != len(meal_keys) and problems.append("meals: duplicate (diet_id, meal_slot)")
    bad = len(set(zip(col("diet_items", "diet_id"), col("diet_items", "meal_slot"))) - set(meal_keys)); bad and problems.append(f"diet_items (diet, slot) without meal: {bad}")
    len(set(col("rules", "id"))) != len(T["rules"].rows) and problems.append("rules: duplicate id")
    len(set(col("foods", "canonical_name"))) != len(T["foods"].rows) and problems.append("foods: duplicate canonical_name")
    ak = list(zip(col("archetypes", "sex"), col("archetypes", "age_bucket"), col("archetypes", "goal")))
    len(set(ak)) != len(ak) and problems.append("archetypes: duplicate (sex, age_bucket, goal)")
    return problems


# ------------------------------------------------------------------------------------------------------------------ apply

def apply(T: dict[str, Table], database_url: str, pid: str, replace: bool) -> dict[str, int]:
    import psycopg                                   # lazy: --dry-run must work without it
    from psycopg.types.json import Jsonb
    counts = {}
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        # v2: the professional row carries the identity-provider subject that owns it. It is set HERE and not
        # only in migration 0011 because in a clean bootstrap the migrations run BEFORE any data is loaded:
        # `professionals` is still empty when 0011 runs, its UPDATE touches no row, and the API then answers
        # 403 to a perfectly valid token ("subject not mapped"). Whoever creates the row owns the mapping.
        subject = os.environ.get("PROFESSIONAL_KEYCLOAK_SUBJECT", DEFAULT_KEYCLOAK_SUBJECT)
        cur.execute("""INSERT INTO professionals (id, display_name, keycloak_subject) VALUES (%s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET keycloak_subject = COALESCE(professionals.keycloak_subject, EXCLUDED.keycloak_subject)""",
                    (pid, pid, subject))
        if replace:
            # S1 + dataset-v2: --replace reloads the CASE BASE, never the professional's portfolio. Deleting every
            # client_profiles row would take his clients with it (and fail on the saved_diets foreign key). Only corpus
            # profiles are removed; the portfolio (is_corpus_case = false) and its saved diets, records and labs stay.
            for t in reversed(TABLE_ORDER):
                if t == "client_profiles":
                    cur.execute("DELETE FROM client_profiles WHERE professional_id = %s AND is_corpus_case", (pid,))
                elif t == "lab_results":
                    # Igual que arriba: --replace recarga la BASE DE CASOS. Las analiticas de sus clientes de cartera
                    # las importo el (S4) y no son nuestras para borrarlas.
                    cur.execute("DELETE FROM lab_results lr USING client_profiles p WHERE lr.professional_id = %s "
                                "AND p.professional_id = lr.professional_id AND p.client_code = lr.client_code AND p.is_corpus_case", (pid,))
                elif t == "body_measurements":
                    # Same reasoning as client_profiles: --replace reloads the CASE BASE. The professional's own clients
                    # have readings in this table too (S3 import) and they are not ours to delete.
                    cur.execute("DELETE FROM body_measurements bm USING client_profiles p WHERE bm.professional_id = %s "
                                "AND p.professional_id = bm.professional_id AND p.client_code = bm.client_code AND p.is_corpus_case", (pid,))
                else:
                    cur.execute(f"DELETE FROM {t} WHERE professional_id = %s", (pid,))
        for t in TABLE_ORDER:
            table = T[t]
            cols = ", ".join(table.columns)
            marks = ", ".join("%s" for _ in table.columns)
            rows = table.rows
            if t == "rules":
                j = table.columns.index("detail")
                rows = [r[:j] + (Jsonb(r[j]),) + r[j + 1:] for r in rows]
            cur.executemany(f"INSERT INTO {t} ({cols}) VALUES ({marks})", rows)
            cur.execute(f"SELECT count(*) FROM {t} WHERE professional_id = %s", (pid,))
            counts[t] = cur.fetchone()[0]
        conn.commit()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=DATASET_DIR)
    ap.add_argument("--professional-id", default=os.environ.get("PROFESSIONAL_ID", "prof_001"))
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"), help="psycopg URL; the SQLAlchemy driver suffix (+psycopg) is accepted and stripped")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="build and validate rows; touch no database")
    mode.add_argument("--apply", action="store_true", help="write to --database-url / DATABASE_URL")
    ap.add_argument("--replace", action="store_true", help="with --apply: delete this professional's rows first")
    args = ap.parse_args()
    if args.database_url:
        args.database_url = args.database_url.replace("postgresql+psycopg://", "postgresql://")

    T = build_rows(args.dataset, args.professional_id)
    schema = schema_columns(SCHEMA_SQL.read_text(encoding="utf-8"))
    problems = validate_against_schema(T, schema) + validate_integrity(T)
    counts = {t: len(T[t].rows) for t in TABLE_ORDER}
    print(json.dumps({"mode": "dry-run" if args.dry_run else "apply", "professional_id": args.professional_id, "rows_built": counts,
                      "pharmacological_guard": guard_report(args.dataset), "problems": problems}, ensure_ascii=False, indent=1))
    if problems:
        return 1
    if args.apply:
        if not args.database_url:
            raise SystemExit("--database-url or DATABASE_URL is required with --apply")
        loaded = apply(T, args.database_url, args.professional_id, args.replace)
        # El log va al dataset, que es la ENTRADA de este script. Cuando la entrada es de solo lectura --el
        # contenedor de arranque la enlaza con `:ro` a proposito, porque cargar no debe poder modificar el corpus--
        # escribirlo falla, y no puede ser que la carga entera se de por fallida por no poder dejar una nota sobre
        # si misma. Se avisa y se sigue: el log es una comodidad, la carga es el trabajo.
        try:
            (args.dataset / "load_postgres_log.json").write_text(
                json.dumps({"professional_id": args.professional_id, "rows_built": counts, "rows_in_db": loaded},
                           ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            print(f"WARNING: no se pudo escribir load_postgres_log.json ({e.strerror}); el dataset es de solo lectura")
        print(json.dumps({"rows_in_db": loaded}, indent=1))
        if any(loaded[t] != counts[t] for t in TABLE_ORDER):
            print("WARNING: row counts in the database differ from the rows built (pre-existing rows? use --replace)")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
