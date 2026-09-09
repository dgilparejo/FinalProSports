# -*- coding: utf-8 -*-
"""External discriminator: can a classifier tell a generated diet from one the professional wrote?

The overlap metrics answer "how close is the proposal to the hidden diet". They cannot answer "does the proposal look like
something he would have written", because a diet can be close on average and still carry a signature no human output has
(always exactly three notes, always the same number of items per slot, never a repetition). This adapter asks the question
the overlap metrics cannot: an independent model is given ONLY structural, interpretable descriptors and has to guess the
origin. Reading of the result:

    AUC ~ 0.50   the generated diets are structurally indistinguishable from real ones on these descriptors.
    AUC >> 0.50  they are distinguishable, and the permutation importance names the descriptor that gives them away.
                 That is a defect list, not a verdict: each feature at the top is a concrete thing to fix.

The control comes FIRST and is not optional. Real diets are split into two arbitrary halves BY CLIENT and the identical
pipeline is run on them. That AUC must land at ~0.50: it is a null by construction, so anything else means the harness
itself (leakage through the grouping, an unbalanced split, a feature that encodes the fold) is broken and the principal
number would be an artefact. The principal AUC is only reported if the control passes.

Grouping: every fold splits by CLIENT, never by diet. A client contributes both a real and a generated diet, so a
diet-level split would let the model memorise a client's style in training and recognise it in test — it would measure
client identity, not realism.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.discriminability
Out:  la memoria (discriminabilidad), docs/evaluation/discriminability.json, docs/evaluation/figures/fig09_discriminability.png
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from finalprosports.infrastructure.config.paths import docs_dir
from finalprosports.domain.model.food import FoodGroup
from finalprosports.domain.model.meal_slot import MealSlot
from finalprosports.domain.model.quantity import Unit
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import (apply_plausibility, composer_like, retrieve_all, setup, to_diet)
from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.domain.model.restriction import RestrictionMode

SEED = 42
N_SPLITS = 5
N_BOOTSTRAP = 2000
DOCS = docs_dir() / "evaluation"

# Descriptors deliberately NOT given to the classifier, and why. A discriminator is only worth reading if losing means
# something: every one of these would let it win for a reason that has nothing to do with whether the diet is realistic.
DISCARDED = {
    "raw_text of each item": "the real diets keep the professional's original wording, the generated ones a rebuilt string. "
                             "The classifier would recognise the serialiser, not the diet.",
    "note text (only the count is kept)": "notes are emitted by copying a neighbour's literal wording, so exact strings match "
                                          "real diets. That measures the copying, not the realism, and it is being fixed separately.",
    "diet id, client code, diet_version": "identifiers. Generated diets have no version of their own; the label is in the field.",
    "template_group_id": "present only on corpus diets.",
    "retrieval score, rank, k_effective, degradation": "harness metadata. It exists only on the generated side.",
    "goal": "balanced by construction (each generated diet is built for the goal of the real diet it is paired with), so it "
            "carries no signal — listed to make the balance explicit rather than to imply it was tested.",
    "number of characters of the serialised diet": "a monotone function of the serialiser, dominated by the wording.",
    "food_id values as categories": "the catalogue id is an arbitrary integer; as a category it lets a tree memorise which "
                                    "specific foods the composer favours, which is a retrieval fingerprint rather than a structural trait.",
}

DROP_HELP = """descriptores a EXCLUIR del experimento, separados por comas (tambien del control).

