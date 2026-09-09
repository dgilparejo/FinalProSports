# -*- coding: utf-8 -*-
"""
Phase 5 — Acceptance test suite for the anonymised / sanitised dataset.

Run with pytest (`python -m pytest pipeline/tests/test_dataset.py -q`) or, when pytest is not
installed, directly (`python pipeline/tests/test_dataset.py`): the built-in runner executes every
`test_*` function and exits non-zero on the first failure set.

Every test fails loudly if an input file is missing. The name dictionary comes from
_dataset/_private/name_map.json and is never printed.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent                    # pipeline/tests
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent / "src" / "data_tools"))
from pipeline.paths import data_dir, dataset_dir, repo_root  # noqa: E402

ROOT = data_dir()                        # processed-data tree (FPS_DATA_DIR), outside the code repository
DATASET = dataset_dir()                  # FPS_DATASET_DIR
PRIVATE = DATASET / "_private"
# Las cifras declaradas pertenecen AL DATASET que describen, no a un documento del arbol de codigo: las emite su
# propio constructor (pipeline_v3/provenance.write_declared_figures) al lado de los ficheros que cuenta. Antes vivian
# dentro de un .md publicado, de modo que la comprobacion de deriva dependia de que ese documento se entregara -- y
# apuntar a un documento fijo habria comparado los datos de una version del dataset con las cifras de otra, que es
# desacuerdo entre datasets distintos, no deriva.
FIGURES = DATASET / "declared_figures.json"
from pii_common import (  # noqa: E402
    DETECTORS, HEALTH_FIELDS_EN, ID_ALLOWED, alpha_tokens_not_allowed, custody_alternation, iter_strings,
    load_name_set, load_records, name_tokens_in, require_file,
)
from build_profiles import SCHEMA as PROFILE_SCHEMA  # noqa: E402

DIET_ID_RE = re.compile(r"^CLIENTE_\d{3}::(v\d{2,}|s\d{2,})(-\d+)?$")
def _allowed_slots() -> set[str]:
    """The domain's MealSlot is the single source of truth for the slot vocabulary.

    This set used to be a second, hand-kept copy of it, and it went out of date the moment dataset-v3 added the
    five slots the professional actually writes: the dataset was correct and the test said "unknown slot
    SUPLEMENTOS". A vocabulary written down twice is a vocabulary that will disagree with itself.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))
    from finalprosports.domain.model import MealSlot
    return {s.value for s in MealSlot} | {"PRE ENTRENO"}      # legacy literal still present in dataset-v1


ALLOWED_SLOTS = _allowed_slots()
TRUNCATED_SLOTS = {"MEDIA MA", "DESPU", "POST"}
# El trozo que nombra al profesional se lee de la CUSTODIA: un test que lleva su nombre dentro lo publica con el
# repositorio. Sin custodia no hay nada que comprobar de ESO, y `test_no_boilerplate...` lo dice en vez de callarse.
_CUSTODIA = custody_alternation()
BOILER = re.compile(r"\[TEL\]|\[EMAIL\]|mailto:|https?://|www\." + (f"|{_CUSTODIA}" if _CUSTODIA else ""), re.I)
HARD_PII = ("email", "phone", "dni", "nie", "iban", "full_date")

# ------------------------------------------------------------------ fixtures (plain functions, cached)
_cache: dict = {}


def load(name: str):
    if name not in _cache:
        _cache[name] = load_records(require_file(DATASET / name))
    return _cache[name]


def name_set():
    """Hashed dictionary (_private/name_tokens_hashed.json): the plaintext name map lives only in the encrypted custody.
    Reviewed false positives are embedded (hashed) in the same file."""
    if "names" not in _cache:
        _cache["names"] = load_name_set(None, PRIVATE / "name_tokens_hashed.json")
        _cache["fp"] = set()
    return _cache["names"], _cache["fp"]


def test_whole_tree_has_no_real_names():
    """Task B permanent audit: directory names, file names and text content of the code repository (the deliverable) and of
    the processed-data tree (anonymised client files)."""
    from audit_tree import DEFAULT_EXCLUDE, audit
    names, _ = name_set()
    for root in (repo_root(), ROOT):
        r = audit(root, names, set(DEFAULT_EXCLUDE))
        assert r["total_hits"] == 0, f"tree audit of {root.name} found {r['total_hits']} hits: {r['hits']} at {r['locations_top'][:5]}"


