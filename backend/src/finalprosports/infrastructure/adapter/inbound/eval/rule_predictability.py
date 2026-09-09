# -*- coding: utf-8 -*-
"""The ceiling of conditional accuracy: is his per-case rule decision predictable AT ALL from what the system knows?

The composer's per-case agreement with him (0,806) sits below the trivial baseline of always predicting his majority (0,831),
which reads as a failure — but only if the decision was learnable in the first place. This experiment asks the question the
right way round: give a classifier everything the system has about the client (goal, sex, age, height, activity, declared
restrictions, the diet's phase) and let it predict, for each rule, whether HE satisfied it on that diet. Grouped by client,
so a fold never tests on a client it trained on.

  * If the classifier beats the base rate, the decision is predictable and the composer is leaving signal on the table.
  * If it does not, the variance is his own — the same client profile gets the rule some days and not others — and the base
    rate IS the ceiling. Then "conditional accuracy below the base rate" is a statement about the composer's flattening, and
    matching the base rate is the honest target, not beating it.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.rule_predictability
Out:  FPS_DATASET_DIR/rule_predictability.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

from finalprosports.domain.composition.policy.rule_engine import RuleEngine
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import setup, retrieve_all
from finalprosports.infrastructure.config.paths import dataset_dir

SEED = 42
N_SPLITS = 5
MIN_MINORITY = 25          # below this many cases of the minority class a per-rule model cannot be evaluated honestly


def features(profile, diet) -> list[float]:
    """Everything the system knows about the client when it composes. No leakage from the diet's content: only its phase,
    which the system also knows (it is composing version N)."""
    return [
        float(hash(profile.goal.value) % 1000),           # goal as a stable categorical code
        1.0 if profile.sex == "M" else 0.0,
        float(profile.age or 0), float(profile.height_cm or 0), float(profile.activity_level or 0),
        1.0 if getattr(profile, "has_allergies", False) else 0.0,
        1.0 if getattr(profile, "has_intolerances", False) else 0.0,
        1.0 if getattr(profile, "has_medical_restrictions", False) else 0.0,
        float(diet.diet_version or 0),
        float(len(diet.meals)),
    ]


def main() -> int:
    root, pid, diets, profiles, queries, rules = setup()
    engine = RuleEngine(root.catalog)
    retrieved, _ = retrieve_all(root, pid, queries, profiles, root.composer.params.k)

    X_all, groups, labels = [], [], defaultdict(dict)
    for i, h in enumerate(queries):
        profile, _ = retrieved[h.id]
        X_all.append(features(profile, h))
        groups.append(h.client_code)
        for c in engine.check(rules, h, profile):
            if c.applicable:
                labels[c.rule_id][i] = bool(c.satisfied)
    X_all = np.array(X_all, dtype=float)
    groups = np.array(groups)

    out = []
    for rid, lab in sorted(labels.items()):
        idx = np.array(sorted(lab))
        y = np.array([lab[i] for i in idx], dtype=int)
        minority = min(int(y.sum()), int((1 - y).sum()))
        base = max(y.mean(), 1 - y.mean())
        row = {"rule": rid, "n": int(len(y)), "base_rate_accuracy": round(float(base), 4), "minority": minority}
        if minority < MIN_MINORITY or len(set(groups[idx])) < N_SPLITS:
            row.update({"verdict": "not evaluable", "reason": f"minority class {minority} < {MIN_MINORITY}"})
            out.append(row); continue
        X, g = X_all[idx], groups[idx]
        cv = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
        oof = np.zeros(len(y))
        proto = HistGradientBoostingClassifier(random_state=SEED, max_iter=200, early_stopping=True)
        for tr, te in cv.split(X, y, g):
            m = clone(proto).fit(X[tr], y[tr])
            oof[te] = m.predict_proba(X[te])[:, 1]
        acc = float(((oof >= 0.5).astype(int) == y).mean())
        auc = float(roc_auc_score(y, oof))
        row.update({"auc": round(auc, 4), "accuracy": round(acc, 4), "gain_over_base": round(acc - base, 4),
                    "verdict": "predictable" if auc >= 0.60 and acc > base else "not predictable from the profile"})
        out.append(row)

    ev = [r for r in out if "auc" in r]
    print(f"{'rule':34s} {'n':>5s} {'minority':>8s} {'AUC':>7s} {'acc':>7s} {'base':>7s} {'gain':>7s}  verdict")
    for r in out:
        if "auc" in r:
            print(f"{r['rule']:34s} {r['n']:5d} {r['minority']:8d} {r['auc']:7.3f} {r['accuracy']:7.3f} "
                  f"{r['base_rate_accuracy']:7.3f} {r['gain_over_base']:+7.3f}  {r['verdict']}")
        else:
            print(f"{r['rule']:34s} {r['n']:5d} {r['minority']:8d} {'-':>7s} {'-':>7s} {r['base_rate_accuracy']:7.3f} {'-':>7s}  {r['verdict']}")
    if ev:
        print(f"\nevaluable rules: {len(ev)} of {len(out)}")
        print(f"  predictable from the client's profile: {sum(1 for r in ev if r['verdict'] == 'predictable')}")
        print(f"  mean AUC {sum(r['auc'] for r in ev) / len(ev):.3f}   mean gain over base {sum(r['gain_over_base'] for r in ev) / len(ev):+.4f}")
    (dataset_dir() / "rule_predictability.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