Existe por una pregunta concreta: `share_unmapped` es el segundo delator, y lo que mide es que el sistema NO reproduce
los items que el extractor deja sin mapear en las dietas reales (el 2,5 % de los suyos, mediana 1,4 %; el sistema 0,0 %).
Eso no es una conducta del profesional que el motor deje de imitar: es basura del parser sobre el corpus, y un
discriminador que gana por ahi esta detectando el pipeline de extraccion, no el realismo de la dieta. La cifra honesta
para la memoria es la de las conductas, asi que hay que poder medir las dos y publicarlas juntas."""

GROUPS = [FoodGroup.PROTEIN, FoodGroup.CARB, FoodGroup.FAT, FoodGroup.VEGETABLE, FoodGroup.FRUIT,
          FoodGroup.DAIRY, FoodGroup.SUPPLEMENT, FoodGroup.BEVERAGE]
SLOTS = [MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.LUNCH, MealSlot.SNACK, MealSlot.DINNER,
         MealSlot.PRE_WORKOUT, MealSlot.INTRA_WORKOUT, MealSlot.POST_WORKOUT]
UNITS = [Unit.GRAM, Unit.MILLILITER, Unit.PIECE, Unit.TABLESPOON, Unit.SCOOP, Unit.NONE]


def entropy(counts) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    return -sum((c / total) * math.log(c / total) for c in counts if c > 0)


def features(diet, catalog) -> dict[str, float]:
    """Structural descriptors of ONE diet. Every one of them is a sentence a human could say about the diet
    ("how many items per slot", "what share of it is protein", "how often a food repeats")."""
    items = [i for m in diet.meals for i in m.items]
    n = len(items)
    per_slot = [len(m.items) for m in diet.meals]
    foods = [i.food_id for i in items if i.food_id is not None]
    fam = Counter(catalog[f].family for f in foods if f in catalog)
    grp = Counter(catalog[f].group for f in foods if f in catalog)
    rep = Counter(foods)
    alt = Counter(i.alternative_group for i in items if i.alternative_group)
    comp = Counter(i.compound_group for i in items if i.compound_group)
    quantities = [i.quantity.value for i in items if i.quantity.has_amount]
    grams = [i.quantity.value for i in items if i.quantity.has_amount and i.quantity.unit is Unit.GRAM]
    units = Counter(i.quantity.unit for i in items)
    slot_rep = []                                            # repetitions of a food WITHIN one slot
    for m in diet.meals:
        c = Counter(i.food_id for i in m.items if i.food_id is not None)
        slot_rep.append(sum(v - 1 for v in c.values() if v > 1))

    f = {
        "n_items": n,
        "n_slots": len(diet.meals),
        "items_per_slot_mean": statistics.fmean(per_slot) if per_slot else 0.0,
        "items_per_slot_max": max(per_slot) if per_slot else 0,
        "items_per_slot_sd": statistics.pstdev(per_slot) if len(per_slot) > 1 else 0.0,
        "n_distinct_foods": len(set(foods)),
        "n_distinct_families": len(fam),
        "n_distinct_groups": len(grp),
        "family_entropy": entropy(fam.values()),
        "repeat_total": sum(v - 1 for v in rep.values() if v > 1),
        "repeat_max": max(rep.values()) if rep else 0,
        "repeat_within_slot": sum(slot_rep),
        "n_alternative_groups": len(alt),
        "alternatives_per_group_mean": statistics.fmean(alt.values()) if alt else 0.0,
        "alternatives_per_group_max": max(alt.values()) if alt else 0,
        "share_items_in_alternatives": sum(alt.values()) / n if n else 0.0,
        "n_compound_groups": len(comp),
        "n_notes": len(diet.notes),
        "share_with_quantity": sum(1 for i in items if i.quantity.has_amount) / n if n else 0.0,
        "share_unmapped": sum(1 for i in items if i.food_id is None) / n if n else 0.0,
        "quantity_median": statistics.median(quantities) if quantities else 0.0,
        "quantity_iqr": (statistics.quantiles(quantities, n=4)[2] - statistics.quantiles(quantities, n=4)[0]) if len(quantities) >= 4 else 0.0,
        "grams_median": statistics.median(grams) if grams else 0.0,
        "grams_round_to_50": sum(1 for g in grams if g % 50 == 0) / len(grams) if grams else 0.0,
    }
    for g in GROUPS:
        f[f"share_{g.value}"] = grp.get(g, 0) / max(1, len(foods))
    for s in SLOTS:
        m = diet.meal(s)
        f[f"has_{s.name.lower()}"] = 1.0 if m else 0.0
        f[f"n_items_{s.name.lower()}"] = len(m.items) if m else 0
    for u in UNITS:
        f[f"unit_share_{u.name.lower()}"] = units.get(u, 0) / n if n else 0.0
    return f


def build_dataset(arm: str = "motor"):
    """The two populations: the professional's held-out diets and, for each of them, the diet the DELIVERED configuration
    proposes for that same client and goal. One pair per LOO query, so the classes are balanced by construction.

    `arm` selects the neighbourhood the proposals are composed from, and it matters here for a reason that is not
    fidelity: going from seven effective voters to twenty changes which items and which notes reach consensus, and the
    descriptors this classifier reads are precisely counts of items and notes. Measuring realism on one arm and
    shipping the other would publish a number about a system nobody serves.
    """
    root, pid, diets, profiles, queries, rules = setup()
    catalog = root.catalog
    k = root.composer.params.k
    retrieved, _ = retrieve_all(root, pid, queries, profiles, k)
    if arm == "D3":
        from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import as_of_profile
        from finalprosports.infrastructure.adapter.inbound.eval.scarce_goals import variants
        svc = root.retrieve_similar_cases_service
        for q in queries:
            perfil = as_of_profile(root, pid, profiles[q.client_code], q.goal, q.id)
            excl = frozenset(svc.mandatory_exclusions(pid, perfil) | {q.id})
            # crudo del repositorio: el servicio ya aplica D3 y pedirselo aqui seleccionaria dos veces
            cands = root.case_repository.find_similar(pid, svc.query_for(perfil), k * 8, excl)
            retrieved[q.id] = (retrieved[q.id][0], variants(cands, q.goal, k)["D3"])
    composer = composer_like(root)
    validator = DietValidator(catalog, RestrictionMode.STRICT, True)
    env = root.envelope.load(pid)
    assert env is not None, "plausibility_envelope.json missing (make envelope)"

    real, gen, groups_real = [], [], []
    for hidden in queries:
        profile, cases = retrieved[hidden.id]
        raw = composer.propose(profile, cases, rules)
        plaus, _ = apply_plausibility(raw, cases, env, catalog)
        delivered = to_diet(validator.validate(plaus, rules, profile, cases=cases))
        real.append(features(hidden, catalog))
        gen.append(features(delivered, catalog))
        groups_real.append(hidden.client_code)
    return real, gen, groups_real, len(queries)


def matrices(a: list[dict], b: list[dict], groups_a, groups_b):
    names = sorted(a[0])
    X = np.array([[r[n] for n in names] for r in a + b], dtype=float)
    y = np.array([0] * len(a) + [1] * len(b))
    g = np.array(list(groups_a) + list(groups_b))
    return X, y, g, names


def models():
    return {
        "logistic_regression": Pipeline([("scale", StandardScaler()),
                                         ("clf", LogisticRegression(max_iter=5000, random_state=SEED))]),
        "gradient_boosting": HistGradientBoostingClassifier(random_state=SEED, max_iter=300, early_stopping=True),
    }


def cluster_bootstrap_auc(y, p, groups, rng) -> tuple[float, float]:
    """Resample CLIENTS, not diets: two diets of the same client are not independent observations, and a naive bootstrap
    over rows would report a confidence interval narrower than the data supports."""
    by = {}
    for i, gid in enumerate(groups):
        by.setdefault(gid, []).append(i)
    keys = list(by)
    aucs = []
    for _ in range(N_BOOTSTRAP):
        idx = [i for kk in (keys[rng.randrange(len(keys))] for _ in keys) for i in by[kk]]
        yy = y[idx]
        if len(set(yy)) < 2:
            continue
        aucs.append(roc_auc_score(yy, p[idx]))
    aucs.sort()
    lo = aucs[int(0.025 * len(aucs))]
    hi = aucs[int(0.975 * len(aucs)) - 1]
    return lo, hi


def run_experiment(X, y, g, names, label: str, with_importance: bool = True) -> dict:
    cv = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    out = {"label": label, "n": int(len(y)), "n_positive": int(y.sum()), "n_groups": int(len(set(g))), "models": {}}
    rng = random.Random(SEED)
    for mname, proto in models().items():
        oof = np.zeros(len(y))
        imps = []
        for tr, te in cv.split(X, y, g):
            from sklearn.base import clone
            m = clone(proto)
            m.fit(X[tr], y[tr])
            oof[te] = m.predict_proba(X[te])[:, 1]
            if with_importance:
                r = permutation_importance(m, X[te], y[te], n_repeats=10, random_state=SEED, scoring="roc_auc")
                imps.append(r.importances_mean)
        auc = roc_auc_score(y, oof)
        lo, hi = cluster_bootstrap_auc(y, oof, g, rng)
        entry = {"auc": round(float(auc), 4), "ci95": [round(lo, 4), round(hi, 4)]}
        if with_importance:
            mean_imp = np.mean(imps, axis=0)
            order = np.argsort(-mean_imp)
            entry["permutation_importance"] = [{"feature": names[i], "auc_drop": round(float(mean_imp[i]), 5)} for i in order]
        out["models"][mname] = entry
    return out


def cascade(X, y, g, names, principal: dict, rounds: int = 6) -> list[dict]:
    """A single AUC is a verdict; a cascade is a work list.

    When one descriptor separates the two populations perfectly, it hides every other difference behind it: the model has no
    reason to learn a second tell once the first one is free. So the top descriptor is removed and the experiment is repeated,
    and again. Each row answers "if I fix this, what does the classifier fall back on, and how much does that buy me" — which
    is the order in which the defects are worth fixing."""
    dropped: list[str] = []
    keep = list(range(len(names)))
    order = [d["feature"] for d in principal["models"]["gradient_boosting"]["permutation_importance"]]
    rows = []
    rng = random.Random(SEED)
    cv = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    for _ in range(rounds):
        nxt = next((f for f in order if f not in dropped), None)
        if nxt is None:
            break
        dropped.append(nxt)
        keep = [i for i in range(len(names)) if names[i] not in dropped]
        if len(keep) < 2:
            break
        Xk = X[:, keep]
        from sklearn.base import clone
        proto = models()["gradient_boosting"]
        oof = np.zeros(len(y))
        for tr, te in cv.split(Xk, y, g):
            m = clone(proto)
            m.fit(Xk[tr], y[tr])
            oof[te] = m.predict_proba(Xk[te])[:, 1]
        auc = roc_auc_score(y, oof)
        lo, hi = cluster_bootstrap_auc(y, oof, g, rng)
        # the tell the model falls back on once `nxt` is gone
        m = clone(proto).fit(Xk, y)
        r = permutation_importance(m, Xk, y, n_repeats=5, random_state=SEED, scoring="roc_auc")
        nxt_tell = [names[keep[i]] for i in np.argsort(-r.importances_mean)][0]
        rows.append({"removed": list(dropped), "last_removed": nxt, "auc": round(float(auc), 4),
                     "ci95": [round(lo, 4), round(hi, 4)], "next_tell": nxt_tell})
        order = [names[keep[i]] for i in np.argsort(-r.importances_mean)]
    return rows


def sanity_control(real: list[dict], groups: list[str]) -> dict:
    """The null. Real diets only, split into two arbitrary halves BY CLIENT, then the identical pipeline. Because the
    pseudo-label carries no information and the folds are grouped by client, the honest answer is 0.50. A result above
    0.60 means the measurement apparatus leaks and the principal number cannot be read."""
    rng = random.Random(SEED)
    coin = {c: rng.random() < 0.5 for c in sorted(set(groups))}
    a = [r for r, c in zip(real, groups) if not coin[c]]
    b = [r for r, c in zip(real, groups) if coin[c]]
    ga = [c for c in groups if not coin[c]]
    gb = [c for c in groups if coin[c]]
    n = min(len(a), len(b))                          # balanced, like the principal experiment
    a, b, ga, gb = a[:n], b[:n], ga[:n], gb[:n]
    X, y, g, names = matrices(a, b, ga, gb)
    res = run_experiment(X, y, g, names, "control: real vs real (arbitrary halves by client)", with_importance=False)
    res["verdict"] = "PASS" if max(m["auc"] for m in res["models"].values()) <= 0.60 else "FAIL"
    return res


def figure(principal: dict, names: list[str], path: Path, top: int = 18) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    imp = principal["models"]["gradient_boosting"]["permutation_importance"][:top][::-1]
    fig, ax = plt.subplots(figsize=(9, 0.34 * len(imp) + 1.6))
    ax.barh([d["feature"] for d in imp], [d["auc_drop"] for d in imp], color="#3b6ea5")
    ax.set_xlabel("drop in AUC when the descriptor is permuted (gradient boosting, mean over the 5 folds)")
    ax.set_title(f"What gives a generated diet away  ·  AUC {principal['models']['gradient_boosting']['auc']:.3f}")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def report(res: dict) -> str:
    p, c = res["principal"], res["control"]
    gb, lr = p["models"]["gradient_boosting"], p["models"]["logistic_regression"]
    auc = max(gb["auc"], lr["auc"])
    reading = ("indistinguishable on these descriptors" if auc < 0.60 else
               "distinguishable, but only weakly" if auc < 0.70 else
               "clearly distinguishable" if auc < 0.85 else "trivially distinguishable")
    L = [
        "# Discriminability: can a classifier tell a generated diet from a real one?",
        "",
        f"_Measured {res['measured_at']} · {p['n'] // 2} pairs (one real diet and one generated diet per leave-one-out query),"
        f" {p['n_groups']} clients, {N_SPLITS}-fold cross-validation grouped by client, 95 % CI from a bootstrap over clients._",
        "",
        *(["> **Descriptores excluidos en esta ejecución (`--drop`): "
           + ", ".join(f"`{f}`" for f in res["dropped_features"]) + "**. Ni el control ni el principal los ven.", ""]
          if res.get("dropped_features") else []),
        "## 0. What this measures, and what it does not",
        "",
        "The overlap metrics say how close a proposal is to the diet the professional actually wrote. They cannot say whether it",
        "*looks like* something he would write: a proposal can be close on average and still carry a signature no human output has.",
        "This experiment hands an independent classifier nothing but structural descriptors of a diet and asks it to name the origin.",
        "",
        "| Reading | Meaning |",
        "|---|---|",
        "| AUC ≈ 0.50 | the two populations are not separable on these descriptors |",
        "| AUC > 0.50 | they are separable, and the ranking below names the descriptor that separates them |",
        "",
        "An AUC above 0.50 is **a list of defects, not a verdict**: each descriptor at the top of the ranking is a concrete,",
        "nameable difference between what the system produces and what the professional produces.",
        "",
        "## 1. The control comes first",
        "",
        "The null: the same real diets, split into two arbitrary halves **by client**, run through the identical pipeline. The",
        "pseudo-label carries no information, so the honest answer is 0.50. This is not a formality — if the apparatus leaked",
        "(a feature encoding the fold, an unbalanced split, grouping that lets a client appear on both sides), the control would",
        "reveal it and the principal number would be an artefact.",
        "",
        "| model | AUC | 95 % CI |",
        "|---|---|---|",
    ]
    for m, v in c["models"].items():
        L.append(f"| {m} | {v['auc']:.3f} | [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}] |")
    L += ["", f"**Control: {c['verdict']}** (criterion: AUC ≤ 0.60). "
              + ("The apparatus does not separate what is not separable, so the principal result below can be read."
                 if c["verdict"] == "PASS" else
                 "The apparatus separates diets that carry no label. The principal result is NOT reported: it would be an artefact."),
          ""]
    if c["verdict"] != "PASS":
        return "\n".join(L)
    L += [
        "## 2. Principal result — real diet vs generated diet",
        "",
        "| model | AUC | 95 % CI |",
        "|---|---|---|",
        f"| logistic regression (linear, scaled) | {lr['auc']:.3f} | [{lr['ci95'][0]:.3f}, {lr['ci95'][1]:.3f}] |",
        f"| gradient boosting (non-linear) | {gb['auc']:.3f} | [{gb['ci95'][0]:.3f}, {gb['ci95'][1]:.3f}] |",
        "",
        f"Reading: **{reading}** (AUC {auc:.3f}).",
        "",
        "The gap between the linear and the non-linear model is itself informative: when boosting wins by a wide margin the",
        "signature is an interaction (a combination of descriptors), not a single descriptor out of range.",
        "",
        "## 3. What gives a generated diet away",
        "",
        "Permutation importance: how much AUC the model loses when one descriptor is shuffled, averaged over the folds.",
        "",
        "| # | descriptor | AUC lost when permuted | real (mean) | generated (mean) |",
        "|---:|---|---:|---:|---:|",
    ]
    for i, d in enumerate(gb["permutation_importance"][:18], 1):
        st = res["descriptor_means"][d["feature"]]
        L.append(f"| {i} | `{d['feature']}` | {d['auc_drop']:.4f} | {st['real']:.3f} | {st['generated']:.3f} |")
    L += [
        "",
        "![What gives a generated diet away](figures/fig09_discriminability.png)",
        "",
        "## 3bis. The cascade — what remains once the top tell is fixed",
        "",
        "One descriptor separating the populations perfectly hides every other difference behind it: the model has no reason to",
        "learn a second tell while the first one is free. Each row removes the current top descriptor and repeats the experiment,",
        "so the table reads as a work list — *fix this, and the classifier falls back on that*.",
        "",
        "| removed so far | AUC | 95 % CI | what it falls back on |",
        "|---|---:|---|---|",
        f"| — (nothing removed) | {gb['auc']:.3f} | [{gb['ci95'][0]:.3f}, {gb['ci95'][1]:.3f}] | `{gb['permutation_importance'][0]['feature']}` |",
    ]
    for row in res.get("cascade", []):
        L.append(f"| `{'`, `'.join(row['removed'])}` | {row['auc']:.3f} | [{row['ci95'][0]:.3f}, {row['ci95'][1]:.3f}] | `{row['next_tell']}` |")
    L += [
        "",
        "## 4. Descriptors deliberately withheld",
        "",
        "A discriminator is only worth reading if losing means something. Each of these would let the classifier win for a reason",
        "unrelated to whether the diet is realistic, so none of them was given to it.",
        "",
        "| withheld | why |",
        "|---|---|",
    ]
    for kk, v in DISCARDED.items():
        L.append(f"| {kk} | {v} |")
    L += ["", "## 5. Method", "",
          f"- **Populations.** One pair per leave-one-out query: the held-out real diet, and the diet the delivered configuration",
          f"  (strategy → plausibility layer → validator) proposes for that same client and goal. Classes balanced by construction",
          f"  ({p['n'] // 2} and {p['n'] // 2}); the goal distribution is identical on both sides for the same reason.",
          "- **Grouping.** Every fold splits by client, never by diet. A client contributes to both classes, so a diet-level split",
          "  would let the model memorise a client's style in training and recognise it in test — measuring identity, not realism.",
          "- **Confidence interval.** Bootstrap over *clients*, not rows: two diets of the same client are not independent",
          f"  observations, and a row-level resample would report an interval narrower than the data supports ({N_BOOTSTRAP} resamples).",
          f"- **Seed** {SEED} throughout; the run is reproducible from a clean clone.",
          ""]
    return "\n".join(L)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="external discriminator")
    ap.add_argument("--arm", choices=("motor", "D3"), default="motor")
    ap.add_argument("--suffix", default="", help="output suffix, so a second arm does not overwrite the first")
    ap.add_argument("--drop", default="", help=DROP_HELP)
    args = ap.parse_args()
    real, gen, groups, n_queries = build_dataset(args.arm)
    dropped_features = [f.strip() for f in args.drop.split(",") if f.strip()]
    unknown = [f for f in dropped_features if f not in real[0]]
    if unknown:
        raise SystemExit(f"--drop: descriptor(es) inexistente(s): {unknown}")
    if dropped_features:
        real = [{k: v for k, v in r.items() if k not in dropped_features} for r in real]
        gen = [{k: v for k, v in r.items() if k not in dropped_features} for r in gen]
    print(f"dataset: {n_queries} pairs, {len(set(groups))} clients, {len(real[0])} descriptors, arm={args.arm}"
          + (f", dropped={dropped_features}" if dropped_features else ""), file=sys.stderr)

    control = sanity_control(real, groups)
    print(f"control (real vs real): {[ (m, v['auc']) for m, v in control['models'].items() ]} -> {control['verdict']}", file=sys.stderr)

    res = {"measured_at": datetime.now().isoformat(timespec="seconds"), "seed": SEED, "n_splits": N_SPLITS,
           "n_bootstrap": N_BOOTSTRAP, "control": control, "discarded_features": DISCARDED, "arm": args.arm,
           "dropped_features": dropped_features}
    if control["verdict"] != "PASS":
        res["principal"] = None
        res["note"] = "principal experiment NOT run: the sanity control failed, so any AUC it produced would be an artefact"
    else:
        X, y, g, names = matrices(real, gen, groups, groups)
        principal = run_experiment(X, y, g, names, "principal: real vs generated")
        res["principal"] = principal
        res["cascade"] = cascade(X, y, g, names, principal)
        res["descriptor_means"] = {n: {"real": round(float(np.mean([r[n] for r in real])), 4),
                                       "generated": round(float(np.mean([r[n] for r in gen])), 4)} for n in names}
        DOCS.joinpath("figures").mkdir(parents=True, exist_ok=True)
        figure(principal, names, DOCS / "figures" / f"fig09_discriminability{args.suffix}.png")
        print(f"principal: {[ (m, v['auc']) for m, v in principal['models'].items() ]}", file=sys.stderr)

    DOCS.mkdir(parents=True, exist_ok=True)
    DOCS.joinpath(f"discriminability{args.suffix}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    DOCS.joinpath(f"DISCRIMINABILITY{args.suffix.upper()}.md").write_text(report(res), encoding="utf-8", newline="\n")
    print(json.dumps({"control_auc": {m: v["auc"] for m, v in control["models"].items()}, "control": control["verdict"],
                      "principal_auc": ({m: v["auc"] for m, v in res["principal"]["models"].items()} if res.get("principal") else None)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
