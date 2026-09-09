# -*- coding: utf-8 -*-
"""Per-rule agreement between the system and the professional, on the antecedent subset (E9 · realism batch, 2.A).

Two questions, and only the second one is the objective:

  * **rate** — how often each of them satisfies a rule. Useful to spot a broken pipeline (a rule at 0,019 against his 0,787
    is not a matter of taste, it is a defect), useless as a target: matching his aggregate rate would mean reproducing his
    inconsistency for its own sake.
  * **conditional accuracy** — whether the system decides as he decided ON THE SAME CASE. This is the objective. It is
    reported against the only honest baseline, always predicting his majority behaviour for that rule: a rule he satisfies
    93 % of the time is 93 % "accurate" for free, and a system that does not beat that has learned nothing about the case.

Everything is measured on the ANTECEDENT subset, which the engine already isolates (`RuleEngine.evaluate` returns None when
the antecedent does not hold, `applicable` filters by profile scope), and PAIRED: only the queries where the antecedent holds
on both sides, so the two rates speak about the same diets.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.rule_rates [--variant composer_raw]
In:   FPS_DATASET_DIR/composer_per_query.jsonl (loo_harness --final)
Out:  FPS_DATASET_DIR/rule_rate_diagnosis.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict

from finalprosports.infrastructure.composition_root import CompositionRoot
from finalprosports.infrastructure.config.paths import dataset_dir


def binom_two_sided(k: int, n: int, p: float = 0.5) -> float:
    if n == 0:
        return 1.0
    pmf = [math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    return min(1.0, sum(x for x in pmf if x <= pmf[k] * (1 + 1e-9)))


def measure(records: list[dict], variant: str, rules: dict) -> dict:
    paired = defaultdict(lambda: [0, 0, 0])
    marg_p = defaultdict(lambda: [0, 0])
    marg_s = defaultdict(lambda: [0, 0])
    disagree = defaultdict(lambda: [0, 0])
    for r in records:
        h = r.get("hidden_by_rule") or {}
        s = (r["variants"].get(variant) or {}).get("by_rule") or {}
        for rid, ok in h.items():
            marg_p[rid][0] += 1; marg_p[rid][1] += bool(ok)
        for rid, ok in s.items():
            marg_s[rid][0] += 1; marg_s[rid][1] += bool(ok)
        for rid in h.keys() & s.keys():
            paired[rid][0] += 1; paired[rid][1] += bool(h[rid]); paired[rid][2] += bool(s[rid])
            if bool(s[rid]) != bool(h[rid]):
                disagree[rid][0 if s[rid] else 1] += 1

    rows = []
    for rid, (n, hp, hs) in paired.items():
        if not n:
            continue
        p_r, s_r = hp / n, hs / n
        b, c = disagree[rid]
        m = rules.get(rid)
        rows.append({"rule": rid, "n_paired": n, "p_r": round(p_r, 4), "s_r": round(s_r, 4), "d": round(s_r - p_r, 4),
                     "accuracy": round(1 - (b + c) / n, 4), "base_rate_accuracy": round(max(p_r, 1 - p_r), 4),
                     "gain_over_base": round((1 - (b + c) / n) - max(p_r, 1 - p_r), 4),
                     "mcnemar_p": binom_two_sided(min(b, c), b + c) if (b + c) else 1.0, "b": b, "c": c,
                     "level": (m.evaluation_level if m else None), "nature": (m.nature.value if m and m.nature else None),
                     "prevalence": (m.prevalence if m else None),
                     "n_prof_only": marg_p[rid][0], "n_sys_only": marg_s[rid][0]})
    rows.sort(key=lambda x: x["d"])
    pos = sum(1 for r in rows if r["d"] > 1e-9)
    neg = sum(1 for r in rows if r["d"] < -1e-9)
    w = sum(r["n_paired"] for r in rows) or 1
    return {"variant": variant, "queries": len(records), "rules_measurable": len(rows), "rules_total": len(rules),
            "rules": rows,
            "sign_test": {"positive": pos, "negative": neg, "ties": len(rows) - pos - neg,
                          "p_two_sided": round(binom_two_sided(min(pos, neg), pos + neg), 4)},
            "mean_signed_difference": round(sum(r["d"] for r in rows) / len(rows), 4),
            "conditional_accuracy": round(sum(r["accuracy"] * r["n_paired"] for r in rows) / w, 4),
            "base_rate_accuracy": round(sum(r["base_rate_accuracy"] * r["n_paired"] for r in rows) / w, 4),
            "rules_beating_base": sum(1 for r in rows if r["gain_over_base"] > 1e-9)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="composer_raw", help="composer_raw (the strategy alone) | validated_plausible (delivered)")
    args = ap.parse_args()
    D = dataset_dir()
    records = [json.loads(l) for l in (D / "composer_per_query.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    root = CompositionRoot.from_env()
    rules = {r.id: r for r in root.rules.all(root.configured_professional_id)}
    res = measure(records, args.variant, rules)

    print(f"# per-rule agreement · {res['queries']} LOO queries · variant = {args.variant}\n")
    print(f"{'rule':34s} {'n':>5s} {'p_r':>7s} {'s_r':>7s} {'s-p':>7s} {'acc':>7s} {'base':>7s} {'gain':>7s} {'McNemar':>9s}")
    for r in res["rules"]:
        print(f"{r['rule']:34s} {r['n_paired']:5d} {r['p_r']:7.3f} {r['s_r']:7.3f} {r['d']:+7.3f} "
              f"{r['accuracy']:7.3f} {r['base_rate_accuracy']:7.3f} {r['gain_over_base']:+7.3f} {r['mcnemar_p']:9.2e}")
    st = res["sign_test"]
    print(f"\nmeasurable antecedent: {res['rules_measurable']} of {res['rules_total']} rules")
    print(f"sign test on s_r - p_r: +{st['positive']} / -{st['negative']} -> p = {st['p_two_sided']:.4g}   "
          f"mean signed difference {res['mean_signed_difference']:+.4f}")
    print(f"\nCONDITIONAL ACCURACY (the objective): {res['conditional_accuracy']:.4f}   "
          f"majority baseline: {res['base_rate_accuracy']:.4f}   gain {res['conditional_accuracy'] - res['base_rate_accuracy']:+.4f}")
    print(f"rules beating their own majority baseline: {res['rules_beating_base']}/{res['rules_measurable']}")
    worst = sorted(res["rules"], key=lambda r: r["gain_over_base"])[:4]
    for r in worst:
        print(f"   {r['rule']:32s} acc {r['accuracy']:.3f} vs base {r['base_rate_accuracy']:.3f} ({r['gain_over_base']:+.3f})")
    (D / "rule_rate_diagnosis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
