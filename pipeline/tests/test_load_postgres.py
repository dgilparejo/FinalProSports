# -*- coding: utf-8 -*-
"""Acceptance tests of the Postgres loader that run WITHOUT a database: the rows built from the frozen dataset must fit
db/schema.sql exactly (columns, NOT NULL, foreign keys, unique keys). Skipped when the dataset is not present."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import DATASET_DIR  # noqa: E402

DATASET = DATASET_DIR


def _jl(path):
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
from pipeline.load_postgres import SCHEMA_SQL, TABLE_ORDER, build_rows, schema_columns, validate_against_schema, validate_integrity  # noqa: E402

HAVE_DATASET = (DATASET_DIR / "diets.jsonl").exists()
SCHEMA = schema_columns(SCHEMA_SQL.read_text(encoding="utf-8"))
_TABLES = build_rows(DATASET_DIR, "prof_test") if HAVE_DATASET else None


def test_schema_parser_sees_every_table_and_professional_id():
    assert set(SCHEMA) == {"professionals", "gaps", "saved_diets", "client_records", "body_measurements", "lab_results", *TABLE_ORDER}, sorted(SCHEMA)     # gaps, saved_diets, client_records, body_measurements are written at runtime, not loaded
    for t in TABLE_ORDER:
        assert SCHEMA[t]["professional_id"]["not_null"], t
    assert SCHEMA["diets"]["embedding"] == {"not_null": False, "default": False}
    assert SCHEMA["client_profiles"]["age"]["not_null"] is False          # plausibility is a flag, not a CHECK


def test_rows_fit_the_schema():
    if not HAVE_DATASET:
        return
    assert validate_against_schema(_TABLES, SCHEMA) == []


def test_referential_and_unique_integrity():
    if not HAVE_DATASET:
        return
    assert validate_integrity(_TABLES) == []


def test_frozen_dataset_counts():
    if not HAVE_DATASET:
        return
    # Against the dataset's OWN declared figures, not a literal. A frozen count pinned to one dataset turns into a
    # false alarm the moment another is active: it stops testing "the loader built a row per record" and starts
    # testing "you are using dataset-v2". The invariant that matters is that every record in the files became a row.
    counts = {t: len(_TABLES[t].rows) for t in TABLE_ORDER}
    expected = {
        "client_profiles": len(_jl(DATASET / "profiles.jsonl")),
        "foods": len(json.loads((DATASET / "foods.json").read_text(encoding="utf-8"))["foods"]),
        "diets": len(_jl(DATASET / "diets.jsonl")),
        "meals": len(_jl(DATASET / "meals.jsonl")),
        "diet_items": len(_jl(DATASET / "diet_items.jsonl")),
        "rules": len(json.loads((DATASET / "validated_rules.json").read_text(encoding="utf-8"))["rules"]),
        "archetypes": len(json.loads((DATASET / "archetypes.json").read_text(encoding="utf-8"))),
        # La bascula (0015) es la unica tabla cuyo numero de filas NO es el numero de registros del fichero: se
        # descartan las lecturas de clientes que no estan en `profiles.jsonl` (la clave ajena las rechazaria) y las
        # que empatan en (cliente, fecha, origen), que es la clave unica de la propia tabla. El invariante que queda
        # es el que se puede afirmar: ni una fila de mas, y ninguna inventada.
        "body_measurements": len(_expected_measurements()),
        # 0016: una fila por VALOR, no por informe, y con la misma clase de descarte que la bascula (cliente
        # desconocido, valor nulo, o el mismo parametro dos veces en el mismo informe).
        "lab_results": len(_expected_lab_values()),
    }
    assert counts == expected, (counts, expected)


def _expected_lab_values() -> set:
    known = {json.loads(line)["client_code"] for line in _jl(DATASET / "profiles.jsonl")}
    keys = set()
    path = DATASET / "lab_results.jsonl"
    if not path.exists():
        return keys
    for line in _jl(path):
        r = json.loads(line)
        if r.get("client_code") not in known:
            continue
        for v in r.get("values") or ():
            name = v.get("indicator") or v.get("analyte")
            if name and v.get("value") is not None:
                keys.add((r["client_code"], r.get("report_date"), r["report_sha1"], name))
    return keys


def _expected_measurements() -> set:
    known = {json.loads(line)["client_code"] for line in _jl(DATASET / "profiles.jsonl")}
    keys = set()
    for name in ("body_measurements.jsonl", "body_measurements_followup.jsonl"):
        path = DATASET / name
        if not path.exists():
            continue
        for line in _jl(path):
            r = json.loads(line)
            if r.get("client_code") in known and r.get("date"):
                keys.add((r["client_code"], r["date"], r.get("source") or "bascula"))
    return keys


def test_every_row_is_stamped_with_the_professional():
    if not HAVE_DATASET:
        return
    for t in TABLE_ORDER:
        i = _TABLES[t].columns.index("professional_id")
        assert all(r[i] == "prof_test" for r in _TABLES[t].rows), t


def test_rules_enabled_by_default_are_kept_and_not_low_confidence():
    if not HAVE_DATASET:
        return
    cols = _TABLES["rules"].columns
    s, c, e, lvl = cols.index("status"), cols.index("confidence"), cols.index("enabled"), cols.index("evaluation_level")
    for r in _TABLES["rules"].rows:
        assert r[e] == (r[s] == "kept" and r[c] in ("high", "medium")), r[:1]
        assert r[lvl] in ("item", "note"), r[lvl]
    assert sum(r[e] for r in _TABLES["rules"].rows) > 0
    n = cols.index("nature")
    assert all(r[n] in ("prescriptive", "descriptive") for r in _TABLES["rules"].rows)
    assert 0 < sum(r[n] == "prescriptive" for r in _TABLES["rules"].rows) < len(_TABLES["rules"].rows)


def test_meal_positions_follow_the_order_of_slots_in_the_diet():
    if not HAVE_DATASET:
        return
    cols = _TABLES["meals"].columns
    d, p = cols.index("diet_id"), cols.index("position")
    per_diet: dict[str, list[int]] = {}
    for r in _TABLES["meals"].rows:
        per_diet.setdefault(r[d], []).append(r[p])
    assert all(sorted(v) == list(range(len(v))) for v in per_diet.values())


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    if not HAVE_DATASET:
        print("NOTE  dataset not present: data-dependent tests were skipped")
    sys.exit(1 if failed else 0)