def strings(records, skip_fields=()):
    for rec in records:
        for field, s in iter_strings(rec):
            if field in skip_fields:
                continue
            yield field, s


# ------------------------------------------------------------------ PII
def test_no_names_in_identifiers_and_metadata():
    names, fp = name_set()
    for fname in ("diets.jsonl", "meals.jsonl", "profiles.jsonl"):
        for rec in load(fname):
            for field, s in iter_strings(rec):
                if field in ("text", "notes[]", "meals.<items>", "meta.goal_text", "goals", "sport", "liked_foods", "disliked_foods"):
                    continue   # free text is checked separately
                assert not name_tokens_in(s, names, extra_stop=fp), f"{fname}: name token in field {field}"
                if field in ("id", "client_code", "meta.client_code", "meta.diet_id") or field.startswith("meta.template_clients"):
                    assert not alpha_tokens_not_allowed(s), f"{fname}: not-allowed token in identifier field {field}"


def test_no_names_in_free_text():
    names, fp = name_set()
    for fname in ("diets.jsonl", "meals.jsonl", "profiles.jsonl"):
        hits = Counter()
        for field, s in strings(load(fname)):
            for t in name_tokens_in(s, names, extra_stop=fp):
                hits[field] += 1
        assert not hits, f"{fname}: reviewed-name tokens remain in free text: {dict(hits)}"


def test_no_hard_pii_patterns():
    for fname in ("diets.jsonl", "meals.jsonl", "profiles.jsonl", "discarded_empty.jsonl"):
        for field, s in strings(load(fname)):
            for det in HARD_PII:
                assert not DETECTORS[det].search(s), f"{fname}: {det} pattern in field {field}"


def test_no_boilerplate_or_links_in_text_and_notes():
    for rec in load("diets.jsonl"):
        assert not BOILER.search(rec["text"]), f"{rec['id']}: signature/link residue in text"
        for n in rec["notes"]:
            assert not BOILER.search(n), f"{rec['id']}: boilerplate note survived"
    for rec in load("meals.jsonl"):
        assert not BOILER.search(rec["text"]), f"{rec['id']}: link residue in meal text"


def test_no_rtf_or_form_residue():
    rx_rtf, rx_form = DETECTORS["rtf_residue"], DETECTORS["form_line"]
    for fname in ("diets.jsonl", "meals.jsonl", "profiles.jsonl"):
        for field, s in strings(load(fname)):
            assert not rx_rtf.search(s), f"{fname}: RTF residue in {field}"
            assert not rx_form.search(s), f"{fname}: form line in {field}"


def test_no_health_free_text_in_public_profiles():
    for rec in load("profiles.jsonl"):
        for k in HEALTH_FIELDS_EN:
            assert k not in rec, f"{rec['client_code']}: health free-text field {k} leaked into profiles.jsonl"
        for k in ("has_allergies", "has_intolerances", "has_medical_restrictions"):
            assert isinstance(rec[k], bool)


# ------------------------------------------------------------------ labels & slots
def test_no_raw_regex_in_goal_labels_or_reports():
    rx = DETECTORS["raw_regex_label"]
    for rec in load("diets.jsonl"):
        assert not rx.search(rec["meta"]["goal"]) and "/" not in rec["meta"]["goal"] and " " not in rec["meta"]["goal"]
        for g in rec["meta"]["goals"]:
            assert not rx.search(g) and re.fullmatch(r"[a-z0-9_]+", g), f"goal label not snake_case: {g}"
    for md in ("rules.md", "rules_conditions.md", "archetypes.md", "INDEX.md", "validated_rules.md"):
        text = require_file(DATASET / md).read_text(encoding="utf-8")
        assert "[oó]" not in text and "MEDIA MA:" not in text and "DESPU:" not in text, f"{md}: raw label residue"


def test_meal_slots_expanded_and_known():
    for rec in load("diets.jsonl"):
        for slot in rec["meals"]:
            assert slot not in TRUNCATED_SLOTS, f"{rec['id']}: truncated slot {slot}"
            assert slot in ALLOWED_SLOTS, f"{rec['id']}: unknown slot {slot}"
        for line in rec["text"].split("\n")[1:]:
            head = line.split(":", 1)[0]
            assert head == "NOTAS" or head in ALLOWED_SLOTS, f"{rec['id']}: unexpected text header {head}"


