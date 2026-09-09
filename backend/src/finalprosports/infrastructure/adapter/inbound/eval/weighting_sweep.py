# -*- coding: utf-8 -*-
"""Does weighting the consensus by neighbour similarity buy per-case agreement, and at what cost in overlap?

The flat consensus reproduces his AVERAGE behaviour: measured, its per-case agreement with him on the 15 measurable rules
(0,806) is below the trivial baseline of always predicting his majority (0,831). A similarity-weighted vote lets the nearest
cases decide, which should recover some of the discrimination the retrieval already found. Both things are reported together
because they trade off: enough weighting turns the composer into copy-top-1, whose overlap is 0,255.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.weighting_sweep
"""
from __future__ import annotations

import dataclasses
import json
import statistics
import sys
from collections import defaultdict

from finalprosports.application.strategy.case_based_composer import CaseBasedComposer
from finalprosports.domain.composition.policy.rule_engine import RuleEngine
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import key_set, setup, retrieve_all, to_diet
from finalprosports.infrastructure.config.paths import dataset_dir

POWERS = (0.0, 1.0, 2.0, 4.0, 8.0)


def jaccard(a, b) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def main() -> int:
    root, pid, diets, profiles, queries, rules = setup()
    catalog, engine = root.catalog, RuleEngine(catalog := root.catalog)
    retrieved, _ = retrieve_all(root, pid, queries, profiles, root.composer.params.k)
    hidden_by_rule = {}
    for h in queries:
        profile, _ = retrieved[h.id]
        hidden_by_rule[h.id] = {c.rule_id: c.satisfied for c in engine.check(rules, h, profile) if c.applicable}

    out = []
    for power in POWERS:
        params = dataclasses.replace(root.composer.params, similarity_weighting=power)
        composer = CaseBasedComposer(catalog, params, notes=root.composer._notes)   # noqa: SLF001
        js, agree, tot = [], defaultdict(lambda: [0, 0]), 0
        prof_hits = defaultdict(lambda: [0, 0])
        for h in queries:
            profile, cases = retrieved[h.id]
            d = to_diet(composer.propose(profile, cases, rules))
            js.append(jaccard(key_set(h), key_set(d)))
            sys_by_rule = {c.rule_id: c.satisfied for c in engine.check(rules, d, profile) if c.applicable}
            for rid in hidden_by_rule[h.id].keys() & sys_by_rule.keys():
                agree[rid][0] += 1
                agree[rid][1] += bool(sys_by_rule[rid]) == bool(hidden_by_rule[h.id][rid])
                prof_hits[rid][0] += 1
                prof_hits[rid][1] += bool(hidden_by_rule[h.id][rid])
        w = sum(v[0] for v in agree.values()) or 1
        acc = sum(v[1] for v in agree.values()) / w
        base = sum(max(p[1], p[0] - p[1]) for p in prof_hits.values()) / w
        beat = sum(1 for rid in agree if agree[rid][1] / agree[rid][0] > max(prof_hits[rid][1], prof_hits[rid][0] - prof_hits[rid][1]) / prof_hits[rid][0])
        out.append({"power": power, "j_key": round(statistics.fmean(js), 4), "conditional_accuracy": round(acc, 4),
                    "base_rate_accuracy": round(base, 4), "gain": round(acc - base, 4), "rules_beating_base": beat,
                    "rules": len(agree)})
        print(f"power {power:4.1f}  J key {out[-1]['j_key']:.4f}  conditional accuracy {acc:.4f}  base {base:.4f}  "
              f"gain {acc - base:+.4f}  beats base in {beat}/{len(agree)} rules")
    (dataset_dir() / "weighting_sweep.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
