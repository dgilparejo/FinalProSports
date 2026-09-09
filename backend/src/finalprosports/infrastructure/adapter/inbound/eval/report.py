# -*- coding: utf-8 -*-
"""
E5 · Evaluation report: ONE command regenerates every table (JSON + Markdown) and figure (PNG) of the results chapter from
the per-query records of the harness (`loo_harness --final`), the k x threshold grid and the retrieval benchmark.

  python -m finalprosports.infrastructure.adapter.inbound.eval.report            # tables + figures from the existing records
  python -m finalprosports.infrastructure.adapter.inbound.eval.report --rerun    # runs the harness first (--final and --recurrent; needs the database)

Output (GENERATED, not versioned; aggregates only, pseudonymous ids): docs/evaluation/results.json, RESULTS.md, figures/figNN_*.png.
Contents: success table under both ceiling protocols; bootstrap 95 % CIs (10.000 resamples, fixed seed) and Wilcoxon signed-rank
tests of the paired differences; stratification by goal / sex / age bucket (cells with n < 30 flagged); cumulative ablation whose
last row before the ceiling is the DELIVERED configuration (strategy -> plausibility layer -> validator), with the plausibility
violations each stage leaves; per-slot Jaccard; failure analysis of the 20 worst queries; availability and gaps; figures with Spanish labels.
`tests/evaluation/test_report_consistency.py` checks that RESULTS.md is exactly what results.json renders.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from finalprosports.infrastructure.config.paths import dataset_dir, docs_dir

DATASET_DIR = dataset_dir()          # FPS_DATASET_DIR: the data tree lives outside the code repository
DOCS_DIR = docs_dir() / "evaluation"
N_BOOT = 10_000
SEED = 42
MIN_N = 30
GRAN = {"j_key": "normalized_key", "j_food": "food_id", "j_family": "familia"}
GOAL_ORDER = ["volumen_masa", "ayuno_intermitente", "definicion_grasa", "cetosis_keto", "descarga_carga", "hipocalorica", "alta_en_fibra", "mantenimiento"]
SLOT_ORDER = ["DESAYUNO", "MEDIA MAÑANA", "ALMUERZO", "COMIDA", "MERIENDA", "CENA", "RECENA", "ANTES DE ENTRENAR", "MITAD DE ENTRENAMIENTO", "DESPUES DE ENTRENAR", "BATIDO", "OTHER"]


# ----------------------------------------------------------------------------------------------------------------- utils
def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(float(statistics.fmean(xs)), 4) if xs else None


def r(x, n=4):
    return None if x is None else round(float(x), n)


def load_records():
    recs = [json.loads(l) for l in (DATASET_DIR / "composer_per_query.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    meta = json.loads((DATASET_DIR / "composer_per_query_meta.json").read_text(encoding="utf-8"))
    return recs, meta


def paired_stats(a: list[float], b: list[float], rng) -> dict:
    """a - b: mean difference, bootstrap 95 % CI (percentile, N_BOOT resamples) and Wilcoxon signed-rank p-value."""
    import numpy as np
    from scipy.stats import wilcoxon
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    n = len(d)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    boots = d[idx].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    try:
        p = float(wilcoxon(d, zero_method="wilcox", alternative="two-sided").pvalue) if np.any(d != 0) else 1.0
    except ValueError:
        p = 1.0
    return {"n": n, "mean_diff": r(d.mean()), "ci95": [r(lo), r(hi)], "excludes_zero": bool(lo > 0 or hi < 0), "wilcoxon_p": float(f"{p:.3g}"),
            "share_positive": r((d > 0).mean(), 3)}


# --------------------------------------------------------------------------------------------------------------- builders
DELIVERED = "validated_plausible"       # strategy -> plausibility layer (complete_structure + normalize_quantities) -> validator: what the API serves


def success_tables(recs):
    sub = [x for x in recs if x["ceiling_excl_nn"]]
    out = {}
    for label, rows, ceiling_key in (("A_excl_nearest_neighbour", sub, "ceiling_excl_nn"), ("B_incl_nearest_neighbour", recs, "ceiling_incl_nn")):
        tab = {"queries": len(rows)}
        for m, g in GRAN.items():
            f, c, comp, ce = (mean([x["variants"]["floor_same_goal"][m] for x in rows]), mean([x["variants"]["copy_top1"][m] for x in rows]),
                              mean([x["variants"]["composer_raw"][m] for x in rows]), mean([x[ceiling_key][m] for x in rows]))
            # La configuracion ENTREGADA es una columna de la tabla titular, no una fila de la ablacion: el capitulo de
            # resultados tiene que poder leerse sobre lo que la API sirve sin recomponerlo de dos secciones distintas.
            dl = mean([x["variants"][DELIVERED][m] for x in rows])
            tab[g] = {"floor_same_goal": f, "copy_top1": c, "composer": comp, "delivered": dl, "ceiling": ce, "composer_vs_copy": r(comp - c), "composer_vs_ceiling": r(comp - ce),
                      "delivered_vs_copy": r(dl - c), "delivered_vs_ceiling": r(dl - ce),
                      "composer_normalised": r((comp - f) / (ce - f), 3) if ce != f else None, "copy_normalised": r((c - f) / (ce - f), 3) if ce != f else None,
                      "delivered_normalised": r((dl - f) / (ce - f), 3) if ce != f else None}
        out[label] = tab
    return out


def statistics_tables(recs):
    import numpy as np
    rng = np.random.default_rng(SEED)
    sub = [x for x in recs if x["ceiling_excl_nn"]]
    out = {"method": f"bootstrap percentile 95 % CI over paired differences, {N_BOOT} resamples, seed {SEED}; Wilcoxon signed-rank two-sided", "pairs": {}}
    pairs = {
        "composer - copy_top1": (recs, lambda x, m: x["variants"]["composer_raw"][m], lambda x, m: x["variants"]["copy_top1"][m]),
        "composer - ceiling_excl_nn (subset)": (sub, lambda x, m: x["variants"]["composer_raw"][m], lambda x, m: x["ceiling_excl_nn"][m]),
        "composer - ceiling_incl_nn": (recs, lambda x, m: x["variants"]["composer_raw"][m], lambda x, m: x["ceiling_incl_nn"][m]),
        "composer - floor_same_goal": (recs, lambda x, m: x["variants"]["composer_raw"][m], lambda x, m: x["variants"]["floor_same_goal"][m]),
        "copy_top1 - floor_same_goal": (recs, lambda x, m: x["variants"]["copy_top1"][m], lambda x, m: x["variants"]["floor_same_goal"][m]),
        "composer - composer_no_degradation": (recs, lambda x, m: x["variants"]["composer_raw"][m], lambda x, m: x["variants"]["composer_no_degradation"][m]),
        "validated_strict - composer (overlap)": (recs, lambda x, m: x["variants"]["validated_strict"][m], lambda x, m: x["variants"]["composer_raw"][m]),
        "entregada (validador + plausibilidad) - validated_strict": (recs, lambda x, m: x["variants"]["validated_plausible"][m], lambda x, m: x["variants"]["validated_strict"][m]),
        "entregada - composer": (recs, lambda x, m: x["variants"]["validated_plausible"][m], lambda x, m: x["variants"]["composer_raw"][m]),
        "entregada - copy_top1": (recs, lambda x, m: x["variants"]["validated_plausible"][m], lambda x, m: x["variants"]["copy_top1"][m]),
        "entregada - ceiling_excl_nn (subset)": (sub, lambda x, m: x["variants"]["validated_plausible"][m], lambda x, m: x["ceiling_excl_nn"][m]),
        "entregada - ceiling_incl_nn": (recs, lambda x, m: x["variants"]["validated_plausible"][m], lambda x, m: x["ceiling_incl_nn"][m]),
    }
    for name, (rows, fa, fb) in pairs.items():
        out["pairs"][name] = {GRAN[m]: paired_stats([fa(x, m) for x in rows], [fb(x, m) for x in rows], rng) for m in GRAN}
    comp_rows = [x for x in recs if x["variants"]["composer_raw"]["compliance_cond"] is not None and x["variants"]["validated_strict"]["compliance_cond"] is not None]
    out["pairs"]["validated_strict - composer (conditional compliance)"] = {"cumplimiento condicional": paired_stats(
        [x["variants"]["validated_strict"]["compliance_cond"] for x in comp_rows], [x["variants"]["composer_raw"]["compliance_cond"] for x in comp_rows], rng)}
    hid_rows = [x for x in recs if x["hidden_compliance_cond"] is not None and x["variants"]["validated_strict"]["compliance_cond"] is not None]
    out["pairs"]["validated_strict - hidden diet (conditional compliance)"] = {"cumplimiento condicional": paired_stats(
        [x["variants"]["validated_strict"]["compliance_cond"] for x in hid_rows], [x["hidden_compliance_cond"] for x in hid_rows], rng)}
    out["pairs"]["entregada - validated_strict (violaciones de plausibilidad por consulta)"] = {"violaciones": paired_stats(
        [x["plausibility"]["validated_plausible"]["violations"] for x in recs], [x["plausibility"]["validated_strict"]["violations"] for x in recs], rng)}
    return out


def strata(recs, key_fn, order=None):
    groups = defaultdict(list)
    for x in recs:
        groups[key_fn(x)].append(x)
    keys = [k for k in (order or []) if k in groups] + sorted(k for k in groups if not order or k not in order)
    out = {}
    for k in keys:
        rows = groups[k]
        cell = {"n": len(rows), "conclusive": len(rows) >= MIN_N}
        for m, g in GRAN.items():
            cell[g] = {"floor_same_goal": mean([x["variants"]["floor_same_goal"][m] for x in rows]), "copy_top1": mean([x["variants"]["copy_top1"][m] for x in rows]),
                       "composer": mean([x["variants"]["composer_raw"][m] for x in rows]), "delivered": mean([x["variants"][DELIVERED][m] for x in rows]),
                       "ceiling_incl_nn": mean([x["ceiling_incl_nn"][m] for x in rows])}
        cell["composer_vs_copy_key"] = r(cell["normalized_key"]["composer"] - cell["normalized_key"]["copy_top1"])
        cell["delivered_vs_copy_key"] = r(cell["normalized_key"]["delivered"] - cell["normalized_key"]["copy_top1"])
        cell["size_composer"] = mean([x["variants"]["composer_raw"]["size"] for x in rows])
        cell["size_delivered"] = mean([x["variants"][DELIVERED]["size"] for x in rows])
        out[str(k)] = cell
    return out


def stratification(recs):
    return {"min_n_conclusive": MIN_N,
            "by_goal": strata(recs, lambda x: x["goal"], GOAL_ORDER),
            "by_sex": strata(recs, lambda x: x["sex"] or "desconocido", ["M", "F", "desconocido"]),
            "by_age_bucket": strata(recs, lambda x: x["age_bucket"], ["<25", "25-39", "40-54", "55+", "edad_NA"]),
            "generic_assumption": {"with": {g: {"copy_top1": mean([x["variants"]["copy_top1"][m] for x in recs]), "composer": mean([x["variants"]["composer_raw"][m] for x in recs]),
                                                "ceiling_incl_nn": mean([x["ceiling_incl_nn"][m] for x in recs])} for m, g in (("j_key", "normalized_key"), ("j_food", "food_id"))},
                                   "without": {g: {"copy_top1": mean([x["variants"]["copy_top1"][m] for x in recs]), "composer": mean([x["variants"]["composer_raw"][m] for x in recs]),
                                                   "ceiling_incl_nn": mean([x["ceiling_incl_nn"][m] for x in recs])} for m, g in (("j_key_no_generic", "normalized_key"), ("j_food_no_generic", "food_id"))}}}


ABLATION_STEPS = [("Suelo: dieta aleatoria del mismo objetivo", "floor_same_goal"), ("+ recuperación por atributos (copiar top-1)", "copy_top1"),
                  ("+ compositor por consenso (sin degradación)", "composer_no_degradation"), ("+ degradación en objetivos minoritarios", "composer_raw"),
                  ("+ validador (restricciones + prohibiciones forzables)", "validated_strict"),
                  ("+ capa de plausibilidad (estructura desde los casos + cantidades en la envolvente) = **configuración entregada**", DELIVERED)]
ABLATION_BRANCHES = [("Rama no entregada: validador + reglas de confianza baja activadas", "validated_low_rules"),
                     ("Rama no entregada: capa de plausibilidad sin validador", "plausible_unvalidated")]


def _ablation_row(recs, label, v):
    row = {"step": label, "variant": v}
    for m, g in GRAN.items():
        row[g] = mean([x["variants"][v][m] for x in recs])
    row["compliance_all"] = mean([x["variants"][v]["compliance_all_low" if v == "validated_low_rules" else "compliance_all"] for x in recs])
    row["compliance_cond"] = mean([x["variants"][v]["compliance_cond_low" if v == "validated_low_rules" else "compliance_cond"] for x in recs])
    row["forced"] = mean([x["variants"][v]["forced"] for x in recs]) if v.startswith("validated") else None
    row["size"] = mean([x["variants"][v]["size"] for x in recs])
    has_plaus = all(v in x["plausibility"] for x in recs)
    row["plausibility_violations"] = mean([x["plausibility"][v]["violations"] for x in recs]) if has_plaus else None
    row["share_with_violation"] = r(sum(x["plausibility"][v]["violations"] > 0 for x in recs) / len(recs), 3) if has_plaus else None
    return row


def ablation(recs):
    rows, prev = [], None
    for label, v in ABLATION_STEPS:
        row = _ablation_row(recs, label, v)
        row["delta"] = {g: r(row[g] - prev[g]) for g in GRAN.values()} if prev else None
        rows.append(row); prev = row
    sub = [x for x in recs if x["ceiling_excl_nn"]]
    ceiling = {"step": f"Techo: autoconsistencia (con vecino, {len(recs)}) / (sin vecino, {len(sub)})", "variant": "ceiling"}
    for m, g in GRAN.items():
        ceiling[g] = mean([x["ceiling_incl_nn"][m] for x in recs]); ceiling[g + "_excl_nn"] = mean([x["ceiling_excl_nn"][m] for x in sub])
    ceiling["compliance_all"] = mean([x["hidden_compliance_all"] for x in recs]); ceiling["compliance_cond"] = mean([x["hidden_compliance_cond"] for x in recs])
    ceiling["plausibility_violations"] = None; ceiling["share_with_violation"] = None; ceiling["forced"] = None; ceiling["size"] = 1.0
    rows.append(ceiling)
    return rows


def ablation_extra(recs):
    """What the plausibility layer does and what it leaves: changes applied per query, violations by check before / after, and the
    professional's own diets against his envelope (by construction of a p05-p95 band about a tenth of his quantities lie outside)."""
    branches = [_ablation_row(recs, label, v) for label, v in ABLATION_BRANCHES]
    kinds = Counter()
    for x in recs:
        kinds.update(x["plausibility_changes"])
    by_check = {v: dict(sum((Counter(x["plausibility"][v]["by_check"]) for x in recs), Counter())) for v in ("composer_raw", "validated_strict", "plausible_unvalidated", DELIVERED)}
    out_of_band = sum(x["hidden_quantities_out_of_band"] for x in recs); checked = sum(x["hidden_quantities_checked"] for x in recs)
    return {"delivered_variant": DELIVERED, "branches": branches, "changes_per_query": {k: r(v / len(recs), 3) for k, v in sorted(kinds.items())},
            "queries_with_any_change": sum(1 for x in recs if x["plausibility_changes"]),
            "violations_by_check": by_check,
            "hidden_diet_vs_envelope": {"quantities_checked": checked, "out_of_band": out_of_band, "share_out_of_band": r(out_of_band / checked, 3) if checked else None,
                                        "per_query": r(out_of_band / len(recs), 3)}}