# ------------------------------------------------------------------ identifiers
def test_diet_ids_unique_and_well_formed():
    ids = [r["id"] for r in load("diets.jsonl")]
    assert len(ids) == len(set(ids)), "duplicate diet ids"
    for i in ids:
        assert DIET_ID_RE.match(i), f"bad id format: {i}"
    for r in load("diets.jsonl"):
        assert i.startswith(r["meta"]["client_code"]) or r["id"].startswith(r["meta"]["client_code"])


def test_meal_ids_derive_from_diet_ids():
    diet_ids = {r["id"] for r in load("diets.jsonl")}
    seen = set()
    for r in load("meals.jsonl"):
        assert r["id"] not in seen, f"duplicate meal id {r['id']}"
        seen.add(r["id"])
        base, slot = r["id"].rsplit("::", 1)
        assert base in diet_ids and slot in ALLOWED_SLOTS and r["meta"]["diet_id"] == base and r["meta"]["meal_slot"] == slot
        assert not alpha_tokens_not_allowed(r["id"]) or all(t in ID_ALLOWED for t in alpha_tokens_not_allowed(r["id"]))


def test_ids_are_stable_against_private_map():
    id_map = json.loads(require_file(PRIVATE / "id_map.json").read_text(encoding="utf-8"))
    for fname in ("diets.jsonl", "discarded_empty.jsonl"):
        for r in load(fname):
            assert r["id"] in id_map, f"{r['id']} missing from id_map.json (ids not stable)"
    for g in load("duplicates.json"):
        kept = g["kept"] if isinstance(g["kept"], list) else [g["kept"]]     # v1 keeps one diet; the v2 re-split keeps every member
        assert all(k in id_map for k in kept) and all(d in id_map for d in g["dropped"])
    # Not a literal: the invariant is that the map RESOLVES every id the dataset mentions, in the corpus, in the
    # discards and in the duplicates ledger. Pinning the count pins the dataset instead of the property.
    mentioned = {r["id"] for r in load("diets.jsonl")} | {r["id"] for r in load("discarded_empty.jsonl")}
    for g in load("duplicates.json"):
        mentioned |= set(g["kept"] if isinstance(g["kept"], list) else [g["kept"]]) | set(g["dropped"])
    assert mentioned <= set(id_map), sorted(mentioned - set(id_map))[:8]


# ------------------------------------------------------------------ content quality
def test_text_min_length_and_non_empty_meals():
    for r in load("diets.jsonl"):
        assert len(r["text"]) >= 80, f"{r['id']}: text shorter than 80 chars"
        assert r["meals"] and all(r["meals"].values()), f"{r['id']}: empty meals"


