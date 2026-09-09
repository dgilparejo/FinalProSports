# -*- coding: utf-8 -*-
"""
E3.2 — Leave-one-out benchmark of the four retrieval strategies on the 746 hold-out queries.

Protocol (loo_eligibility.json, `excluding_template_groups.eligible_ge2_complete_demographics`): every non-template diet of a
client with >= 2 non-template diets and complete demographics (sex, age, height) is hidden once; the query is the client's
profile with the HIDDEN diet's goal (the goal is the professional's structured input). Mandatory exclusions are applied by
the retrieval service itself: all diets of the client and every diet of the template groups the client belongs to.

Per strategy: top1_same_goal_rate, topk_same_goal_rate, archetype (sex, age bucket, goal) present in the top-k, mean Jaccard
of the top-1 against the hidden diet at normalized_key and food_id granularity (also best-of-top-k and mean-of-top-k), and
latency p50/p95 (query embedding counted only for the strategies that need it). Jaccard is placed between the floor and the
ceiling measured in Part A (normalized_key 0,191 / 0,275; food_id 0,285 / 0,366): normalised = (system - floor) / (ceiling - floor).

Writes _dataset/retrieval_strategies.json and prints the comparison table. Nothing else is printed (pseudonymous ids only).
Run (venv, corpus loaded and vectorised): python -m finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from finalprosports.application.service.retrieval.retrieve_similar_cases_service import RetrieveSimilarCasesService
from finalprosports.application.strategy.retrieval_strategy import RetrievalStrategy
from finalprosports.domain.composition.policy.gap_policy import assess_gap
from finalprosports.domain.composition.policy.retrieval_text_policy import query_text
from finalprosports.domain.model import CaseQuery, ClientProfile, Diet, MealSlot, RetrievedCase
from finalprosports.infrastructure.adapter.outbound.persistence.service.case.retrieval_strategy_adapters import case_repository_for
from finalprosports.infrastructure.adapter.outbound.persistence.service.client.client_repository_output_adapter import ClientRepositoryOutputAdapter
from finalprosports.infrastructure.composition_root import CompositionRoot

from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()          # FPS_DATASET_DIR: the data tree lives outside the code repository
FLOOR_CEILING = {"normalized_key": (0.191, 0.275), "food_id": (0.285, 0.366)}       # Part A, NORMALIZATION_REPORT §7 (random floor; secondary)


def keys_of(d: Diet) -> frozenset[str]:
    return frozenset(i.normalized_key for m in d.meals for i in m.items if i.normalized_key)


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def precision_recall(hidden: frozenset, retrieved: frozenset) -> tuple[float, float]:
    """precision = |hidden ∩ retrieved| / |retrieved|, recall = |hidden ∩ retrieved| / |hidden| (retrieved = top-1 diet's items)."""
    inter = len(hidden & retrieved)
    return (inter / len(retrieved) if retrieved else 0.0, inter / len(hidden) if hidden else 0.0)


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


IRREPRESENTABLE_SHARE = 0.5
"""A diet more than half of whose items sit in the non-composable OTHER bucket is not a valid hold-out target.

The bucket holds the header shapes the vocabulary could not map, and the system is structurally forbidden to
propose inside it. A diet whose content lives mostly there cannot be reproduced by any engine, so scoring against
it measures the extraction, not the system. Such diets are DECLARED out of the evaluation rather than silently
scored low; `irrepresentable()` returns the count so it can be published as a limit of the system.
"""


def _other_share(d: Diet) -> float:
    total = sum(len(m.items) for m in d.meals)
    if not total:
        return 0.0
    return sum(len(m.items) for m in d.meals if m.slot is MealSlot.OTHER) / total


def scorable_keys(d: Diet) -> int:
    return sum(1 for m in d.meals if m.slot is not MealSlot.OTHER for i in m.items if i.normalized_key)


def irrepresentable(diets) -> list[Diet]:
    """The diets excluded from the evaluation for having nothing the system could be scored against.

    Two ways to get there, and the second is not implied by the first. A diet MOSTLY inside the non-composable
    bucket cannot be reproduced. A diet with NO scorable item at all -- everything either in the bucket or
    unmapped -- is worse: its target set is empty, and an empty set makes every overlap metric meaningless (the
    Jaccard of two empty sets read as 0, which showed up as a baseline that copies the previous version and scores
    0,9986 instead of 1 against it). Half a dozen diets sit exactly there without crossing the share threshold.
    """
    return [d for d in diets if _other_share(d) > IRREPRESENTABLE_SHARE or scorable_keys(d) == 0]


def eligible_queries(diets: dict[str, Diet], profiles: dict[str, ClientProfile]) -> list[Diet]:
    by_client: dict[str, list[Diet]] = defaultdict(list)
    for d in diets.values():
        if d.template_group_id is None:
            by_client[d.client_code].append(d)
    out = []
    for c, ds in by_client.items():
        p = profiles.get(c)
        if len(ds) >= 2 and p and p.sex is not None and p.age is not None and p.height_cm is not None:
            out.extend(sorted(ds, key=lambda d: d.id))
    excluded = {d.id for d in irrepresentable(out)}
    return [d for d in out if d.id not in excluded]


def archetype(p: ClientProfile) -> tuple:
    return (p.sex, p.age_bucket, p.goal)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--alpha", type=float, default=0.5, help="hybrid: weight of the normalised cosine")
    ap.add_argument("--strategies", nargs="*", default=[s.value for s in RetrievalStrategy], help="strategy names; hybrid accepts hybrid:<alpha> variants")
    ap.add_argument("--seed", type=int, default=42, help="random baselines")
    ap.add_argument("--threshold", type=float, default=0.80, help="secondary gap signal (attribute score)")
    ap.add_argument("--limit", type=int, default=None, help="debug: only the first N queries")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "retrieval_strategies.json")
    args = ap.parse_args()

    root = CompositionRoot.from_env()
    pid = root.configured_professional_id          # offline harness: no request, no token
    sf = root.case_repository._sf  # noqa: SLF001 (same session factory for every strategy)
    def make(name):
        base_name, _, a = name.partition(':')
        return case_repository_for(base_name, sf, alpha=float(a) if a else args.alpha)
    repos = {s: make(s) for s in args.strategies}
    services = {s: RetrieveSimilarCasesService(root.embedder, r, gaps=None) for s, r in repos.items()}
    base = next(iter(repos.values()))
    diets = base.all_diets(pid)
    profiles = {p.client_code: p for p in ClientRepositoryOutputAdapter(sf).list_case_profiles(pid)}
    queries = eligible_queries(diets, profiles)
    if args.limit:
        queries = queries[: args.limit]
    print(json.dumps({"diets": len(diets), "queries": len(queries), "k": args.k, "strategies": list(repos)}))

    per = {s: defaultdict(list) for s in repos}
    sets = {i: (keys_of(d), d.food_ids) for i, d in diets.items()}
    hidden_sets = {d.id: sets[d.id] for d in queries}
    rng = random.Random(args.seed)
    by_client: dict[str, list[str]] = defaultdict(list)
    for d in diets.values():
        by_client[d.client_code].append(d.id)
    ref = defaultdict(list)                       # floor / ceiling on THIS query set
    gap_counter = defaultdict(int)                # how many of the queries trigger each gap condition (attributes strategy)
    gap_repo = repos.get('attributes') or make('attributes')
    for n, hidden in enumerate(queries, 1):
        profile = dataclasses.replace(profiles[hidden.client_code], goal=hidden.goal)
        excluded = services[next(iter(services))].mandatory_exclusions(pid, profile)
        assert hidden.id in excluded
        hk0, hf0 = hidden_sets[hidden.id]
        allowed = [i for i in diets if i not in excluded]
        same_goal = [i for i in allowed if diets[i].goal == hidden.goal] or allowed
        r1, r2 = rng.choice(allowed), rng.choice(same_goal)
        ref['floor_random_key'].append(jaccard(hk0, sets[r1][0])); ref['floor_random_food'].append(jaccard(hf0, sets[r1][1]))
        ref['floor_same_goal_key'].append(jaccard(hk0, sets[r2][0])); ref['floor_same_goal_food'].append(jaccard(hf0, sets[r2][1]))
        others = [i for i in by_client[hidden.client_code] if i != hidden.id and diets[i].template_group_id is None]
        jk_o = sorted((jaccard(hk0, sets[i][0]) for i in others), reverse=True); jf_o = sorted((jaccard(hf0, sets[i][1]) for i in others), reverse=True)
        ref['ceiling_key'].append(statistics.fmean(jk_o)); ref['ceiling_food'].append(statistics.fmean(jf_o))
        if len(jk_o) > 1:
            ref['ceiling_key_excl_nn'].append(statistics.fmean(jk_o[1:])); ref['ceiling_food_excl_nn'].append(statistics.fmean(jf_o[1:]))
        t0 = time.perf_counter(); vec = tuple(root.embedder.embed_query(query_text(profile))); embed_ms = (time.perf_counter() - t0) * 1000
        for s, repo in repos.items():
            q = CaseQuery(profile, vec if repo.requires_embedding else None)
            t1 = time.perf_counter(); hits: tuple[RetrievedCase, ...] = repo.find_similar(pid, q, args.k, excluded); find_ms = (time.perf_counter() - t1) * 1000
            assert hits and not ({h.diet.id for h in hits} & excluded)
            m = per[s]
            m["latency_ms"].append(find_ms + (embed_ms if repo.requires_embedding else 0.0))
            m["find_ms"].append(find_ms)
            m["top1_same_goal"].append(hits[0].diet.goal == hidden.goal)
            m["topk_same_goal"].append(sum(h.diet.goal == hidden.goal for h in hits) / len(hits))
            m["archetype_in_topk"].append(any(h.case_profile and archetype(h.case_profile) == archetype(profile) for h in hits))
            hk, hf = hidden_sets[hidden.id]
            jk = [jaccard(hk, keys_of(h.diet)) for h in hits]
            jf = [jaccard(hf, h.diet.food_ids) for h in hits]
            m["j_key_top1"].append(jk[0]); m["j_key_best"].append(max(jk)); m["j_key_mean"].append(statistics.fmean(jk))
            m["j_food_top1"].append(jf[0]); m["j_food_best"].append(max(jf)); m["j_food_mean"].append(statistics.fmean(jf))
            m["top1_score"].append(hits[0].score.total)
            m["top1_size_ratio"].append(len(keys_of(hits[0].diet)) / max(1, len(hk)))
            pk, rk = precision_recall(hk, keys_of(hits[0].diet)); pf, rf = precision_recall(hf, hits[0].diet.food_ids)
            m["prec_key"].append(pk); m["rec_key"].append(rk); m["prec_food"].append(pf); m["rec_food"].append(rf)
            if s == "attributes":
                a = assess_gap(gap_repo.candidate_counts(pid, profile, excluded), args.k, hits[0].score.total, args.threshold)
                for cond in a.triggered:
                    gap_counter[cond] += 1
                gap_counter["any"] += a.is_gap
                gap_counter["archetype_lt2"] += a.counts.archetype < 2
                gap_counter["restrictions_declared"] += a.counts.restrictions_declared > 0
        if n % 100 == 0:
            print(f"  {n}/{len(queries)}", file=sys.stderr)

    same_goal_floor = {"normalized_key": statistics.fmean(ref["floor_same_goal_key"]), "food_id": statistics.fmean(ref["floor_same_goal_food"])}
    ceiling = {"normalized_key": statistics.fmean(ref["ceiling_key_excl_nn"]), "food_id": statistics.fmean(ref["ceiling_food_excl_nn"])}

    def norm(v, g):                              # PRIMARY: floor = random diet of the SAME goal (the goal is user input, not merit)
        return round((v - same_goal_floor[g]) / (ceiling[g] - same_goal_floor[g]), 3)

    def norm_random(v, g):                       # secondary: Part A random floor / ceiling
        lo, hi = FLOOR_CEILING[g]
        return round((v - lo) / (hi - lo), 3)

    results = {}
    for s, m in per.items():
        r = {"queries": len(m["latency_ms"]),
             "top1_same_goal_rate": round(statistics.fmean(m["top1_same_goal"]), 3),
             "topk_same_goal_rate": round(statistics.fmean(m["topk_same_goal"]), 3),
             "archetype_in_topk_rate": round(statistics.fmean(m["archetype_in_topk"]), 3),
             "jaccard_normalized_key": {"top1": round(statistics.fmean(m["j_key_top1"]), 4), "top1_normalised": norm(statistics.fmean(m["j_key_top1"]), "normalized_key"),
                                        "top1_normalised_vs_random_floor": norm_random(statistics.fmean(m["j_key_top1"]), "normalized_key"),
                                        "precision_top1": round(statistics.fmean(m["prec_key"]), 4), "recall_top1": round(statistics.fmean(m["rec_key"]), 4),
                                        "best_of_topk": round(statistics.fmean(m["j_key_best"]), 4), "mean_of_topk": round(statistics.fmean(m["j_key_mean"]), 4)},
             "jaccard_food_id": {"top1": round(statistics.fmean(m["j_food_top1"]), 4), "top1_normalised": norm(statistics.fmean(m["j_food_top1"]), "food_id"),
                                 "top1_normalised_vs_random_floor": norm_random(statistics.fmean(m["j_food_top1"]), "food_id"),
                                 "precision_top1": round(statistics.fmean(m["prec_food"]), 4), "recall_top1": round(statistics.fmean(m["rec_food"]), 4),
                                 "best_of_topk": round(statistics.fmean(m["j_food_best"]), 4), "mean_of_topk": round(statistics.fmean(m["j_food_mean"]), 4)},
             "latency_ms": {"p50": round(pct(m["latency_ms"], .5), 1), "p95": round(pct(m["latency_ms"], .95), 1),
                            "find_only_p50": round(pct(m["find_ms"], .5), 1), "find_only_p95": round(pct(m["find_ms"], .95), 1)},
             "top1_score": {"p05": round(pct(m["top1_score"], .05), 4), "p50": round(pct(m["top1_score"], .5), 4), "min": round(min(m["top1_score"]), 4)},
             "top1_size_ratio_mean": round(statistics.fmean(m["top1_size_ratio"]), 3)}
        results[s] = r

    goal_share = defaultdict(int)
    for d in diets.values():
        goal_share[d.goal.value] += 1
    chance = sum((v / len(diets)) ** 2 for v in goal_share.values())
    report = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "protocol": {"queries": len(queries), "k": args.k, "eligibility": "non-template diets of clients with >= 2 non-template diets and complete demographics (sex, age, height)",
              "exclusions": "all diets of the client + all diets of the client's template groups", "query": "client profile + hidden diet's goal; retrieval text header (E3.1)",
              "chance_top1_same_goal": round(chance, 3), "floor_ceiling_part_a": FLOOR_CEILING},
              "normalisation": {"primary": "floor = random diet of the same goal on this query set; ceiling = same client excl. nearest neighbour on this query set",
                                "secondary": "Part A random floor / ceiling", "same_goal_floor": {k: round(v, 4) for k, v in same_goal_floor.items()}, "ceiling": {k: round(v, 4) for k, v in ceiling.items()}},
              "reference_on_this_query_set": {k: round(statistics.fmean(v), 4) for k, v in ref.items()},
              "gap_conditions_attributes": {"queries": len(queries), "threshold": args.threshold, **dict(gap_counter)},
              "alpha_curve_hybrid": {s.split(":")[1] if ":" in s else "0.5": {"jaccard_key_top1": results[s]["jaccard_normalized_key"]["top1"], "jaccard_food_top1": results[s]["jaccard_food_id"]["top1"],
                                     "size_ratio": results[s]["top1_size_ratio_mean"]} for s in results if s.startswith("hybrid")},
              "results": results}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nqueries={len(queries)}  k={args.k}  chance(top1 same goal)={chance:.3f}")
    print("reference on this query set:", {k: round(statistics.fmean(v), 4) for k, v in ref.items()})
    print("gap conditions (attributes):", dict(gap_counter))
    print(f"{'strategy':22s} {'top1goal':>8s} {'topKgoal':>8s} {'archK':>6s} | {'J key top1':>10s} {'norm':>6s} {'bestK':>6s} | {'J food top1':>11s} {'norm':>6s} {'bestK':>6s} | {'p50ms':>6s} {'p95ms':>6s}")
    for s, r in results.items():
        jk, jf, lat = r["jaccard_normalized_key"], r["jaccard_food_id"], r["latency_ms"]
        print(f"{s:22s} {r['top1_same_goal_rate']:8.3f} {r['topk_same_goal_rate']:8.3f} {r['archetype_in_topk_rate']:6.3f} | {jk['top1']:10.4f} {jk['top1_normalised']:6.3f} {jk['best_of_topk']:6.4f} | "
              f"{jf['top1']:11.4f} {jf['top1_normalised']:6.3f} {jf['best_of_topk']:6.4f} | {lat['p50']:6.1f} {lat['p95']:6.1f} | size {r['top1_size_ratio_mean']:.2f} | P/R key {jk['precision_top1']:.3f}/{jk['recall_top1']:.3f} food {jf['precision_top1']:.3f}/{jf['recall_top1']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