def per_slot(recs):
    out = {}
    for slot in SLOT_ORDER:
        rows = [x["slot_jaccard"][slot] for x in recs if slot in x["slot_jaccard"]]
        if not rows:
            continue
        out[slot] = {"n": len(rows), "hidden_items_mean": mean([s["hidden_items"] for s in rows]), "composer": mean([s["composer"] for s in rows]), "copy_top1": mean([s["copy"] for s in rows]),
                     "validated": mean([s["validated"] for s in rows]), "delivered": mean([s.get("delivered") for s in rows]), "ceiling_incl_nn": mean([s["ceiling_incl_nn"] for s in rows]),
                     "composer_present_share": mean([1.0 if s["composer_present"] else 0.0 for s in rows]), "composer_vs_copy": r(mean([s["composer"] for s in rows]) - mean([s["copy"] for s in rows]))}
    return out


def failures(recs, n=20):
    minority = {"alta_en_fibra", "hipocalorica", "mantenimiento"}
    # Las peores consultas de LO QUE SE ENTREGA. Antes se ordenaba por el compositor crudo, que no es lo que sirve la
    # API: una consulta que el validador o la capa de plausibilidad arreglan no es un fallo del sistema entregado.
    worst = sorted(recs, key=lambda x: (x["variants"][DELIVERED]["j_key"], x["diet_id"]))[:n]
    rows = [{"diet_id": x["diet_id"], "goal": x["goal"], "sex": x["sex"], "age_bucket": x["age_bucket"], "hidden_items": x["hidden_items"], "hidden_slots": len(x["hidden_slots"]),
             "same_goal_available": x["same_goal_available"], "same_goal_in_k": x["same_goal_in_k"], "gap": x["gap_triggered"], "degradation": x["degradation"],
             "j_key_delivered": x["variants"][DELIVERED]["j_key"],
             "j_key_composer": x["variants"]["composer_raw"]["j_key"], "j_key_copy": x["variants"]["copy_top1"]["j_key"], "j_key_ceiling_incl_nn": x["ceiling_incl_nn"]["j_key"],
             "size_composer": x["variants"]["composer_raw"]["size"], "size_delivered": x["variants"][DELIVERED]["size"]} for x in worst]
    all_items = [x["hidden_items"] for x in recs]
    summary = {"n": len(rows),
               "share_minority_goal": r(sum(w["goal"] in minority for w in rows) / len(rows), 3), "share_minority_goal_overall": r(sum(x["goal"] in minority for x in recs) / len(recs), 3),
               "share_gap": r(sum(bool(w["gap"]) for w in rows) / len(rows), 3), "share_gap_overall": r(sum(bool(x["gap_triggered"]) for x in recs) / len(recs), 3),
               "share_female": r(sum(w["sex"] == "F" for w in rows) / len(rows), 3), "share_female_overall": r(sum(x["sex"] == "F" for x in recs) / len(recs), 3),
               "hidden_items_mean": mean([w["hidden_items"] for w in rows]), "hidden_items_mean_overall": mean(all_items), "hidden_items_median_overall": statistics.median(all_items),
               "share_hidden_items_lt_15": r(sum(w["hidden_items"] < 15 for w in rows) / len(rows), 3), "share_hidden_items_lt_15_overall": r(sum(x < 15 for x in all_items) / len(all_items), 3),
               "ceiling_incl_nn_mean": mean([w["j_key_ceiling_incl_nn"] for w in rows]), "ceiling_incl_nn_mean_overall": mean([x["ceiling_incl_nn"]["j_key"] for x in recs]),
               "copy_beats_composer": sum(w["j_key_copy"] > w["j_key_composer"] for w in rows),
               "copy_beats_delivered": sum(w["j_key_copy"] > w["j_key_delivered"] for w in rows),
               "ranked_by": DELIVERED,
               "goals": dict(Counter(w["goal"] for w in rows)), "slots_mean": mean([w["hidden_slots"] for w in rows]), "slots_mean_overall": mean([len(x["hidden_slots"]) for x in recs])}
    return {"worst": rows, "summary": summary}


