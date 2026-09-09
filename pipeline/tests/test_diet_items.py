# -*- coding: utf-8 -*-
"""Acceptance tests of E1 outputs: foods.json (catalogue + attributes) and diet_items.jsonl.

  * no canonical_name starts with a preposition (the legacy 'sopera de aceite...' bug)
  * no canonical_name is exactly 30 characters long or cut mid-word (the legacy food[:30] bug)
  * every unit belongs to the closed domain.Unit set
  * items sharing an alternative_group (or compound_group) belong to the same diet and meal slot
  * every rule of validated_rules.json is evaluable (rules_evaluability.json) with the catalogue attributes
  * mapping coverage >= 85 % with the explicit denominator (all food components)
  * every food has a group and every flag of domain.FoodFlags; excluded substances never appear as foods
  * generic_assumption is boolean and only set on mapped items
Run with pytest or `python pipeline/tests/test_diet_items.py`.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import DATASET_DIR, REPO_ROOT, DATA_DIR  # noqa: E402
from pipeline.build_food_catalog import normalize_key  # noqa: E402
from finalprosports.domain.model import FoodFlags, FoodGroup, Unit  # noqa: E402

PREPOSITIONS = ("de ", "del ", "sopera de ", "soperas de ", "con ", "en ", "al ", "a la ", "para ", "por ")
UNITS = {u.value for u in Unit}
GROUPS = {g.value for g in FoodGroup}
FLAGS = set(FoodFlags().__dict__)


def load(name):
    p = DATASET_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"Required input file not found: {p}")
    if p.suffix == ".jsonl":
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(p.read_text(encoding="utf-8"))


def foods():
    return load("foods.json")["foods"]


def test_canonical_names_do_not_start_with_a_preposition():
    bad = [f["canonical_name"] for f in foods() if f["canonical_name"].lower().startswith(PREPOSITIONS)]
    assert not bad, bad


def test_canonical_names_are_not_truncated():
    bad30 = [f["canonical_name"] for f in foods() if len(f["canonical_name"]) == 30]
    assert not bad30, f"exactly 30 characters (legacy truncation): {bad30}"
    # a name cut mid-word ends in a 1-char fragment; single letters/digits are legitimate only after vitamina/omega/complejo
    bad_cut = [f["canonical_name"] for f in foods()
               if len(f["canonical_name"].split()[-1]) < 2 and not re.search(r"\b(vitamina|omega|complejo) [a-z0-9]$", f["canonical_name"])]
    assert not bad_cut, bad_cut
    assert not any(f["canonical_name"] != f["canonical_name"].strip() for f in foods())
    # the legacy bug sliced strings at 30 chars regardless of word boundaries: no canonical or key may end mid-word
    for f in foods():
        for k in f["keys"]:
            assert len(k) != 30 or k.endswith(tuple("aeiouslnrzdy")), f"key of 30 chars ending mid-word: {k!r}"


def test_units_belong_to_the_closed_set():
    bad = {r["unit"] for r in load("diet_items.jsonl") if r["unit"] not in UNITS}
    assert not bad, bad


def test_groups_share_diet_and_slot():
    alt, comp = defaultdict(set), defaultdict(set)
    for r in load("diet_items.jsonl"):
        if r["alternative_group"]:
            alt[r["alternative_group"]].add((r["diet_id"], r["meal_slot"]))
        if r["compound_group"]:
            comp[r["compound_group"]].add((r["diet_id"], r["meal_slot"]))
    assert all(len(v) == 1 for v in alt.values()), "alternative_group spans several diets/slots"
    assert all(len(v) == 1 for v in comp.values()), "compound_group spans several diets/slots"
    for g in alt:
        assert g.startswith(next(iter(alt[g]))[0]), "alternative_group id does not embed the diet id"


def test_every_rule_is_evaluable():
    rules = load("validated_rules.json")["rules"]
    matrix = {m["id"]: m for m in load("rules_evaluability.json")}
    missing = [r["id"] for r in rules if r["id"] not in matrix or not matrix[r["id"]]["evaluable"]]
    assert not missing, f"rules without an evaluation path: {missing}"
    assert all(m["level"] in ("item", "note") for m in matrix.values())
    # the attribute names mentioned by item-level rules exist in the catalogue
    attrs = FLAGS | {"group", "family", "canonical"}
    for m in matrix.values():
        if m["level"] == "item":
            assert any(a in m["attributes"] for a in attrs) or "canonical" in m["attributes"], m


def test_coverage_at_least_85_percent_with_explicit_denominator():
    log = load("normalize_diets_log.json")
    assert log["records"] == log["mapped"] + log["unmapped_no_canonical"] + log["descriptor_only"] + log["excluded_substance"]
    assert log["coverage_pct"] >= 85.0, log["coverage_pct"]
    cat = load("foods.json")["summary"]
    assert cat["food_components_denominator"] == log["records"]


def test_catalogue_attributes_complete_and_excluded_absent():
    excluded = json.loads((DATA_DIR / "excluded_substances.json").read_text(encoding="utf-8"))
    ex_keys = {normalize_key(k) for e in excluded["substances"] for k in [e["name"]] + e["keys"]}
    for f in foods():
        assert f["group"] in GROUPS, f["canonical_name"]
        assert f["secondary_group"] in GROUPS | {None}
        assert set(f["flags"]) == FLAGS, f["canonical_name"]
        assert f["family"], f"{f['canonical_name']} has no family"
        assert normalize_key(f["canonical_name"]) not in ex_keys, f"excluded substance in catalogue: {f['canonical_name']}"
        assert not any(k in ex_keys for k in f["keys"]), f"excluded key mapped to {f['canonical_name']}"
    assert 200 <= len(foods()) <= 600


def test_generic_assumption_flag_is_consistent():
    for r in load("diet_items.jsonl"):
        assert isinstance(r["generic_assumption"], bool)
        if r["generic_assumption"]:
            assert not r["unmapped"]
        assert r["unmapped"] == (r["food_id"] is None)
        if r["unmapped"]:
            assert r["unmapped_reason"] in ("no_canonical", "descriptor_only", "excluded_substance")


if __name__ == "__main__":
    # ESTA SUITE DESCRIBE EL ETL DEL CORPUS PRIVADO. En un árbol sin corpus —el repositorio público lleva una base de
    # casos sintética y ningún artefacto de la extracción— no hay nada que comprobar, así que se SALTA diciendo por
    # qué en vez de fallar y tapar la única señal que importa allí. Mismo criterio que `test_dataset.py`.
    from pipeline.paths import dataset_dir as _dd
    if not (_dd() / "normalize_diets_log.json").exists():
        print(f"SKIP  test_diet_items: no hay artefactos de la extracción en {_dd()} "
              f"(esta suite describe el ETL del corpus; el árbol público no lo lleva por diseño)")
        sys.exit(0)

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {str(e)[:300]}")
    sys.exit(1 if failed else 0)
