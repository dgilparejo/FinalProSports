# -*- coding: utf-8 -*-
"""
Leave-one-out eligibility of the clean corpus.

A client is eligible when it has >= 2 clean diets (one can be held out and the others
remain as the client's own history). Reported with and without the template-diet
groups (diets whose `meta.template_group_id` is set: the same document was delivered
to several clients, so retrieving it for another client would be a leak, not a prediction).

Inputs:  --diets _dataset/diets.jsonl   --profiles _dataset/profiles.jsonl
Output:  --out _dataset/loo_eligibility.json  (+ summary on stdout)

Definitions:
  queries  = number of hold-out folds = number of diets of eligible clients (each diet is held out once)
  pairs    = unordered pairs of diets of the same client = sum C(k, 2)
  complete = client has sex, age and height_cm (not null)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pii_common import load_records, require_file, write_json  # noqa: E402


def summarize(diets_by_client: dict, profiles: dict) -> dict:
    eligible = {c: ids for c, ids in diets_by_client.items() if len(ids) >= 2}
    complete = {c: ids for c, ids in eligible.items()
                if profiles.get(c) and all(profiles[c].get(k) is not None for k in ("sex", "age", "height_cm"))}
    def block(d):
        ks = [len(v) for v in d.values()]
        return {"clients": len(d), "queries": sum(ks), "pairs": sum(comb(k, 2) for k in ks),
                "diets_per_client": {"min": min(ks) if ks else 0, "max": max(ks) if ks else 0,
                                     "mean": round(sum(ks) / len(ks), 2) if ks else 0}}
    return {"clients_with_diets": len(diets_by_client), "diets": sum(len(v) for v in diets_by_client.values()),
            "eligible_ge2": block(eligible), "eligible_ge2_complete_demographics": block(complete),
            "eligible_ge2_distribution": dict(sorted(Counter(min(len(v), 10) for v in eligible.values()).items()))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diets", required=True, type=Path)
    ap.add_argument("--profiles", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    diets = load_records(require_file(args.diets))
    profiles = {p["client_code"]: p for p in load_records(require_file(args.profiles))}

    all_by_client, no_tpl_by_client = defaultdict(list), defaultdict(list)
    tpl_diets = 0
    for r in diets:
        c = r["meta"]["client_code"]
        all_by_client[c].append(r["id"])
        if r["meta"].get("template_group_id"):
            tpl_diets += 1
        else:
            no_tpl_by_client[c].append(r["id"])
    out = {"all_diets": summarize(all_by_client, profiles),
           "excluding_template_groups": summarize(no_tpl_by_client, profiles),
           "template_diets_excluded": tpl_diets}
    write_json(args.out, out)
    for k in ("all_diets", "excluding_template_groups"):
        b = out[k]
        print(f"[{k}] clients_with_diets={b['clients_with_diets']} diets={b['diets']}")
        for kk in ("eligible_ge2", "eligible_ge2_complete_demographics"):
            v = b[kk]
            print(f"    {kk:36s} clients={v['clients']:4d} queries={v['queries']:5d} pairs={v['pairs']:6d} diets/client={v['diets_per_client']}")
    print(f"template diets excluded: {tpl_diets}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
