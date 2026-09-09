# -*- coding: utf-8 -*-
"""
E1.4 — Structured diet items: one record per (diet, meal slot, component) mapped to the food catalogue.

Input:  _dataset/parsed_items.jsonl (E1.1), _dataset/foods.json (E1.2 + E1.3 attributes),
        pipeline/data/excluded_substances.json
Output: _dataset/diet_items.jsonl, _dataset/normalize_diets_log.json

Record:
  {"diet_id": "CLIENTE_016::v05", "meal_slot": "CENA", "position": 2, "component_index": 0,
   "food_id": 42, "canonical_name": "pollo", "family": "ave", "group": "PROTEIN",
   "raw_text": "200 gr Pollo (cualquier parte)", "food_text": "Pollo", "quantity": 200, "unit": "g", "raw_unit": null,
   "alternative_group": null, "compound_item": false, "compound_group": null,
   "unmapped": false, "unmapped_reason": null, "generic_assumption": false, "note": "cualquier parte"}

Only food components are emitted (instructions and signature noise are counted in the log).
`generic_assumption` marks components resolved through one of the twelve high-volume generic keys declared in the
synonym audit (vitamina -> multivitamínico, pescado -> pescado blanco, ...): the overlap metric can be reported
with and without them. Components of excluded substances are emitted as unmapped (reason "excluded_substance").
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR  # noqa: E402
from pipeline.build_food_catalog import (  # noqa: E402
    DESCRIPTOR_ONLY, EXCLUDED_PATH, excluded_index, load_json, normalize_key, resolve, resolve_excluded,
)

# the twelve high-volume interpretations of generic words (declared in the report; flag generic_assumption)
GENERIC_KEYS = {"vitamina", "pescado", "cereal", "aminoacido", "proteina", "batido", "blanco", "harina", "aceite", "oliva", "carne", "azul"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parsed", type=Path, default=DATASET_DIR / "parsed_items.jsonl")
    ap.add_argument("--foods", type=Path, default=DATASET_DIR / "foods.json")
    ap.add_argument("--excluded", type=Path, default=EXCLUDED_PATH)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "diet_items.jsonl")
    args = ap.parse_args()
    for p in (args.parsed, args.foods, args.excluded):
        if not p.exists():
            raise FileNotFoundError(f"Required input file not found: {p}")
    foods = load_json(args.foods)["foods"]
    by_name = {f["canonical_name"]: f for f in foods}
    key_idx = {k: f["canonical_name"] for f in foods for k in f["keys"]}
    ex_idx = excluded_index(load_json(args.excluded))
    rows = [json.loads(l) for l in args.parsed.read_text(encoding="utf-8").splitlines() if l.strip()]

    log = Counter()
    unmapped_keys = Counter()
    comp_index: Counter = Counter()
    out = []
    for r in rows:
        if r.get("is_noise"):
            log["noise_skipped"] += 1
            continue
        if r["is_instruction"]:
            log["instructions_skipped"] += 1
            continue
        if not r["food_text"]:
            log["no_food_text_skipped"] += 1
            continue
        key = normalize_key(r["food_text"])
        rec = {
            "diet_id": r["diet_id"], "meal_slot": r["meal_slot"], "position": r["position"],
            "component_index": comp_index[(r["diet_id"], r["meal_slot"], r["position"])],
            "food_id": None, "canonical_name": None, "family": None, "group": None,
            "normalized_key": key,           # grouping key BEFORE synonym resolution: fine-grained overlap metric
            "raw_text": r["raw_text"], "food_text": r["food_text"], "quantity": r["quantity"], "unit": r["unit"], "raw_unit": r["raw_unit"],
            "alternative_group": r["alternative_group"], "compound_item": r["compound_item"], "compound_group": r["compound_group"],
            "unmapped": True, "unmapped_reason": None, "generic_assumption": False, "note": r["note"],
        }
        comp_index[(r["diet_id"], r["meal_slot"], r["position"])] += 1
        ex = resolve_excluded(key, ex_idx) if key else None
        if not key or key in DESCRIPTOR_ONLY:
            rec["unmapped_reason"] = "descriptor_only"
            log["descriptor_only"] += 1
        elif ex:
            rec["unmapped_reason"] = "excluded_substance"
            log["excluded_substance"] += 1
        else:
            canon = resolve(key, key_idx)
            if canon is None:
                rec["unmapped_reason"] = "no_canonical"
                unmapped_keys[key] += 1
                log["unmapped"] += 1
            else:
                f = by_name[canon]
                rec.update(food_id=f["id"], canonical_name=canon, family=f.get("family"), group=f.get("group"), unmapped=False, unmapped_reason=None)
                # generic assumption: the key itself, or the prefix that resolved it, is one of the twelve generic words
                toks = key.split()
                resolved_via = key if key in key_idx else next((" ".join(toks[:n]) for n in range(len(toks) - 1, 0, -1) if " ".join(toks[:n]) in key_idx), key)
                if resolved_via in GENERIC_KEYS:
                    rec["generic_assumption"] = True
                    log["generic_assumption"] += 1
                log["mapped"] += 1
        out.append(rec)
    args.out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n", encoding="utf-8", newline="\n")
    total = len(out)
    summary = {"records": total, "mapped": log["mapped"], "unmapped_no_canonical": log["unmapped"], "descriptor_only": log["descriptor_only"],
               "excluded_substance": log["excluded_substance"], "coverage_pct": round(100 * log["mapped"] / total, 2),
               "generic_assumption": log["generic_assumption"], "generic_assumption_pct_of_mapped": round(100 * log["generic_assumption"] / max(1, log["mapped"]), 2),
               "instructions_skipped": log["instructions_skipped"], "noise_skipped": log["noise_skipped"], "no_food_text_skipped": log["no_food_text_skipped"],
               "diets": len({x["diet_id"] for x in out}), "with_quantity": sum(1 for x in out if x["quantity"] is not None),
               "alternatives": sum(1 for x in out if x["alternative_group"]), "compound": sum(1 for x in out if x["compound_item"]),
               "groups": dict(Counter(x["group"] for x in out if x["group"]).most_common()),
               "families": dict(Counter(x["family"] for x in out if x["family"]).most_common()),
               "unmapped_top30": unmapped_keys.most_common(30)}
    (DATASET_DIR / "normalize_diets_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("unmapped_top30", "families")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