def test_duplicate_meal_sets_are_recorded_as_template_groups():
    """sanitize DROPS a duplicate and keeps one; the dataset-v2 slot re-split revealed five more shared templates and KEEPS both
    members (dropping them would change the leave-one-out query set). Either way, no duplicate may go unrecorded: every repeated
    meal set must belong to a template group, which is what retrieval excludes."""
    diets = load("diets.jsonl")
    by_hash = defaultdict(list)
    for r in diets:
        by_hash[hashlib.sha1(json.dumps(r["meals"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()].append(r)
    unrecorded = [h for h, group in by_hash.items() if len(group) > 1 and len({r["meta"]["template_group_id"] for r in group}) != 1]
    assert not unrecorded, f"{len(unrecorded)} duplicate meal sets are not recorded as a template group"
    for h, group in by_hash.items():
        if len(group) > 1:
            assert group[0]["meta"]["template_group_id"], f"duplicate meal set {h[:8]} without template_group_id"


def test_template_groups_recorded():
    """Every cross-client duplicate group is recorded and reachable from the diets: v1 groups (sanitize) mark the single diet that
    was kept; v2 groups (the slot re-split) mark every member because none was dropped."""
    tpl = [r for r in load("diets.jsonl") if r["meta"]["template_group_id"]]
    groups = [g for g in load("duplicates.json") if not g["same_client"]]
    ids = {g["template_group_id"] for g in groups}
    marked = {r["meta"]["template_group_id"] for r in tpl}
    assert marked <= ids | {g["template_group_id"] for g in load("duplicates.json")}, sorted(marked - ids)
    assert ids <= marked, f"template groups with no diet marked: {sorted(ids - marked)}"
    for r in tpl:
        assert len(r["meta"]["template_clients"]) >= 1 and r["meta"]["client_code"] in r["meta"]["template_clients"]


def test_flags_present_and_typed():
    for r in load("diets.jsonl"):
        m = r["meta"]
        for k in ("goal_inferred", "activity_level_reported", "suspicious_demographics", "shared_diet", "has_intolerances"):
            assert isinstance(m[k], bool), f"{r['id']}: flag {k} missing or not boolean"
        assert m["activity_level"] != 0, f"{r['id']}: activity_level 0 must be null"
        assert "intolerances" not in m, "raw intolerance text leaked into diet meta"


# ------------------------------------------------------------------ profiles
def test_profiles_uniform_schema():
    rows = load("profiles.jsonl")
    assert len(rows) == declared_figures()["profiles"]      # the dataset's own declared figure, not a literal
    for r in rows:
        # Every v2 field present, and every row shaped identically. NOT equality: the rebuild ADDS fields (the
        # questionnaire and scale blocks), which the schema-parity rule allows and requires -- what it forbids is
        # renaming or dropping one. Equality here would fail precisely because the rebuild kept its promise.
        assert set(PROFILE_SCHEMA) <= set(r), f"{r.get('client_code')}: missing {sorted(set(PROFILE_SCHEMA) - set(r))}"
        assert list(r) == list(rows[0]), f"{r.get('client_code')}: key order differs from the other profiles"
        assert r["activity_level"] != 0
        assert not r["empty_profile"] or (r["sex"] is None and r["goals"] is None)
    codes = [r["client_code"] for r in rows]
    assert len(codes) == len(set(codes))


def test_profile_diet_counts_match_clean_corpus():
    counts = Counter(r["meta"]["client_code"] for r in load("diets.jsonl"))
    for r in load("profiles.jsonl"):
        assert r["diet_count"] == counts.get(r["client_code"], 0)


# ------------------------------------------------------------------ report consistency
def declared_figures() -> dict:
    return json.loads(require_file(FIGURES).read_text(encoding="utf-8"))


def test_report_figures_match_data():
    f = declared_figures()
    san = json.loads(require_file(DATASET / "sanitize_log.json").read_text(encoding="utf-8"))
    prof_log = DATASET / "build_profiles_log.json"      # v2 only: the rebuild derives the figure from the profiles
    prof = json.loads(prof_log.read_text(encoding="utf-8")) if prof_log.exists() else None
    loo = json.loads(require_file(DATASET / "loo_eligibility.json").read_text(encoding="utf-8"))
    vr = json.loads(require_file(DATASET / "validated_rules.json").read_text(encoding="utf-8"))
    rules = load("rules.json")
    diets, meals, profiles = load("diets.jsonl"), load("meals.jsonl"), load("profiles.jsonl")
    actual = {
        "input_diets": san["counts"]["input_diets"],
        "discarded_empty": len(load("discarded_empty.jsonl")),
        "duplicate_groups": len(load("duplicates.json")),
        "duplicates_dropped": sum(len(g["dropped"]) for g in load("duplicates.json")),
        "template_groups": sum(1 for g in load("duplicates.json") if not g["same_client"]),
        "output_diets": len(diets),
        "output_meals": len(meals),
        "clients_with_diets": len({r["meta"]["client_code"] for r in diets}),
        "profiles": len(profiles),
        "empty_profiles": sum(1 for p in profiles if p["empty_profile"]),
        "unmapped_profiles": sum(1 for p in profiles if p["unmapped"]),
        "health_profiles": len(load_records(PRIVATE / "health_profiles.jsonl")),
        "goal_inferred": sum(1 for r in diets if r["meta"]["goal_inferred"]),
        "shared_diet": sum(1 for r in diets if r["meta"]["shared_diet"]),
        "notes_before": san["notes"]["total_before"],
        "notes_after": san["notes"]["total_after"],            # over the 1.183 cleaned diets (see test_notes_after_matches_log)
        "notes_after_in_final_diets": sum(len(r["notes"]) for r in diets),
        "slot_sections_expanded": san["counts"]["slot_sections_expanded"],
        "items_with_links_cleaned": san["counts"]["items_with_links_cleaned"],
        "distinct_rules": len(rules),
        "validated_rules": len(vr["rules"]),
        "validated_kept": sum(1 for r in vr["rules"] if r["status"] == "kept"),
        "validated_retired": sum(1 for r in vr["rules"] if r["status"] == "retired"),
        "loo_eligible_clients": loo["all_diets"]["eligible_ge2"]["clients"],
        "loo_eligible_complete_clients": loo["all_diets"]["eligible_ge2_complete_demographics"]["clients"],
        "loo_queries_complete": loo["all_diets"]["eligible_ge2_complete_demographics"]["queries"],
        "loo_pairs_complete": loo["all_diets"]["eligible_ge2_complete_demographics"]["pairs"],
        "loo_excl_template_complete_clients": loo["excluding_template_groups"]["eligible_ge2_complete_demographics"]["clients"],
        "loo_excl_template_complete_queries": loo["excluding_template_groups"]["eligible_ge2_complete_demographics"]["queries"],
        "field_carryover_profiles": (prof["counts"]["field_carryover_suspected"] if prof
                                    else sum(1 for p in profiles if p.get("field_carryover_suspected"))),
    }
    mismatches = {k: (f.get(k), actual[k]) for k in actual if f.get(k) != actual[k]}
    assert not mismatches, f"report figures differ from data (declared, actual): {mismatches}"


def test_validated_rules_carry_a_nature_with_the_majority_cut():
    """Fase 9 (B): every rule is prescriptive or descriptive; prescriptive <=> kept/policy AND followed by the majority of its group
    (STRICTLY > 0.5; avoided pattern < 0.5 for avoidance rules). The cut is the same constant the domain uses (Rule.nature fallback).

    The comparison is strict because a majority is more than half: on the rebuilt corpus a rule landed on exactly 52 of 104 and
    the validator then demanded it of 100 % of proposals, failing 14 of the 21 golden profiles over a coin flip."""
    vr = json.loads(require_file(DATASET / "validated_rules.json").read_text(encoding="utf-8"))
    cut = vr["nature_split"]["majority_prevalence"]
    assert cut == 0.5
    domain_rule = (Path(__file__).resolve().parents[2] / "backend" / "src" / "finalprosports" / "domain" / "model" / "rule.py").read_text(encoding="utf-8")   # code root, not the data tree
    assert f"MAJORITY_PREVALENCE = {cut}" in domain_rule
    seen = Counter()
    for r in vr["rules"]:
        assert r["nature"] in ("prescriptive", "descriptive"), r["id"]
        seen[r["nature"]] += 1
        if r["status"] == "policy":
            expected = "prescriptive"
        elif r["status"] != "kept" or r["kind"] == "behaviour" or r.get("prevalence_in_group") is None:
            expected = "descriptive"
        else:
            followed = 1 - r["prevalence_in_group"] if r["avoid"] else r["prevalence_in_group"]
            expected = "prescriptive" if followed > cut else "descriptive"
        assert r["nature"] == expected, r["id"]
    assert set(vr["nature_split"]["prescriptive"]) == {r["id"] for r in vr["rules"] if r["nature"] == "prescriptive"}
    assert seen["prescriptive"] > 0 and seen["descriptive"] > 0


def test_notes_after_matches_log():
    san = json.loads(require_file(DATASET / "sanitize_log.json").read_text(encoding="utf-8"))
    assert san["notes"]["total_after"] == san["notes"]["actions"]["kept"]
    assert san["notes"]["total_before"] == sum(san["notes"]["actions"].values())


# ------------------------------------------------------------------ fallback runner
if __name__ == "__main__":
    # Esta suite describe el CORPUS CONGELADO: sin él no hay nada que comprobar. En el árbol público el corpus no
    # existe a propósito (es dato de salud), así que se SALTA diciendo por qué, en vez de fallar veintiuna veces y
    # ensuciar la única señal que importa allí: que el árbol no lleva datos personales.
    if not (DATASET / "diets.jsonl").exists() or not PRIVATE.exists():
        print(f"SKIP  test_dataset: no hay corpus privado en {DATASET} "
              f"(esta suite describe el dataset congelado; en el árbol público no existe por diseño)")
        sys.exit(0)
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    sys.exit(1 if failed else 0)
