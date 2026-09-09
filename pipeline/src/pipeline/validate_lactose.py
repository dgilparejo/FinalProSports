# -*- coding: utf-8 -*-
"""
E1.3 — Empirical validation of the lactose (and honey) flags against the corpus.

Question: do clients with a DECLARED lactose intolerance receive whey isolate, cured cheese, kefir, casein...
in their real diets? If the trainer gives them a food, he treats it as safe and the catalogue must do the same;
vetoing it would penalise the system against the very reference it is measured on.

Inputs:  _dataset/_private/health_profiles.jsonl (read in-process only; no text is printed),
         _dataset/diets.jsonl, _dataset/parsed_items.jsonl, _dataset/foods.json
Output:  _dataset/lactose_validation.json + aggregates on stdout (client codes, counts and shares only).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR, PRIVATE_DIR  # noqa: E402
from pipeline.build_food_catalog import normalize_key, load_json  # noqa: E402

LACTOSE_RE = re.compile(r"lactosa|l[aá]cteo|leche", re.I)
CANDIDATES = ["leche", "yogur", "queso fresco", "requesón", "queso", "kéfir", "mantequilla", "batido de proteínas", "proteína aislada",
              "caseína", "bebida de proteínas", "barrita proteica", "café con leche", "postre o dulce", "leche sin lactosa", "yogur sin lactosa"]
HONEY = ["miel"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--health", type=Path, default=PRIVATE_DIR / "health_profiles.jsonl")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "lactose_validation.json")
    args = ap.parse_args()
    if not args.health.exists():
        raise FileNotFoundError(f"Required input file not found: {args.health}")
    health = [json.loads(l) for l in args.health.read_text(encoding="utf-8").splitlines() if l.strip()]
    lactose_clients = {h["client_code"] for h in health
                       if (h.get("intolerances") and LACTOSE_RE.search(h["intolerances"])) or (h.get("allergies") and LACTOSE_RE.search(h["allergies"]))}
    foods = load_json(DATASET_DIR / "foods.json")["foods"]
    key_to_canon = {k: f["canonical_name"] for f in foods for k in f["keys"]}
    parsed = [json.loads(l) for l in (DATASET_DIR / "parsed_items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    diets = {json.loads(l)["id"]: json.loads(l) for l in (DATASET_DIR / "diets.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    diet_client = {d: r["meta"]["client_code"] for d, r in diets.items()}
    all_clients = set(diet_client.values())
    lactose_with_diets = lactose_clients & all_clients

    def resolve(key):
        if key in key_to_canon:
            return key_to_canon[key]
        toks = key.split()
        for n in range(len(toks) - 1, 0, -1):
            c = " ".join(toks[:n])
            if c in key_to_canon:
                return key_to_canon[c]
        return None

    per_canon_lact: dict[str, set] = defaultdict(set)
    per_canon_all: dict[str, set] = defaultdict(set)
    comp_lact = Counter()
    for r in parsed:
        if r["is_instruction"] or r.get("is_noise") or not r["food_text"]:
            continue
        canon = resolve(normalize_key(r["food_text"]))
        if canon is None:
            continue
        client = diet_client.get(r["diet_id"])
        if client is None:
            continue
        per_canon_all[canon].add(client)
        if client in lactose_with_diets:
            per_canon_lact[canon].add(client)
            comp_lact[canon] += 1
    # honey: prohibition check in notes
    honey_notes = sum(1 for d in diets.values() for n in d["notes"] if re.search(r"\bmiel\b", n, re.I))
    honey_forbid = sum(1 for d in diets.values() for n in d["notes"] if re.search(r"\bmiel\b", n, re.I) and re.search(r"\bno\b|nada|evitar|prohib|sin", n, re.I))
    result = {
        "lactose_intolerant_clients_declared": len(lactose_clients),
        "of_which_with_clean_diets": len(lactose_with_diets),
        "diets_of_those_clients": sum(1 for c in diet_client.values() if c in lactose_with_diets),
        "foods": {},
        "honey": {"components_total": sum(1 for r in parsed if r["food_text"] and resolve(normalize_key(r["food_text"])) == "miel"),
                  "clients": len(per_canon_all.get("miel", set())), "notes_mentioning_miel": honey_notes,
                  "notes_forbidding_miel": honey_forbid},
    }
    for c in CANDIDATES + HONEY:
        n_l = len(per_canon_lact.get(c, set()))
        result["foods"][c] = {
            "lactose_clients_receiving_it": n_l,
            "share_of_lactose_clients": round(n_l / len(lactose_with_diets), 3) if lactose_with_diets else None,
            "components_in_their_diets": comp_lact.get(c, 0),
            "all_clients_receiving_it": len(per_canon_all.get(c, set())),
            "share_of_all_clients": round(len(per_canon_all.get(c, set())) / len(all_clients), 3),
        }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "foods"}, ensure_ascii=False))
    for c, v in result["foods"].items():
        print(f"  {c:22s} lactose-clients {v['lactose_clients_receiving_it']:2d}/{len(lactose_with_diets)} ({v['share_of_lactose_clients']})  "
              f"vs all {v['all_clients_receiving_it']:3d}/{len(all_clients)} ({v['share_of_all_clients']})  components={v['components_in_their_diets']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
