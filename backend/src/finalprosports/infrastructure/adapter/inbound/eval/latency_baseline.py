# -*- coding: utf-8 -*-
"""
Latency baseline of the retrieval engine (E2.7, measured with statistics, not with one sample).

~50 varied query profiles (every goal x sex x age bucket, deterministic sample) are run through the SAME components
the API uses (wired by the composition root): phase 1 = vectorising the query with e5 in process, phase 2 = the
pgvector cosine query without index (professional_id filter, top-5), plus the goal-prefiltered variant of phase 2.
Reports p50 / p95 / mean / max per phase and writes _dataset/latency_baseline.json.

Run (venv, database loaded and vectorised):  python -m finalprosports.infrastructure.adapter.inbound.eval.latency_baseline
Nothing is printed but timings, counts and environment versions.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path

from finalprosports.domain.composition.policy.retrieval_text_policy import query_text
from finalprosports.domain.model import CaseQuery, ClientProfile, Goal
from finalprosports.infrastructure.composition_root import CompositionRoot

from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()          # FPS_DATASET_DIR: the data tree lives outside the code repository
GOALS = [g for g in Goal if g is not Goal.UNCLASSIFIED]
AGES = {"<25": 22, "25-39": 31, "40-54": 46, "55+": 58}


def query_profiles(n: int, professional_id: str, seed: int = 42) -> list[ClientProfile]:
    combos = list(itertools.product(GOALS, ("M", "F"), AGES.items()))          # 8 x 2 x 4 = 64
    rng = random.Random(seed)
    chosen = rng.sample(combos, min(n, len(combos)))
    return [ClientProfile(f"QUERY_{i:03d}", professional_id, sex, age, 178 if sex == "M" else 165, 3 + (i % 4), goal=goal)
            for i, (goal, sex, (_, age)) in enumerate(chosen)]


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summary(ms: list[float]) -> dict:
    return {"n": len(ms), "p50_ms": round(pct(ms, 0.50), 2), "p95_ms": round(pct(ms, 0.95), 2), "mean_ms": round(statistics.fmean(ms), 2),
            "min_ms": round(min(ms), 2), "max_ms": round(max(ms), 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "latency_baseline.json")
    args = ap.parse_args()

    t0 = time.perf_counter()
    root = CompositionRoot.from_env()
    startup_s = time.perf_counter() - t0
    pid = root.configured_professional_id          # offline harness: no request, no token
    embedder = root.embedder
    from finalprosports.infrastructure.adapter.outbound.persistence.service.case.retrieval_strategy_adapters import GoalFilteredVectorCaseRepositoryAdapter, VectorCaseRepositoryAdapter
    cases, goal_cases = VectorCaseRepositoryAdapter(root.case_repository._sf), GoalFilteredVectorCaseRepositoryAdapter(root.case_repository._sf)  # noqa: SLF001 (same session factory)
    profiles = query_profiles(args.n, pid)

    for p in profiles[: args.warmup]:                                           # warm-up: model kernels, connection pool, plan cache
        cases.find_similar(pid, CaseQuery(p, tuple(embedder.embed_query(query_text(p)))), args.k, frozenset())

    embed_ms, sql_ms, sql_goal_ms, total_ms, per_query = [], [], [], [], []
    for p in profiles:
        q = query_text(p)
        t1 = time.perf_counter(); vec = tuple(embedder.embed_query(q)); t2 = time.perf_counter()
        hits = cases.find_similar(pid, CaseQuery(p, vec), args.k, frozenset()); t3 = time.perf_counter()
        hits_goal = goal_cases.find_similar(pid, CaseQuery(p, vec), args.k, frozenset()); t4 = time.perf_counter()
        assert len(hits) == args.k and 0 < len(hits_goal) <= args.k, (len(hits), len(hits_goal))   # a goal may have < k diets (mantenimiento: 3)
        e, s, sg = (t2 - t1) * 1000, (t3 - t2) * 1000, (t4 - t3) * 1000
        embed_ms.append(e); sql_ms.append(s); sql_goal_ms.append(sg); total_ms.append(e + s)
        per_query.append({"goal": p.goal.value, "sex": p.sex, "age_bucket": p.age_bucket, "embed_ms": round(e, 2), "sql_ms": round(s, 2),
                          "sql_goal_filtered_ms": round(sg, 2), "goal_filtered_hits": len(hits_goal), "top1_cosine": round(hits[0].score.vector, 4), "top1_same_goal": hits[0].diet.goal == p.goal})

    diag = cases.diagnostics(pid)
    import torch
    report = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"queries": len(profiles), "warmup_excluded": args.warmup, "k": args.k, "seed": 42, "profile_grid": "8 goals x 2 sexes x 4 age buckets, deterministic sample",
                     "phase_1": "e5 query embedding in process (CPU)", "phase_2": "pgvector cosine ORDER BY <=> LIMIT k, sequential scan, professional_id filter, plus hydration of the k diets (2 statements in total, E3.3)",
                     "phase_2_goal": "phase 2 with goal prefilter (goal_filtered_vector strategy)", "retrieval_text": "E3.1 structured document/query text"},
        "corpus": {"diets": diag["diets"], "with_embedding": diag["with_embedding"]},
        "environment": {"python": platform.python_version(), "os": platform.platform(), "cpu": platform.processor(), "cpu_count": os.cpu_count(),
                        "torch": torch.__version__, "torch_threads": torch.get_num_threads(), "postgres": diag["postgres"], "pgvector_extension": diag["pgvector_extension"],
                        "embedding_model": os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-base"), "startup_s": round(startup_s, 1)},
        "embed_query_ms": summary(embed_ms), "sql_top_k_ms": summary(sql_ms), "sql_top_k_goal_filtered_ms": summary(sql_goal_ms), "end_to_end_ms": summary(total_ms),
        "top1_same_goal_rate": round(sum(q["top1_same_goal"] for q in per_query) / len(per_query), 3),
        "per_query": per_query,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "per_query"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