def availability(recs, meta):
    minority_rows = [x for x in recs if x["same_goal_available"] < meta["params"]["k"]]
    return {"k": meta["params"]["k"], "k_effective_distribution": dict(Counter(x["k_effective"] for x in recs)),
            "degradation_modes": dict(Counter(x["degradation"] for x in recs)),
            "queries_with_fewer_than_k_same_goal_available": len(minority_rows),
            "gap_conditions": dict(Counter(c for x in recs for c in x["gap_triggered"])), "queries_with_any_gap": sum(bool(x["gap_triggered"]) for x in recs),
            "minority_subset": {"n": len(minority_rows), "j_key_copy": mean([x["variants"]["copy_top1"]["j_key"] for x in minority_rows]),
                                "j_key_composer_no_degradation": mean([x["variants"]["composer_no_degradation"]["j_key"] for x in minority_rows]),
                                "j_key_composer_with_degradation": mean([x["variants"]["composer_raw"]["j_key"] for x in minority_rows]),
                                "j_key_delivered": mean([x["variants"][DELIVERED]["j_key"] for x in minority_rows])},
            "majority_subset": {"n": len(recs) - len(minority_rows), "j_key_copy": mean([x["variants"]["copy_top1"]["j_key"] for x in recs if x["same_goal_available"] >= meta["params"]["k"]]),
                                "j_key_composer": mean([x["variants"]["composer_raw"]["j_key"] for x in recs if x["same_goal_available"] >= meta["params"]["k"]]),
                                "j_key_delivered": mean([x["variants"][DELIVERED]["j_key"] for x in recs if x["same_goal_available"] >= meta["params"]["k"]])}}


def recurrent_tables():
    path = DATASET_DIR / "recurrent_per_query.jsonl"
    if not path.exists():
        return None
    import numpy as np
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    meta = json.loads((DATASET_DIR / "recurrent_per_query_meta.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(SEED)
    variants = ["copy_previous", "cold_composer", "composer_history_candidates", "rotation_consensus_only", "rotation_composer", "rotation_validated", "routed",
                "routed_validated", "routed_delivered"]
    labels = {"copy_previous": "Copiar la versión anterior (línea base)", "cold_composer": "Compositor frío (cliente excluido, protocolo E5)",
              "composer_history_candidates": "Compositor con las versiones anteriores como candidatos", "rotation_consensus_only": "RotationComposer conservador (reemplazos solo del consenso)",
              "rotation_composer": "RotationComposer completo (objetivo de renovación del profesional)", "rotation_validated": "RotationComposer completo + validador",
              "routed": "Enrutado: mismo objetivo → rotación completa; cambio de objetivo → arquetipo (con historial como candidatos)",
              "routed_validated": "Enrutado + validador", "routed_delivered": "Enrutado + capa de plausibilidad + validador = **configuración entregada**"}
    table = {}
    for v in variants:
        table[v] = {"label": labels[v], "j_key": mean([r["variants"][v]["j_key"] for r in recs]), "j_food": mean([r["variants"][v]["j_food"] for r in recs]),
                    "j_family": mean([r["variants"][v]["j_family"] for r in recs]), "per_slot": mean([r["variants"][v]["per_slot"] for r in recs]),
                    "novelty_j_key": mean([r["variants"][v]["novelty_j_key"] for r in recs]), "novelty_j_food": mean([r["variants"][v]["novelty_j_food"] for r in recs]),
                    "size": mean([r["variants"][v]["size"] for r in recs]), "compliance_cond": mean([r["variants"][v]["compliance_cond"] for r in recs]),
                    "plausibility_violations": mean([r["plausibility"][v]["violations"] for r in recs]) if all(v in r["plausibility"] for r in recs) else None}
    human = {"novelty_j_key": mean([r["novelty_human"]["j_key"] for r in recs]), "novelty_j_food": mean([r["novelty_human"]["j_food"] for r in recs]),
             "renewal_same_goal": meta["renewal_targets"]["same_goal"], "renewal_goal_change": meta["renewal_targets"]["goal_change"]}
    pairs = {"rotation_consensus_only - copy_previous": ("rotation_consensus_only", "copy_previous"), "rotation_composer - copy_previous": ("rotation_composer", "copy_previous"),
             "cold_composer - copy_previous": ("cold_composer", "copy_previous"), "composer_history_candidates - cold_composer": ("composer_history_candidates", "cold_composer"),
             "rotation_composer - cold_composer": ("rotation_composer", "cold_composer"), "routed - copy_previous": ("routed", "copy_previous"),
             "routed - rotation_composer": ("routed", "rotation_composer"), "routed_delivered - routed": ("routed_delivered", "routed"),
             "routed_delivered - routed_validated": ("routed_delivered", "routed_validated"), "routed_delivered - copy_previous": ("routed_delivered", "copy_previous")}
    stats = {name: {g: paired_stats([r["variants"][a][m] for r in recs], [r["variants"][b][m] for r in recs], rng) for m, g in GRAN.items()} for name, (a, b) in pairs.items()}
    stats["cold_composer novelty - human novelty"] = {"novelty (J vs versión anterior)": paired_stats([r["variants"]["cold_composer"]["novelty_j_key"] for r in recs], [r["novelty_human"]["j_key"] for r in recs], rng)}
    stats["rotation_composer novelty - human novelty"] = {"novelty (J vs versión anterior)": paired_stats([r["variants"]["rotation_composer"]["novelty_j_key"] for r in recs], [r["novelty_human"]["j_key"] for r in recs], rng)}
    stats["routed_delivered novelty - human novelty"] = {"novelty (J vs versión anterior)": paired_stats([r["variants"]["routed_delivered"]["novelty_j_key"] for r in recs], [r["novelty_human"]["j_key"] for r in recs], rng)}
    stats["routed_delivered - routed_validated (violaciones de plausibilidad)"] = {"violaciones": paired_stats([r["plausibility"]["routed_delivered"]["violations"] for r in recs], [r["plausibility"]["routed_validated"]["violations"] for r in recs], rng)}
    by_goal_change = {}
    for flag, lab in ((False, "mismo objetivo"), (True, "cambio de objetivo")):
        rows = [r for r in recs if r["goal_changed"] == flag]
        by_goal_change[lab] = {"n": len(rows), "copy_previous": mean([r["variants"]["copy_previous"]["j_key"] for r in rows]), "rotation_consensus_only": mean([r["variants"]["rotation_consensus_only"]["j_key"] for r in rows]),
                               "rotation_composer": mean([r["variants"]["rotation_composer"]["j_key"] for r in rows]), "cold_composer": mean([r["variants"]["cold_composer"]["j_key"] for r in rows]),
                               "routed": mean([r["variants"]["routed"]["j_key"] for r in rows]), "routed_delivered": mean([r["variants"]["routed_delivered"]["j_key"] for r in rows]),
                               "delivered_family": mean([r["variants"]["routed_delivered"]["j_family"] for r in rows]), "novelty_delivered": mean([r["variants"]["routed_delivered"]["novelty_j_key"] for r in rows]),
                               "rotation_family": mean([r["variants"]["rotation_composer"]["j_family"] for r in rows]),
                               "copy_family": mean([r["variants"]["copy_previous"]["j_family"] for r in rows]),
                               "novelty_human": mean([r["novelty_human"]["j_key"] for r in rows]), "novelty_rotation": mean([r["variants"]["rotation_composer"]["novelty_j_key"] for r in rows])}
    kinds = Counter()
    for x in recs:
        kinds.update(x["plausibility_changes"])
    plaus = {"delivered_variant": "routed_delivered", "changes_per_query": {k: r(v / len(recs), 3) for k, v in sorted(kinds.items())},
             "queries_with_any_change": sum(1 for x in recs if x["plausibility_changes"]),
             "violations_by_check": {v: dict(sum((Counter(x["plausibility"][v]["by_check"]) for x in recs), Counter())) for v in ("routed", "routed_validated", "routed_delivered")}}
    return {"meta": meta, "queries": len(recs), "table": table, "human": human, "statistics": stats, "by_goal_change": by_goal_change, "plausibility": plaus,
            "rotation_applied": {"renewal_applied_mean": mean([r["rotation"]["renewal_applied"] or 0 for r in recs]), "rotated_items_mean": mean([r["rotation"]["rotated_items"] for r in recs]),
                                 "renewal_applied_conservative": mean([r["rotation_consensus_only"]["renewal_applied"] or 0 for r in recs]),
                                 "own_versions_among_cases_mean": mean([r["own_versions_among_cases"] for r in recs]), "history_size_median": statistics.median(r["history_size"] for r in recs)}}


def build_results():
    recs, meta = load_records()
    grid = json.loads((DATASET_DIR / "composer_grid.json").read_text(encoding="utf-8"))
    g = grid["grid"]
    t_def = meta["params"]["inclusion_threshold"]; k_def = meta["params"]["k"]
    curves = {"k_curve": [{"k": v["k"], "j_key": v["jaccard_key_top"], "j_food": v["jaccard_food"], "size": v["size_ratio"]} for v in g.values() if abs(v["threshold"] - t_def) < 1e-9],
              "threshold_curve": [{"t": v["threshold"], "j_key": v["jaccard_key_top"], "precision": v["precision_key"], "recall": v["recall_key"], "size": v["size_ratio"], "items": v["items_median"]}
                                  for v in g.values() if v["k"] == k_def]}
    retrieval = json.loads((DATASET_DIR / "retrieval_strategies.json").read_text(encoding="utf-8"))
    alpha = {k: v for k, v in retrieval.get("alpha_curve_hybrid", {}).items()}
    alpha_curve = sorted(({"alpha": float(a), "j_key": v["jaccard_key_top1"], "j_food": v["jaccard_food_top1"], "size": v["size_ratio"]} for a, v in alpha.items()), key=lambda d: -d["alpha"])
    strategies = {s: {"j_key": v["jaccard_normalized_key"]["top1"], "j_food": v["jaccard_food_id"]["top1"], "size": v["top1_size_ratio_mean"], "p50_ms": v["latency_ms"]["p50"]}
                  for s, v in retrieval["results"].items()}
    return {"meta": meta, "success": success_tables(recs), "statistics": statistics_tables(recs), "stratification": stratification(recs), "ablation": ablation(recs),
            "ablation_extra": ablation_extra(recs),
            "per_slot": per_slot(recs), "failures": failures(recs), "availability": availability(recs, meta), "curves": curves,
            "retrieval": {"strategies": strategies, "alpha_curve_hybrid": alpha_curve, "chance_top1_same_goal": retrieval["protocol"].get("chance_top1_same_goal")},
            "recurrent": recurrent_tables()}


# --------------------------------------------------------------------------------------------------------------- markdown
def f4(x):
    return "—" if x is None else f"{x:.3f}"


def cost_phrase(st: dict, what: str) -> str:
    """Wording of a paired difference of the plausibility layer against the previous stage: a cost when the CI is below zero, neutral when it includes it."""
    lo, hi = st["ci95"]
    if hi < 0:
        return f"cuesta {st['mean_diff']:+.3f} de {what} (IC 95 % [{lo:+.3f}, {hi:+.3f}], Wilcoxon p = {st['wilcoxon_p']:.2g})"
    if lo > 0:
        return f"gana {st['mean_diff']:+.3f} de {what} (IC 95 % [{lo:+.3f}, {hi:+.3f}], Wilcoxon p = {st['wilcoxon_p']:.2g})"
    return f"no cambia el {what} de forma medible ({st['mean_diff']:+.3f}, IC 95 % [{lo:+.3f}, {hi:+.3f}] incluye el 0, Wilcoxon p = {st['wilcoxon_p']:.2g})"


# Written by the generator, not by hand, because this file is regenerated on every --rerun and a hand-added note
# would be silently wiped the first time the harness ran.
SLOT_COMPARABILITY_WARNING = [
    "> ### Aviso de comparabilidad entre dataset-v2 y dataset-v3\n",
    ">",
    "> El `dataset-v3` nombra cinco franjas que el v2 no tenía (MEDIA TARDE, RECIEN LEVANTADO, SUPLEMENTOS, AGUA,",
    "> ANTES DE DORMIR) y cuyo contenido el troceador antiguo dejaba caer en la franja que estuviera abierta. Al",
    "> darles franja propia, **ítems que en el v2 vivían dentro de DESAYUNO o MERIENDA pasan a tener la suya**.",
    ">",
    "> Consecuencia directa, y hay que leerla antes que cualquier tabla:",
    ">",
    "> * **Las métricas por FRANJA no son comparables entre v2 y v3.** Cambian los ítems por franja, el número de",
    ">   franjas por dieta, el Jaccard por franja (§6) y cualquier recuento que use la franja como unidad. Una",
    ">   diferencia ahí es un cambio de taxonomía, no una mejora del motor.",
    "> * **Las métricas por DIETA y por ÍTEM sí lo son.** El titular (§0), la ablación (§4) y el escenario recurrente",
    ">   (§9) se miden sobre la dieta y sobre el conjunto de ítems, que no dependen del reparto en franjas.",
    ">",
    "> Contexto: el MERIENDA del v2 (896 dietas) es el MERIENDA del v3 más MEDIA TARDE, y su RECENA (225) es RECENA",
    "> más ANTES DE DORMIR. Detalle en la memoria (comparación entre versiones del dataset) §3.\n",
]


def render_markdown(res: dict) -> str:  # noqa: C901
    m = res["meta"]; L = []
    L.append(f"# Resultados de la evaluación (E5) — generado por `eval.report` el {m['measured_at']}\n")
    L.append(f"Protocolo: {m['queries']} consultas leave-one-out, recuperación `{m['retrieval_strategy']}`, compositor k = {m['params']['k']}, umbral = {m['params']['inclusion_threshold']}, "
             f"semilla {m['seed']}. Toda cifra de este fichero se regenera desde `_dataset/composer_per_query.jsonl` (`results.json` es la fuente; este Markdown es su render).\n")
    sA = res["success"]["A_excl_nearest_neighbour"]["normalized_key"]; cc = res["statistics"]["pairs"]["composer - copy_top1"]["normalized_key"]
    L.extend(SLOT_COMPARABILITY_WARNING)
    L.append("## 0. Titular\n")
    L.append(f"**Escenario cliente nuevo (arranque en frío, {m['queries']} consultas): el compositor por consenso bate a copiar el caso más parecido en "
             f"+{cc['mean_diff']:.3f} de Jaccard `normalized_key` (IC 95 % [{cc['ci95'][0]:+.3f}, {cc['ci95'][1]:+.3f}], Wilcoxon p = {cc['wilcoxon_p']:.1e}).** "
             f"Los «techos» de autoconsistencia de las tablas siguientes (dieta oculta frente a las demás dietas del mismo cliente) son **laxos**: mezclan versiones lejanas "
             f"(v1 frente a v6) de una progresión gradual. El techo estricto para la tarea «predecir la siguiente dieta» es la versión inmediatamente anterior del cliente "
             f"(Jaccard 0,525 entre versiones consecutivas en el análisis de rotación) y se trata en la sección 9 (escenario recurrente); el compositor frío queda por debajo de él.\n")
    ab = {row["variant"]: row for row in res["ablation"]}; de = ab[res["ablation_extra"]["delivered_variant"]]; va = ab["validated_strict"]
    dc = res["statistics"]["pairs"]["entregada - copy_top1"]["normalized_key"]; dv = res["statistics"]["pairs"]["entregada (validador + plausibilidad) - validated_strict"]["normalized_key"]
    pv = res["statistics"]["pairs"]["entregada - validated_strict (violaciones de plausibilidad por consulta)"]["violaciones"]
    L.append(f"**Configuración entregada** (la que sirve la API: estrategia → capa de plausibilidad → validador; última fila de la ablación, sección 4): J `normalized_key` "
             f"**{de['normalized_key']:.3f}** frente a copiar top-1 {ab['copy_top1']['normalized_key']:.3f} (+{dc['mean_diff']:.3f}, IC 95 % [{dc['ci95'][0]:+.3f}, {dc['ci95'][1]:+.3f}], "
             f"Wilcoxon p = {dc['wilcoxon_p']:.1e}). Respecto al validador solo, la capa de plausibilidad {cost_phrase(dv, 'Jaccard `normalized_key`')} "
             f"y deja las violaciones de plausibilidad por propuesta en {de['plausibility_violations']:.2f} (desde {va['plausibility_violations']:.2f}; "
             f"{pv['mean_diff']:+.2f}, IC 95 % [{pv['ci95'][0]:+.2f}, {pv['ci95'][1]:+.2f}]); propuestas con alguna violación: {100*va['share_with_violation']:.0f} % → {100*de['share_with_violation']:.0f} %.\n")
    L.append("## 1. Criterio de éxito: suelo · copiar top-1 · compositor · **sistema entregado** · techo laxo\n")
    L.append("La columna **entregada** es lo que sirve la API (estrategia → capa de plausibilidad → validador), la misma que cierra la ablación de la sección 4. "
             "Las dos tablas siguientes la dan en los dos protocolos de techo y en las tres granularidades; debajo de cada una van las diferencias EMPAREJADAS "
             "entregada − copiar y entregada − techo con su intervalo y su Wilcoxon.\n")
    pair_keys = {"A_excl_nearest_neighbour": ("entregada - copy_top1", "entregada - ceiling_excl_nn (subset)"),
                 "B_incl_nearest_neighbour": ("entregada - copy_top1", "entregada - ceiling_incl_nn")}
    for label, tab in res["success"].items():
        title = "A · techo laxo sin el vecino más cercano (clientes con ≥ 3 dietas)" if label.startswith("A") else "B · techo laxo incluyendo el vecino más cercano (todas las consultas)"
        L.append(f"**{title}** — n = {tab['queries']}\n")
        L.append("| Granularidad | Suelo mismo objetivo | Copiar top-1 | Compositor | **Entregada** | Techo | entregada − copia | entregada − techo | normalizada entregada | normalizada compositor |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for g in GRAN.values():
            s = tab[g]
            L.append(f"| {g} | {f4(s['floor_same_goal'])} | {f4(s['copy_top1'])} | {f4(s['composer'])} | **{f4(s['delivered'])}** | {f4(s['ceiling'])} | {s['delivered_vs_copy']:+.3f} | "
                     f"{s['delivered_vs_ceiling']:+.3f} | {f4(s['delivered_normalised'])} | {f4(s['composer_normalised'])} |")
        L.append("")
        kc, kce = pair_keys[label]
        L.append("Diferencias emparejadas de la configuración entregada (mismas consultas; bootstrap 10.000 con semilla fija, Wilcoxon bilateral):\n")
        L.append("| Diferencia | Granularidad | n | media | IC 95 % | excluye 0 | p (Wilcoxon) | % consultas a favor |")
        L.append("|---|---|---|---|---|---|---|---|")
        for name, pk in (("entregada − copiar top-1", kc), ("entregada − techo laxo", kce)):
            for g in GRAN.values():
                st = res["statistics"]["pairs"][pk][g]
                L.append(f"| {name} | {g} | {st['n']} | {st['mean_diff']:+.4f} | [{st['ci95'][0]:+.4f}, {st['ci95'][1]:+.4f}] | {'sí' if st['excludes_zero'] else '**no**'} | "
                         f"{st['wilcoxon_p']:.2g} | {100*st['share_positive']:.0f} % |")
        L.append("")
    L.append("## 2. Intervalos de confianza y contrastes (diferencias emparejadas)\n")
    L.append(f"{res['statistics']['method']}.\n")
    L.append("| Comparación | Granularidad | n | diferencia media | IC 95 % | excluye 0 | p (Wilcoxon) | % consultas a favor |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name, per in res["statistics"]["pairs"].items():
        for g, s in per.items():
            L.append(f"| {name} | {g} | {s['n']} | {s['mean_diff']:+.4f} | [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}] | {'sí' if s['excludes_zero'] else '**no**'} | {s['wilcoxon_p']:.2g} | {100*s['share_positive']:.0f} % |")
    L.append("")
    L.append("## 3. Estratificación (celdas con n < 30 marcadas como no concluyentes)\n")
    for key, title in (("by_goal", "Por objetivo"), ("by_sex", "Por sexo"), ("by_age_bucket", "Por tramo de edad")):
        L.append(f"**{title}** (J `normalized_key`; techo con vecino)\n")
        L.append("| Grupo | n | Suelo mismo obj. | Copiar top-1 | Compositor | **Entregada** | Techo | entregada − copia | tamaño | concluyente |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for k, c in res["stratification"][key].items():
            s = c["normalized_key"]
            L.append(f"| {k} | {c['n']} | {f4(s['floor_same_goal'])} | {f4(s['copy_top1'])} | {f4(s['composer'])} | **{f4(s['delivered'])}** | {f4(s['ceiling_incl_nn'])} | "
                     f"{c['delivered_vs_copy_key']:+.3f} | {c['size_delivered']:.2f} | {'sí' if c['conclusive'] else '**no (n < 30)**'} |")
        L.append("")
    ga = res["stratification"]["generic_assumption"]
    L.append("**Con y sin ítems `generic_assumption`** (todas las consultas)\n")
    L.append("| | copiar top-1 key / food | compositor key / food | techo (con vecino) key / food |")
    L.append("|---|---|---|---|")
    for lab, d in (("con", ga["with"]), ("sin", ga["without"])):
        L.append(f"| {lab} | {f4(d['normalized_key']['copy_top1'])} / {f4(d['food_id']['copy_top1'])} | **{f4(d['normalized_key']['composer'])} / {f4(d['food_id']['composer'])}** | {f4(d['normalized_key']['ceiling_incl_nn'])} / {f4(d['food_id']['ceiling_incl_nn'])} |")
    L.append("")
    L.append(f"## 4. Ablación acumulativa ({m['queries']} consultas): suelo → recuperación → compositor → validador → plausibilidad → techo\n")
    L.append("Cada fila añade una etapa a la anterior en el orden en que el caso de uso las ejecuta. **La última fila antes del techo es la configuración entregada** "
             "(`ProposeDietUseCase`: estrategia → `complete_structure` + `normalize_quantities` → `DietValidator`); las filas anteriores son etapas intermedias que la API no sirve. "
             "«Viol. plaus.» = violaciones de la envolvente de plausibilidad por propuesta (`check_plausibility`: cantidad fuera de [p05, p95], unidad no observada, alimentos por franja, "
             "estructura de franja, alternativas que mezclan grupos, reglas mayoritarias del objetivo); «% con viol.» = propuestas con al menos una.\n")
    L.append("| Paso | J key | Δ | J food | Δ | J familia | Δ | cumpl. todas | cumpl. condicionales | forzados | tamaño | viol. plaus. | % con viol. |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    def _ab_row(row, bold=False):  # noqa: E306
        d = row.get("delta") or {}
        dd = lambda g: (f"{d[g]:+.3f}" if d.get(g) is not None else "")  # noqa: E731
        extra = f" (sin vecino: {f4(row.get('normalized_key_excl_nn'))} / {f4(row.get('food_id_excl_nn'))} / {f4(row.get('familia_excl_nn'))})" if row["variant"] == "ceiling" else ""
        pvv = "—" if row.get("plausibility_violations") is None else f"{row['plausibility_violations']:.2f}"
        sh = "—" if row.get("share_with_violation") is None else f"{100*row['share_with_violation']:.0f} %"
        key = f"**{f4(row['normalized_key'])}**" if bold else f4(row['normalized_key'])
        return (f"| {row['step']}{extra} | {key} | {dd('normalized_key')} | {f4(row['food_id'])} | {dd('food_id')} | {f4(row['familia'])} | {dd('familia')} | {f4(row['compliance_all'])} | "
                f"{f4(row['compliance_cond'])} | {'' if row.get('forced') is None else f'{row['forced']:.2f}'} | {'' if row.get('size') is None else f'{row['size']:.2f}'} | {pvv} | {sh} |")
    for row in res["ablation"]:
        L.append(_ab_row(row, bold=row["variant"] == res["ablation_extra"]["delivered_variant"]))
    L.append("")
    L.append("Ramas medidas pero no entregadas (parten del compositor, no se acumulan):\n")
    L.append("| Rama | J key | J food | J familia | cumpl. todas | cumpl. condicionales | forzados | tamaño | viol. plaus. | % con viol. |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in res["ablation_extra"]["branches"]:
        pvv = "—" if row.get("plausibility_violations") is None else f"{row['plausibility_violations']:.2f}"
        sh = "—" if row.get("share_with_violation") is None else f"{100*row['share_with_violation']:.0f} %"
        L.append(f"| {row['step']} | {f4(row['normalized_key'])} | {f4(row['food_id'])} | {f4(row['familia'])} | {f4(row['compliance_all'])} | {f4(row['compliance_cond'])} | "
                 f"{'' if row.get('forced') is None else f'{row['forced']:.2f}'} | {row['size']:.2f} | {pvv} | {sh} |")
    L.append("")
    ex = res["ablation_extra"]; hv = ex["hidden_diet_vs_envelope"]
    ch = " · ".join(f"`{k}` {v:.2f}" for k, v in ex["changes_per_query"].items())
    vb = lambda v: ", ".join(f"{k} {n}" for k, n in sorted(ex["violations_by_check"][v].items(), key=lambda kv: -kv[1])) or "ninguna"  # noqa: E731
    L.append(f"**Qué hace la capa de plausibilidad y qué deja.** Cambios aplicados por propuesta: {ch} ({ex['queries_with_any_change']} de {m['queries']} propuestas reciben alguno). "
             f"Violaciones por tipo en las {m['queries']} propuestas — validador solo: {vb('validated_strict')}; **entregada: {vb(ex['delivered_variant'])}**. "
             f"Referencia: la dieta oculta del propio profesional tiene {hv['out_of_band']} de {hv['quantities_checked']} cantidades fuera de su envolvente [p05, p95] "
             f"({100*hv['share_out_of_band']:.1f} %, {hv['per_query']:.2f} por dieta), porque la banda se define para dejar fuera ~10 % por construcción: la capa no pretende llegar a cero "
             f"violaciones, sino no proponer nada que el profesional no haya prescrito.\n")
    L.append(f"**Compromiso declarado.** Respecto al validador solo, la capa de plausibilidad {cost_phrase(dv, 'J `normalized_key`')}; {100*dv['share_positive']:.0f} % de las consultas mejoran "
             f"y la diferencia en `food_id` es {ab[ex['delivered_variant']]['delta']['food_id']:+.3f}. A cambio reduce las violaciones de plausibilidad "
             f"de {va['plausibility_violations']:.2f} a {de['plausibility_violations']:.2f} por propuesta y la proporción de propuestas con alguna de {100*va['share_with_violation']:.0f} % a "
             f"{100*de['share_with_violation']:.0f} %. Se entrega con la capa activada aunque el Jaccard no la premie: el Jaccard mide el solapamiento con una dieta que el profesional escribió, no si la propuesta es prescribible; "
             f"una propuesta con cantidades fuera de lo que él prescribe o una cena sin verdura no es una propuesta peor en la métrica, pero sí lo es para el usuario. "
             f"La configuración entregada sigue batiendo a copiar top-1 en +{dc['mean_diff']:.3f} [{dc['ci95'][0]:+.3f}, {dc['ci95'][1]:+.3f}].\n")
    L.append("## 5. Desglose por franja (J `normalized_key` de la franja; n = dietas ocultas con la franja)\n")
    L.append("| Franja | n | ítems ocultos | Copiar top-1 | Compositor | Validado | Entregada | Techo (con vecino) | compositor − copia | compositor propone la franja |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for slot, s in res["per_slot"].items():
        L.append(f"| {slot} | {s['n']} | {s['hidden_items_mean']:.1f} | {f4(s['copy_top1'])} | **{f4(s['composer'])}** | {f4(s['validated'])} | {f4(s.get('delivered'))} | {f4(s['ceiling_incl_nn'])} | {s['composer_vs_copy']:+.3f} | {100*s['composer_present_share']:.0f} % |")
    L.append("")
    fl = res["failures"]; sm = fl["summary"]
    L.append("## 6. Análisis de fallos: las 20 consultas con peor Jaccard de la CONFIGURACIÓN ENTREGADA\n")
    L.append("| Dieta oculta | objetivo | sexo | edad | ítems | franjas | mismo obj. disponibles | mismo obj. en k | gap | degradación | **J entregada** | J compositor | J copiar | J techo | tamaño |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for w in fl["worst"]:
        L.append(f"| {w['diet_id']} | {w['goal']} | {w['sex']} | {w['age_bucket']} | {w['hidden_items']} | {w['hidden_slots']} | {w['same_goal_available']} | {w['same_goal_in_k']} | "
                 f"{','.join(w['gap']) or '—'} | {w['degradation']} | **{w['j_key_delivered']:.3f}** | {w['j_key_composer']:.3f} | {w['j_key_copy']:.3f} | {w['j_key_ceiling_incl_nn']:.3f} | {w['size_delivered']:.2f} |")
    L.append("")
    L.append(f"Qué tienen en común (20 peores frente al total): objetivo minoritario {100*sm['share_minority_goal']:.0f} % (total {100*sm['share_minority_goal_overall']:.0f} %); "
             f"marcadas como gap {100*sm['share_gap']:.0f} % (total {100*sm['share_gap_overall']:.0f} %); mujeres {100*sm['share_female']:.0f} % (total {100*sm['share_female_overall']:.0f} %); "
             f"ítems de la dieta oculta {sm['hidden_items_mean']:.1f} de media (total {sm['hidden_items_mean_overall']:.1f}, mediana {sm['hidden_items_median_overall']:.0f}); "
             f"dietas con < 15 ítems {100*sm['share_hidden_items_lt_15']:.0f} % (total {100*sm['share_hidden_items_lt_15_overall']:.0f} %); franjas {sm['slots_mean']:.1f} (total {sm['slots_mean_overall']:.1f}); "
             f"techo con vecino de esas consultas {sm['ceiling_incl_nn_mean']:.3f} (total {sm['ceiling_incl_nn_mean_overall']:.3f}); copiar bate a la entregada en {sm['copy_beats_delivered']} de 20 (al compositor crudo, en {sm['copy_beats_composer']}). Objetivos: {sm['goals']}.\n")
    av = res["availability"]
    L.append("## 7. Disponibilidad, degradación y gaps\n")
    L.append(f"k = {av['k']}; k efectivo: {av['k_effective_distribution']}; modos de degradación: {av['degradation_modes']}; consultas con < k dietas del mismo objetivo: {av['queries_with_fewer_than_k_same_goal_available']}; "
             f"condiciones de gap: {av['gap_conditions']}; consultas con algún gap: {av['queries_with_any_gap']} ({100*av['queries_with_any_gap']/m['queries']:.1f} %).\n")
    mi, ma = av["minority_subset"], av["majority_subset"]
    L.append(f"Subconjunto minoritario (n = {mi['n']}): copiar {f4(mi['j_key_copy'])} · compositor sin degradación {f4(mi['j_key_composer_no_degradation'])} · compositor con degradación {f4(mi['j_key_composer_with_degradation'])} · "
             f"**entregada {f4(mi['j_key_delivered'])}**. "
             f"Subconjunto mayoritario (n = {ma['n']}): copiar {f4(ma['j_key_copy'])} · compositor {f4(ma['j_key_composer'])} · **entregada {f4(ma['j_key_delivered'])}**.\n")
    L.append("## 8. Curvas\n")
    L.append("Curva de k (umbral por defecto): " + " · ".join(f"k={c['k']}: {c['j_key']:.3f} (tamaño {c['size']:.2f})" for c in res["curves"]["k_curve"]) + "\n")
    L.append("Curva del umbral (k por defecto): " + " · ".join(f"t={c['t']:.2f}: {c['j_key']:.3f} (P {c['precision']:.2f} / R {c['recall']:.2f}, tamaño {c['size']:.2f})" for c in res["curves"]["threshold_curve"]) + "\n")
    L.append("Curva α de la híbrida (E3): " + " · ".join(f"α={c['alpha']:.2f}: {c['j_key']:.3f}" for c in res["retrieval"]["alpha_curve_hybrid"]) + "\n")
    L.append("Figuras: `figures/fig01_curva_k.png`, `fig02_curva_umbral.png`, `fig03_criterio_exito.png`, `fig04_curva_alpha_hibrida.png`, `fig05_estratificacion_objetivo.png`, `fig06_franjas.png`, `fig07_estrategias_recuperacion.png`, `fig08_ablacion.png`.\n")
    rc = res.get("recurrent")
    if rc:
        L.append("## 9. Escenario cliente recurrente (versiones anteriores disponibles) — cifras NO comparables con las de las secciones 1–8\n")
        L.append(f"{rc['queries']} consultas: dietas ocultas con al menos una versión estrictamente anterior del mismo cliente (aserción en el arnés: ninguna versión posterior ni re-emisión "
                 f"del mismo número entra como historial ni como candidato). Las versiones anteriores del cliente **sí** son candidatos de recuperación (en producción el profesional las tiene delante); "
                 f"de media {rc['rotation_applied']['own_versions_among_cases_mean']:.1f} de los 20 casos recuperados son suyas. Historial mediano: {rc['rotation_applied']['history_size_median']:.0f} versiones. "
                 f"Objetivo de renovación del profesional: {100*rc['human']['renewal_same_goal']:.0f} % de los alimentos con el mismo objetivo, {100*rc['human']['renewal_goal_change']:.0f} % al cambiar de objetivo; "
                 f"expresado como Jaccard frente a la versión anterior: **{rc['human']['novelty_j_key']:.3f}** (`normalized_key`) / {rc['human']['novelty_j_food']:.3f} (`food_id`) en estas {rc['queries']} consultas.\n")
        L.append("| Variante | J key vs oculta | J food | J familia | J franja | tamaño | **novedad: J vs versión anterior** (humano " + f"{rc['human']['novelty_j_key']:.3f}) | cumpl. condicional | viol. plaus. |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for v, t in rc["table"].items():
            pvv = "—" if t.get("plausibility_violations") is None else f"{t['plausibility_violations']:.2f}"
            L.append(f"| {t['label']} | **{f4(t['j_key'])}** | {f4(t['j_food'])} | {f4(t['j_family'])} | {f4(t['per_slot'])} | {t['size']:.2f} | {f4(t['novelty_j_key'])} | {f4(t['compliance_cond'])} | {pvv} |")
        L.append("")
        td, tr, tv = rc["table"]["routed_delivered"], rc["table"]["routed"], rc["table"]["routed_validated"]
        sd = rc["statistics"]["routed_delivered - routed_validated"]["normalized_key"]; sp = rc["statistics"]["routed_delivered - routed_validated (violaciones de plausibilidad)"]["violaciones"]
        sn = rc["statistics"]["routed_delivered novelty - human novelty"]["novelty (J vs versión anterior)"]
        rp = rc["plausibility"]; chr_ = " · ".join(f"`{k}` {v:.2f}" for k, v in rp["changes_per_query"].items())
        L.append(f"**La última fila es la configuración entregada** para el cliente recurrente (enrutado → capa de plausibilidad → validador). Respecto al enrutado validado, la capa {cost_phrase(sd, 'J key')}, conserva la fidelidad por familia "
                 f"({td['j_family']:.3f} frente a {tv['j_family']:.3f}) y la novedad ({td['novelty_j_key']:.3f} frente a la humana {rc['human']['novelty_j_key']:.3f}; diferencia {sn['mean_diff']:+.3f} "
                 f"[{sn['ci95'][0]:+.3f}, {sn['ci95'][1]:+.3f}]), y baja las violaciones de plausibilidad de {tv['plausibility_violations']:.2f} a {td['plausibility_violations']:.2f} por propuesta "
                 f"({sp['mean_diff']:+.2f} [{sp['ci95'][0]:+.2f}, {sp['ci95'][1]:+.2f}]). Cambios aplicados por propuesta: {chr_} ({rp['queries_with_any_change']} de {rc['queries']}). "
                 f"Aquí la capa corrige sobre todo lo que la rotación hereda de la versión anterior (unidades y cantidades propias de otro alimento) y las cenas sin verdura.\n")
        L.append(f"Rotación aplicada: RotationComposer completo renueva de media el {100*rc['rotation_applied']['renewal_applied_mean']:.1f} % de los ítems ({rc['rotation_applied']['rotated_items_mean']:.1f} ítems); "
                 f"el conservador (solo reemplazos presentes en el consenso) el {100*rc['rotation_applied']['renewal_applied_conservative']:.1f} %.\n")
        L.append("| Comparación (emparejada) | Granularidad | n | diferencia | IC 95 % | excluye 0 | p (Wilcoxon) | % a favor |")
        L.append("|---|---|---|---|---|---|---|---|")
        for name, per in rc["statistics"].items():
            for g, st in per.items():
                L.append(f"| {name} | {g} | {st['n']} | {st['mean_diff']:+.4f} | [{st['ci95'][0]:+.4f}, {st['ci95'][1]:+.4f}] | {'sí' if st['excludes_zero'] else '**no**'} | {st['wilcoxon_p']:.2g} | {100*st['share_positive']:.0f} % |")
        L.append("")
        L.append("| Transición | n | copiar anterior | rotación conservadora | rotación completa | compositor frío | enrutado | **entregada** | familia: copiar / rotación completa / entregada | novedad humana | novedad rotación completa | novedad entregada |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for lab, b in rc["by_goal_change"].items():
            L.append(f"| {lab} | {b['n']} | {f4(b['copy_previous'])} | {f4(b['rotation_consensus_only'])} | {f4(b['rotation_composer'])} | {f4(b['cold_composer'])} | {f4(b['routed'])} | **{f4(b['routed_delivered'])}** | "
                     f"{f4(b['copy_family'])} / {f4(b['rotation_family'])} / {f4(b['delivered_family'])} | {f4(b['novelty_human'])} | {f4(b['novelty_rotation'])} | {f4(b['novelty_delivered'])} |")
        L.append("")
        t = rc["table"]
        L.append("**Limitación de la métrica en este escenario.** Copiar la versión anterior maximiza la fidelidad por especie (J key "
                 f"{t['copy_previous']['j_key']:.3f}) con novedad 1,000: el óptimo de la métrica es exactamente el fracaso del producto (la misma dieta que el mes pasado). "
                 "La causa está medida: el profesional rota dentro de la familia, pero hacia qué especie no es predecible; si él pasa de una especie a otra y el sistema a una "
                 "tercera de la misma familia, el Jaccard por especie lo cuenta como fallo total. Por eso cualquier sistema que rote pierde fidelidad por especie por construcción. "
                 f"A nivel de **familia** la rotación completa es idéntica a copiar ({t['rotation_composer']['j_family']:.3f} = {t['copy_previous']['j_family']:.3f}; diferencia 0,000 en todas las consultas, por construcción de la política) "
                 f"y alcanza el nivel de renovación humano (novedad {t['rotation_composer']['novelty_j_key']:.3f} frente a {rc['human']['novelty_j_key']:.3f}): conserva la fidelidad estructural "
                 "—familias y estructura de comidas— y concentra el coste en la elección de especie, que el profesional también hace de forma arbitraria. "
                 "La comparación por especie entre variantes que rotan y variantes que copian no representa el requisito en este escenario; la comparación válida es a nivel de familia más la novedad.\n")
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------------------------- figures
def make_figures(res: dict, outdir: Path):
    import matplotlib
    import numpy as np
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "axes.titlesize": 13, "axes.labelsize": 12, "figure.dpi": 150})
    outdir.mkdir(parents=True, exist_ok=True)
    k_def, t_def = res["meta"]["params"]["k"], res["meta"]["params"]["inclusion_threshold"]

    kc = res["curves"]["k_curve"]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot([c["k"] for c in kc], [c["j_key"] for c in kc], "o-", label="Jaccard normalized_key")
    ax.plot([c["k"] for c in kc], [c["j_food"] for c in kc], "s--", label="Jaccard food_id")
    ax.set_xlabel("k (casos recuperados)"); ax.set_ylabel("Jaccard top-1 frente a la dieta oculta"); ax.set_title(f"Curva de k (umbral = {t_def}): rendimientos decrecientes")
    ax.set_xticks([c["k"] for c in kc]); ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(outdir / "fig01_curva_k.png"); plt.close(fig)

    tc = res["curves"]["threshold_curve"]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot([c["t"] for c in tc], [c["j_key"] for c in tc], "o-", label="Jaccard normalized_key")
    ax.plot([c["t"] for c in tc], [c["precision"] for c in tc], "^:", label="precisión")
    ax.plot([c["t"] for c in tc], [c["recall"] for c in tc], "v:", label="exhaustividad")
    ax2 = ax.twinx(); ax2.plot([c["t"] for c in tc], [c["size"] for c in tc], "d-", color="gray", label="tamaño / dieta oculta"); ax2.set_ylabel("tamaño relativo"); ax2.axhline(1.0, color="gray", lw=.8, ls="--")
    ax.set_xlabel("umbral de inclusión t"); ax.set_ylabel("valor"); ax.set_title(f"Curva del umbral (k = {k_def}): compromiso precisión / exhaustividad"); ax.grid(alpha=.3)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax.legend(h1 + h2, l1 + l2, loc="center right")
    fig.tight_layout(); fig.savefig(outdir / "fig02_curva_umbral.png"); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=False)
    for ax, (label, tab) in zip(axes, res["success"].items()):
        names = ["Suelo mismo obj.", "Copiar top-1", "Compositor", "Entregada", "Techo"]
        x = np.arange(3); w = 0.17
        for i, (nm, key) in enumerate(zip(names, ["floor_same_goal", "copy_top1", "composer", "delivered", "ceiling"])):
            vals = [tab[g][key] for g in GRAN.values()]
            ax.bar(x + (i - 2) * w, vals, w, label=nm)
            for xi, v in zip(x + (i - 2) * w, vals):
                ax.text(xi, v + .01, f"{v:.3f}", ha="center", va="bottom", fontsize=7, rotation=90)
        ax.set_xticks(x); ax.set_xticklabels(list(GRAN.values())); ax.set_ylim(0, 0.85)
        ax.set_title(("A · techo sin vecino más cercano" if label.startswith("A") else "B · techo con vecino más cercano") + f" (n = {tab['queries']})")
        ax.set_ylabel("Jaccard top-1"); ax.grid(axis="y", alpha=.3)
    axes[0].legend(loc="upper left", fontsize=9)
    fig.suptitle("Criterio de éxito: suelo · copiar · compositor · ENTREGADA · techo"); fig.tight_layout(); fig.savefig(outdir / "fig03_criterio_exito.png"); plt.close(fig)

    ac = res["retrieval"]["alpha_curve_hybrid"]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot([c["alpha"] for c in ac], [c["j_key"] for c in ac], "o-", label="Jaccard normalized_key (top-1)")
    ax.plot([c["alpha"] for c in ac], [c["j_food"] for c in ac], "s--", label="Jaccard food_id (top-1)")
    ax.axhline(res["retrieval"]["strategies"]["attributes"]["j_key"], color="gray", ls=":", label="atributos puros (key)")
    ax.set_xlabel("α (peso del coseno normalizado en la híbrida)"); ax.set_ylabel("Jaccard top-1"); ax.invert_xaxis()
    ax.set_title("Recuperación híbrida: la señal densa resta en todo el rango de α"); ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(outdir / "fig04_curva_alpha_hibrida.png"); plt.close(fig)

    bg = res["stratification"]["by_goal"]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    goals = list(bg); x = np.arange(len(goals)); w = 0.17
    for i, (nm, key) in enumerate(zip(["Suelo mismo obj.", "Copiar top-1", "Compositor", "Entregada", "Techo (con vecino)"],
                                      ["floor_same_goal", "copy_top1", "composer", "delivered", "ceiling_incl_nn"])):
        ax.bar(x + (i - 2) * w, [bg[g]["normalized_key"][key] for g in goals], w, label=nm)
    ax.set_xticks(x); ax.set_xticklabels([f"{g}\n(n = {bg[g]['n']}{'' if bg[g]['conclusive'] else ', no concl.'})" for g in goals], fontsize=8)
    ax.set_ylabel("Jaccard normalized_key (top-1)"); ax.set_title("Estratificación por objetivo"); ax.grid(axis="y", alpha=.3); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(outdir / "fig05_estratificacion_objetivo.png"); plt.close(fig)

    ps = {k: v for k, v in res["per_slot"].items() if v["n"] >= 10}                 # slots with n < 10 stay in the table, not in the figure
    short = {"MEDIA MAÑANA": "MEDIA\nMAÑANA", "ANTES DE ENTRENAR": "PRE-\nENTRENO", "MITAD DE ENTRENAMIENTO": "INTRA-\nENTRENO", "DESPUES DE ENTRENAR": "POST-\nENTRENO"}
    fig, ax = plt.subplots(figsize=(10, 4.6))
    slots = list(ps); x = np.arange(len(slots)); w = 0.27
    ax.bar(x - w, [ps[s]["copy_top1"] for s in slots], w, label="Copiar top-1")
    ax.bar(x, [ps[s]["composer"] for s in slots], w, label="Compositor")
    ax.bar(x + w, [ps[s]["ceiling_incl_nn"] for s in slots], w, label="Techo (con vecino)")
    ax.set_xticks(x); ax.set_xticklabels([f"{short.get(s, s)}\n(n = {ps[s]['n']})" for s in slots], fontsize=8)
    ax.set_ylabel("Jaccard normalized_key de la franja"); ax.set_title("Desglose por franja (franjas con n ≥ 10)"); ax.grid(axis="y", alpha=.3); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(outdir / "fig06_franjas.png"); plt.close(fig)

    ab = [row for row in res["ablation"]]
    short_steps = {"floor_same_goal": "suelo\nmismo obj.", "copy_top1": "+ recuperación\n(copiar top-1)", "composer_no_degradation": "+ compositor\n(sin degrad.)",
                   "composer_raw": "+ degradación", "validated_strict": "+ validador", res["ablation_extra"]["delivered_variant"]: "+ plausibilidad\n(ENTREGADA)", "ceiling": "techo\n(con vecino)"}
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(ab)); w = 0.38
    ax.bar(x - w / 2, [row["normalized_key"] for row in ab], w, label="Jaccard normalized_key", color=["#9aa0a6" if row["variant"] == "ceiling" else "#1f77b4" for row in ab])
    ax.bar(x + w / 2, [row["food_id"] for row in ab], w, label="Jaccard food_id", color=["#c9ccd1" if row["variant"] == "ceiling" else "#ff7f0e" for row in ab])
    for xi, row in zip(x, ab):
        ax.text(xi - w / 2, row["normalized_key"] + .005, f"{row['normalized_key']:.3f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels([short_steps.get(row["variant"], row["variant"]) for row in ab], fontsize=8); ax.set_ylabel("Jaccard frente a la dieta oculta"); ax.grid(axis="y", alpha=.3)
    ax2 = ax.twinx()
    viol = [row.get("plausibility_violations") for row in ab]
    ax2.plot([xi for xi, v in zip(x, viol) if v is not None], [v for v in viol if v is not None], "d-", color="#d62728", label="violaciones de plausibilidad / propuesta")
    ax2.set_ylabel("violaciones / propuesta"); ax2.set_ylim(bottom=0)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    ax.set_title(f"Ablación acumulativa ({res['meta']['queries']} consultas): la última barra antes del techo es la configuración entregada")
    fig.tight_layout(); fig.savefig(outdir / "fig08_ablacion.png"); plt.close(fig)

    st = res["retrieval"]["strategies"]
    names = [s for s in ["vector", "goal_filtered_vector", "attributes", "hybrid"] if s in st]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(names)); w = 0.35
    ax.bar(x - w / 2, [st[s]["j_key"] for s in names], w, label="Jaccard normalized_key")
    ax.bar(x + w / 2, [st[s]["j_food"] for s in names], w, label="Jaccard food_id")
    ax.set_xticks(x); ax.set_xticklabels(["vectorial", "prefiltro obj. + vectorial", "atributos", "híbrida α=0,5"]); ax.set_ylabel("Jaccard top-1")
    ax.set_title("Estrategias de recuperación (E3, 746 consultas)"); ax.grid(axis="y", alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(outdir / "fig07_estrategias_recuperacion.png"); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rerun", action="store_true", help="run loo_harness --final before building the report (needs DATABASE_URL)")
    ap.add_argument("--out", type=Path, default=DOCS_DIR)
    args = ap.parse_args()
    if args.rerun:
        subprocess.run([sys.executable, "-m", "finalprosports.infrastructure.adapter.inbound.eval.loo_harness", "--final"], check=True)
        subprocess.run([sys.executable, "-m", "finalprosports.infrastructure.adapter.inbound.eval.loo_harness", "--recurrent"], check=True)
    res = build_results()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    res = json.loads((args.out / "results.json").read_text(encoding="utf-8"))          # render from the serialised JSON: exactly what the consistency test re-renders
    (args.out / "RESULTS.md").write_text(render_markdown(res), encoding="utf-8", newline="\n")
    make_figures(res, args.out / "figures")
    s = res["success"]["A_excl_nearest_neighbour"]["normalized_key"]; st = res["statistics"]["pairs"]
    ab = {row["variant"]: row for row in res["ablation"]}
    print(json.dumps({"out": str(args.out), "queries": res["meta"]["queries"], "composer_key_A": s["composer"], "ceiling_A": s["ceiling"],
                      "delivered_key": ab[res["ablation_extra"]["delivered_variant"]]["normalized_key"], "delivered-validated_key": st["entregada (validador + plausibilidad) - validated_strict"]["normalized_key"],
                      "delivered-copy_key": st["entregada - copy_top1"]["normalized_key"],
                      "composer-copy_key": st["composer - copy_top1"]["normalized_key"], "composer-ceiling_excl_key": st["composer - ceiling_excl_nn (subset)"]["normalized_key"],
                      "composer-ceiling_incl_key": st["composer - ceiling_incl_nn"]["normalized_key"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
