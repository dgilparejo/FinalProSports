# -*- coding: utf-8 -*-
"""
E4/E5 · Leave-one-out harness of the composer (inbound evaluation adapter: measures the same engine the API serves).

For each of the 746 hold-out queries (same protocol as the retrieval benchmark): retrieve k cases with the default strategy
(mandatory exclusions of the client and its template groups), then

  --grid     compose with every (k, inclusion threshold) of the grid; raw composer, no degradation, no validator, so that
             the grid measures composition alone.                                   -> _dataset/composer_grid.json
  --final    with the configured (k, t): one record per query with every variant (floors, copy top-1, composer with and
             without degradation, validator modes, low-confidence rules, plausibility layer = delivered configuration),
             the two ceilings, rule compliance (all / goal-conditional), plausibility violations per variant, per-slot
             Jaccard, availability and gap flags.                                    -> _dataset/composer_per_query.jsonl
             The aggregate tables, statistics, stratification, ablation, failure analysis and figures are produced from
             that file by `eval.report` (E5), so that every figure of the report is reproducible from the same records.

Nothing printed but aggregates and pseudonymous ids. Seed fixed.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.application.strategy.case_based_composer import CaseBasedComposer
from finalprosports.application.strategy.rotation_composer import RotationComposer
from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.domain.composition.policy.body_measurement_policy import profile_as_of
from finalprosports.domain.composition.policy.lab_measurement_policy import as_of as lab_as_of
from finalprosports.domain.composition.policy.composition_policy import NON_COMPOSABLE_SLOTS, CompositionParams
from finalprosports.domain.composition.policy.gap_policy import assess_gap
from finalprosports.domain.composition.policy.plausibility_policy import check_plausibility
from finalprosports.domain.composition.policy.proposal_completion_policy import (complete_structure, harmonise_rations, name_variants,
                                                                                 normalize_quantities)
from finalprosports.domain.composition.policy.rotation_policy import RotationParams
from finalprosports.domain.composition.policy.rule_applicability import with_low_confidence_enabled
from finalprosports.domain.composition.policy.rule_engine import RuleEngine
from finalprosports.domain.model import Diet, Food, RestrictionMode
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import (
    eligible_queries, jaccard, precision_recall, scorable_keys)
from finalprosports.infrastructure.adapter.outbound.persistence.service.client.client_repository_output_adapter import ClientRepositoryOutputAdapter
from finalprosports.infrastructure.composition_root import CompositionRoot

from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()          # FPS_DATASET_DIR: the data tree lives outside the code repository
CONDITIONAL_RULES = {"sin_hidratos_cena", "hidratos_en_cena", "suplementacion_pre_post", "sal_himalaya"}     # Part A §7.4 cut
# The cut above predates the prescriptive / descriptive split (Fase 9 B) and mixes both natures: `hidratos_en_cena` is
# DESCRIPTIVE with prevalence 0,104. Reported separately so the aggregate can be read either way, without redefining the
# published metric unilaterally.
CONDITIONAL_DESCRIPTIVE = {"hidratos_en_cena"}
CONDITIONAL_PRESCRIPTIVE = CONDITIONAL_RULES - CONDITIONAL_DESCRIPTIVE
GRID_K = (3, 5, 8, 12, 16, 20)
GRID_T = (0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6)
METRICS = ("j_key", "j_food", "j_family", "j_key_no_generic", "j_food_no_generic", "per_slot")


# ------------------------------------------------------------------------------------------------------------- item sets
# What the system is allowed to PRODUCE is what it is scored on. The generic OTHER bucket is not composable
# (composition_policy.NON_COMPOSABLE_SLOTS), so counting its contents in the hidden diet would charge the system
# for items it is structurally forbidden to propose -- a penalty that no change to the engine could ever recover.
# The bucket is not deleted from the corpus, only from the metric, and the diets that live mostly inside it are
# declared out of the evaluation entirely (see `irrepresentable`), with their count published as a limit.
SCORED_SLOTS = lambda m: m.slot not in NON_COMPOSABLE_SLOTS                                             # noqa: E731


def key_set(d: Diet, generic: bool = True) -> frozenset[str]:
    return frozenset(i.normalized_key for m in d.meals if SCORED_SLOTS(m) for i in m.items
                     if i.normalized_key and (generic or not i.generic_assumption))


def food_set(d: Diet, generic: bool = True) -> frozenset[int]:
    return frozenset(i.food_id for m in d.meals if SCORED_SLOTS(m) for i in m.items
                     if i.food_id is not None and (generic or not i.generic_assumption))


def family_set(d: Diet, catalog: dict[int, Food]) -> frozenset[str]:
    return frozenset(catalog[i.food_id].family for m in d.meals if SCORED_SLOTS(m) for i in m.items
                     if i.food_id in catalog and catalog[i.food_id].family)


def slot_sets(d: Diet) -> dict[str, frozenset[str]]:
    return {m.slot.value: frozenset(i.normalized_key for i in m.items if i.normalized_key)
            for m in d.meals if SCORED_SLOTS(m)}


def per_slot_jaccard(q: dict[str, frozenset], o: dict[str, frozenset]) -> float:
    return statistics.fmean(jaccard(q[s], o.get(s, frozenset())) for s in q) if q else 0.0


def mean(xs):
    return round(statistics.fmean(xs), 4) if xs else None


def apply_plausibility(proposal, cases, env, catalog):
    """The S2 layer exactly as ProposeDietUseCase applies it: structure completed from the retrieved cases, then quantities and
    units normalised into the corpus envelope. Returns (proposal, changes)."""
    meals, changes = complete_structure(list(proposal.meals), cases, env, catalog,
                                        profile=proposal.profile, mode=RestrictionMode.STRICT)
    meals, q_changes = normalize_quantities(meals, env, catalog)        # units and bands first...
    meals, r_changes = harmonise_rations(meals, env, catalog)           # ... then the rations read together (§5)
    meals = name_variants(meals, env, cases)                                   # §3: presentation only, the engine still sees the canonical
    return proposal.__class__(**{**proposal.__dict__, "meals": tuple(meals)}), changes + q_changes + r_changes


def plausibility_summary(proposal, env, catalog, rules) -> dict:
    violations = check_plausibility(proposal, env, catalog, rules)
    return {"violations": len(violations), "by_check": dict(Counter(v.check for v in violations))}


def hidden_out_of_band(hidden: Diet, env) -> tuple[int, int]:
    """(quantities outside the p05-p95 band, quantities with a band) of a corpus diet: the professional against his own envelope."""
    out = checked = 0
    for m in hidden.meals:
        for it in m.items:
            if it.food_id is None or it.quantity.value is None:
                continue
            band = env.quantities.get((it.food_id, it.quantity.unit.value))
            if band is None:
                continue
            checked += 1
            out += 0 if band.contains(float(it.quantity.value)) else 1
    return out, checked


def metric_fns(hidden: Diet, catalog):
    hk, hf, hkg, hfg, hfam, hs = key_set(hidden), food_set(hidden), key_set(hidden, False), food_set(hidden, False), family_set(hidden, catalog), slot_sets(hidden)
    return {"j_key": lambda d: jaccard(hk, key_set(d)), "j_food": lambda d: jaccard(hf, food_set(d)),
            "j_key_no_generic": lambda d: jaccard(hkg, key_set(d, False)), "j_food_no_generic": lambda d: jaccard(hfg, food_set(d, False)),
            "j_family": lambda d: jaccard(hfam, family_set(d, catalog)), "per_slot": lambda d: per_slot_jaccard(hs, slot_sets(d))}


# ---------------------------------------------------------------------------------------------------------------- setup
# ------------------------------------------------------------------------------------- el perfil de consulta, con fecha
# Toda medición construye el perfil de la consulta igual: el del cliente, con el objetivo de la dieta oculta. Desde la
# 0015 lleva además la composición corporal, y ésa NO es un atributo del cliente sino del INSTANTE: la lectura válida es
# la más reciente anterior a la fecha de la dieta oculta. Se centraliza aquí para que ningún arnés pueda olvidarlo — un
# `dataclasses.replace(profiles[c], goal=g)` suelto dejaría el perfil sin báscula y mediría otra cosa, y un
# `profiles[c]` ya poblado por otra consulta arrastraría la lectura equivocada.
_SERIES: dict[str, dict] = {}
_DOC_DATES: dict[str, dict] = {}


_LABS: dict[str, dict] = {}
_SPANS: dict[str, dict] = {}


def _labs(root, pid):
    """Las mediciones analiticas por cliente y el recorrido de cada parametro, leidos una vez."""
    if pid not in _LABS:
        import collections
        import json as _json
        from finalprosports.domain.composition.policy.lab_measurement_policy import LabValue
        por_cliente = collections.defaultdict(list)
        valores = collections.defaultdict(list)
        path = DATASET_DIR / "lab_results.jsonl"
        if path.exists():
            for line in path.open(encoding="utf-8"):
                r = _json.loads(line)
                if not r.get("client_code"):
                    continue
                for v in r.get("values") or ():
                    name = v.get("indicator") or v.get("analyte")
                    if not name or v.get("value") is None:
                        continue
                    por_cliente[r["client_code"]].append(
                        LabValue(marker=name, value=float(v["value"]), source_type=r["source_type"],
                                 measured_at=r.get("report_date"), unreliable=bool(r.get("values_unreliable"))))
                    valores[name].append(float(v["value"]))
        spans = {}
        for name, xs in valores.items():
            xs.sort()
            spans[name] = (xs[int(len(xs) * 0.95)] - xs[int(len(xs) * 0.05)]) or 1.0
        _LABS[pid], _SPANS[pid] = dict(por_cliente), spans
    return _LABS[pid], _SPANS[pid]


def _series(root, pid):
    if pid not in _SERIES:
        from finalprosports.infrastructure.adapter.outbound.persistence.service.record.client_record_output_adapter import BodyMeasurementOutputAdapter
        _SERIES[pid] = BodyMeasurementOutputAdapter(root.case_repository._sf).all_by_client(pid)      # noqa: SLF001
        _DOC_DATES[pid] = root.case_repository.doc_dates(pid)
    return _SERIES[pid], _DOC_DATES[pid]


def as_of_profile(root, pid, profile, goal, hidden_diet_id: str):
    """El perfil de consulta: objetivo de la dieta oculta + la báscula anterior a SU fecha."""
    series, dates = _series(root, pid)
    labs, spans = _labs(root, pid)
    cut = dates.get(hidden_diet_id)
    con_bascula = profile_as_of(dataclasses.replace(profile, goal=goal), series.get(profile.client_code, ()), cut)
    vigentes = lab_as_of(labs.get(profile.client_code, ()), cut)
    return dataclasses.replace(con_bascula,
                               lab_values={k: v.value for k, v in vigentes.items()} or None,
                               lab_spans=spans if vigentes else None)


def composer_like(root, params=None):
    """Un compositor IDENTICO al que sirve la API, con parametros opcionalmente distintos.

    Existe porque trece modulos de evaluacion lo construian a mano repitiendo tres argumentos, y el dia que el
    compositor gano un cuarto -- la tabla de colocacion de suplementos -- los trece se quedaron sin el sin que
    ninguno fallara: el resultado no era un error, era una dieta distinta de la que se entrega. Un arnes que compone
    con menos piezas que el motor no mide el motor.
    """
    return CaseBasedComposer(root.catalog, params or root.composer.params,
                             notes=root.composer._notes,                                   # noqa: SLF001
                             interchangeable=root.composer._interchangeable,               # noqa: SLF001
                             supplement_slots=root.composer._supplement_slots)             # noqa: SLF001


def setup():
    root = CompositionRoot.from_env()
    pid = root.configured_professional_id          # offline harness: no request, no token
    sf = root.case_repository._sf  # noqa: SLF001
    diets = root.case_repository.all_diets(pid)
    profiles = {p.client_code: p for p in ClientRepositoryOutputAdapter(sf).list_case_profiles(pid)}
    queries = eligible_queries(diets, profiles)
    rules = root.rules.all(pid)
    return root, pid, diets, profiles, queries, rules


def retrieve_all(root, pid, queries, profiles, k_max: int):
    svc = root.retrieve_similar_cases_service
    out = {}
    t0 = time.perf_counter()
    for hidden in queries:
        profile = as_of_profile(root, pid, profiles[hidden.client_code], hidden.goal, hidden.id)
        out[hidden.id] = (profile, svc.retrieve(pid, profile, k_max))
    return out, (time.perf_counter() - t0) / len(queries) * 1000


# ----------------------------------------------------------------------------------------------------------------- grid
def run_grid(args):
    root, pid, diets, profiles, queries, rules = setup()
    catalog = root.catalog
    retrieved, ms_retrieval = retrieve_all(root, pid, queries, profiles, max(GRID_K))
    composer = composer_like(root)
    grid = {}
    for k in GRID_K:
        for t in GRID_T:
            params = CompositionParams(k=k, inclusion_threshold=t, degradation="none")
            m = defaultdict(list)
            t0 = time.perf_counter()
            for hidden in queries:
                profile, cases = retrieved[hidden.id]
                prop = to_diet(composer.propose(profile, cases, rules, params))
                fns = metric_fns(hidden, catalog)
                hk, pk = key_set(hidden), key_set(prop)
                m["j_key"].append(fns["j_key"](prop)); m["j_food"].append(fns["j_food"](prop))
                p, r = precision_recall(hk, pk); m["p_key"].append(p); m["r_key"].append(r)
                m["size"].append(len(pk) / max(1, len(hk))); m["items"].append(len(pk)); m["slots"].append(len(prop.meals))
                m["per_slot"].append(fns["per_slot"](prop)); m["notes"].append(len(prop.notes))
                m["alt_groups"].append(sum(1 for me in prop.meals for it in me.items if it.alternative_group) / max(1, len(pk)))
            grid[f"k={k},t={t}"] = {"k": k, "threshold": t, "jaccard_key_top": mean(m["j_key"]), "jaccard_food": mean(m["j_food"]),
                                    "precision_key": mean(m["p_key"]), "recall_key": mean(m["r_key"]), "size_ratio": mean(m["size"]),
                                    "items_median": statistics.median(m["items"]), "slots_mean": mean(m["slots"]), "per_slot_jaccard_key": mean(m["per_slot"]),
                                    "notes_mean": mean(m["notes"]), "share_items_in_alternative_groups": mean(m["alt_groups"]),
                                    "compose_ms_per_query": round((time.perf_counter() - t0) / len(queries) * 1000, 2)}
            print(f"  k={k:2d} t={t:.2f}  Jkey {grid[f'k={k},t={t}']['jaccard_key_top']:.4f}  size {grid[f'k={k},t={t}']['size_ratio']:.2f}", file=sys.stderr)
    best = max(grid.values(), key=lambda g: (g["jaccard_key_top"], g["jaccard_food"]))
    report = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "protocol": {"queries": len(queries), "retrieval_strategy": root.retrieval_strategy, "k_max": max(GRID_K),
              "hidden_items_median": statistics.median(len(key_set(q)) for q in queries), "retrieval_ms_per_query": round(ms_retrieval, 1),
              "composer": "raw (no validator, no degradation) — the grid measures composition alone"}, "best_by_jaccard_key": {"k": best["k"], "threshold": best["threshold"]}, "grid": grid}
    (DATASET_DIR / "composer_grid.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"queries": len(queries), "best": report["best_by_jaccard_key"], "hidden_items_median": report["protocol"]["hidden_items_median"]}))
    for g in grid.values():
        print(f"{g['k']:3d} {g['threshold']:4.2f} | {g['jaccard_key_top']:7.4f} {g['jaccard_food']:7.4f} | {g['precision_key']:6.3f} {g['recall_key']:6.3f} | "
              f"{g['size_ratio']:5.2f} {g['items_median']:5.0f} {g['slots_mean']:5.2f} | {g['per_slot_jaccard_key']:6.4f} {g['notes_mean']:5.2f}")
    return 0


# ---------------------------------------------------------------------------------------------------------------- final
def run_final(args):
    root, pid, diets, profiles, queries, rules = setup()
    catalog = root.catalog
    engine = RuleEngine(catalog)
    rules_low = with_low_confidence_enabled(rules, True)
    k = args.k or root.composer.params.k
    t = args.threshold or root.composer.params.inclusion_threshold
    retrieved, ms_retrieval = retrieve_all(root, pid, queries, profiles, k)
    params = CompositionParams(k=k, inclusion_threshold=t)
    composer = composer_like(root, params)
    params_nodeg = dataclasses.replace(params, degradation="none")
    validators = {"validated_strict": DietValidator(catalog, RestrictionMode.STRICT, True),
                  "validated_professional": DietValidator(catalog, RestrictionMode.PROFESSIONAL, True),
                  "validated_no_enforcement": DietValidator(catalog, RestrictionMode.STRICT, False)}
    threshold = root.retrieve_similar_cases_service._threshold  # noqa: SLF001
    env = root.envelope.load(pid) if root.envelope is not None else None
    assert env is not None, "plausibility_envelope.json missing: run pipeline/src/pipeline/plausibility_envelope.py (make envelope)"
    rng = random.Random(args.seed)
    by_client: dict[str, list[str]] = defaultdict(list)
    for d in diets.values():
        by_client[d.client_code].append(d.id)

    records = []
    t_start = time.perf_counter()
    for hidden in queries:
        profile, cases = retrieved[hidden.id]
        excluded = root.retrieve_similar_cases_service.mandatory_exclusions(pid, profile)
        counts = root.case_repository.candidate_counts(pid, profile, excluded)
        allowed = [i for i in diets if i not in excluded]
        same_goal = [i for i in allowed if diets[i].goal == hidden.goal] or allowed
        other_goal = [i for i in allowed if diets[i].goal != hidden.goal] or allowed
        others = [diets[i] for i in by_client[hidden.client_code] if i != hidden.id and diets[i].template_group_id is None]

        raw = composer.propose(profile, cases, rules)
        nodeg = composer.propose(profile, cases, rules, params_nodeg)
        variants = {"floor_same_goal": diets[rng.choice(same_goal)], "floor_other_goal": diets[rng.choice(other_goal)], "copy_top1": cases[0].diet,
                    "composer_raw": to_diet(raw), "composer_no_degradation": to_diet(nodeg)}
        forced = {}
        for name, v in validators.items():
            vp = v.validate(raw, rules, profile, cases=cases)
            variants[name] = to_diet(vp); forced[name] = len(vp.validation.forced_changes)
        vlow = validators["validated_strict"].validate(raw, rules_low, profile, cases=cases)
        variants["validated_low_rules"] = to_diet(vlow); forced["validated_low_rules"] = len(vlow.validation.forced_changes)
        plaus, changes = apply_plausibility(raw, cases, env, catalog)                     # S2 layer, same order as the use case: strategy -> plausibility -> validator
        vplaus = validators["validated_strict"].validate(plaus, rules, profile, cases=cases)
        variants["plausible_unvalidated"] = to_diet(plaus)
        variants["validated_plausible"] = to_diet(vplaus); forced["validated_plausible"] = len(vplaus.validation.forced_changes)   # = delivered configuration
        vp_strict = validators["validated_strict"].validate(raw, rules, profile, cases=cases)
        plausibility = {"composer_raw": plausibility_summary(raw, env, catalog, rules), "validated_strict": plausibility_summary(vp_strict, env, catalog, rules),
                        "plausible_unvalidated": plausibility_summary(plaus, env, catalog, rules), "validated_plausible": plausibility_summary(vplaus, env, catalog, rules)}
        out_of_band, checked = hidden_out_of_band(hidden, env)

        fns = metric_fns(hidden, catalog)
        hk = key_set(hidden)
        rec = {"diet_id": hidden.id, "client_code": hidden.client_code, "goal": hidden.goal.value, "sex": profile.sex, "age_bucket": profile.age_bucket,
               "hidden_items": len(hk), "hidden_slots": sorted(slot_sets(hidden)), "hidden_notes": len(hidden.notes), "subset_excl_nn": len(others) >= 2,
               "k_effective": raw.parameters["k_effective"], "same_goal_in_k": raw.parameters["same_goal_cases"], "degradation": raw.parameters["degradation"],
               "same_goal_available": counts.same_goal, "total_available": counts.total,
               "gap_triggered": list(assess_gap(counts, k, cases[0].score.total, threshold).triggered),
               "plausibility": plausibility, "plausibility_changes": dict(Counter(c.kind for c in changes)),
               "hidden_quantities_out_of_band": out_of_band, "hidden_quantities_checked": checked,
               "variants": {}, "ceiling_incl_nn": {}, "ceiling_excl_nn": None, "slot_jaccard": {}}
        for name, d in variants.items():
            v = {m: round(fns[m](d), 4) for m in METRICS}
            p, r = precision_recall(hk, key_set(d))
            v.update({"p_key": round(p, 4), "r_key": round(r, 4), "size": round(len(key_set(d)) / max(1, len(hk)), 4), "notes": len(d.notes), "forced": forced.get(name)})
            for rs_name, rs in (("", rules), ("_low", rules_low)):
                v[f"compliance_all{rs_name}"] = engine.compliance(rs, d, profile)[0]
                v[f"compliance_cond{rs_name}"] = engine.compliance(rs, d, profile, only=CONDITIONAL_RULES)[0]
            # per-rule attribution of the conditional compliance: without it a movement in the aggregate cannot be explained
            v["cond_by_rule"] = {c.rule_id: c.satisfied for c in engine.check(rules, d, profile) if c.applicable and c.rule_id in CONDITIONAL_RULES}
            # per-rule state of ALL the rules, recorded only where the ANTECEDENT holds (engine.evaluate returns None otherwise).
            # This is the raw material of the aggregation-bias diagnosis: a rate measured over the total, and not over the
            # antecedent subset, compares two different denominators and every conclusion drawn from it is wrong.
            v["by_rule"] = {c.rule_id: c.satisfied for c in engine.check(rules, d, profile) if c.applicable}
            v["compliance_cond_prescriptive"] = engine.compliance(rules, d, profile, only=CONDITIONAL_PRESCRIPTIVE)[0]
            rec["variants"][name] = v
        for rs_name, rs in (("", rules), ("_low", rules_low)):
            rec[f"hidden_compliance_all{rs_name}"] = engine.compliance(rs, hidden, profile)[0]
            rec[f"hidden_compliance_cond{rs_name}"] = engine.compliance(rs, hidden, profile, only=CONDITIONAL_RULES)[0]
        rec["hidden_cond_by_rule"] = {c.rule_id: c.satisfied for c in engine.check(rules, hidden, profile) if c.applicable and c.rule_id in CONDITIONAL_RULES}
        rec["hidden_by_rule"] = {c.rule_id: c.satisfied for c in engine.check(rules, hidden, profile) if c.applicable}
        rec["hidden_compliance_cond_prescriptive"] = engine.compliance(rules, hidden, profile, only=CONDITIONAL_PRESCRIPTIVE)[0]
        for m in METRICS:
            scores = sorted((fns[m](o) for o in others), reverse=True)
            rec["ceiling_incl_nn"][m] = round(statistics.fmean(scores), 4)
            if len(scores) >= 2:
                rec["ceiling_excl_nn"] = rec["ceiling_excl_nn"] or {}
                rec["ceiling_excl_nn"][m] = round(statistics.fmean(scores[1:]), 4)
        hs = slot_sets(hidden)
        comp_s, copy_s, val_s, del_s = slot_sets(variants["composer_raw"]), slot_sets(variants["copy_top1"]), slot_sets(variants["validated_strict"]), slot_sets(variants["validated_plausible"])
        for slot, hset in hs.items():
            rec["slot_jaccard"][slot] = {"composer": round(jaccard(hset, comp_s.get(slot, frozenset())), 4), "copy": round(jaccard(hset, copy_s.get(slot, frozenset())), 4),
                                        "validated": round(jaccard(hset, val_s.get(slot, frozenset())), 4), "delivered": round(jaccard(hset, del_s.get(slot, frozenset())), 4),
                                        "ceiling_incl_nn": round(statistics.fmean(jaccard(hset, slot_sets(o).get(slot, frozenset())) for o in others), 4),
                                        "composer_present": slot in comp_s, "hidden_items": len(hset)}
        records.append(rec)

    out = DATASET_DIR / "composer_per_query.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "queries": len(records), "params": params.as_dict(), "retrieval_strategy": root.retrieval_strategy,
            "retrieval_ms_per_query": round(ms_retrieval, 1), "harness_s": round(time.perf_counter() - t_start, 1), "seed": args.seed,
            "conditional_rules": sorted(CONDITIONAL_RULES), "gap_threshold": threshold, "degradation_modes": dict(Counter(r["degradation"] for r in records)),
            "delivered_variant": "validated_plausible", "pipeline": "strategy -> plausibility layer (complete_structure + normalize_quantities) -> validator (strict, enforcement)"}
    (DATASET_DIR / "composer_per_query_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({**meta, "j_key_composer": mean([r["variants"]["composer_raw"]["j_key"] for r in records]),
                      "j_key_composer_no_degradation": mean([r["variants"]["composer_no_degradation"]["j_key"] for r in records]),
                      "j_key_validated": mean([r["variants"]["validated_strict"]["j_key"] for r in records]),
                      "j_key_delivered": mean([r["variants"]["validated_plausible"]["j_key"] for r in records]),
                      "violations_validated": mean([r["plausibility"]["validated_strict"]["violations"] for r in records]),
                      "violations_delivered": mean([r["plausibility"]["validated_plausible"]["violations"] for r in records]),
                      "j_key_copy": mean([r["variants"]["copy_top1"]["j_key"] for r in records])}, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------------------------------------------------ recurrent (2.4)
VERSION_RX = re.compile(r"::v(\d+)(?:-\d+)?$")


def version_number(diet_id: str) -> int | None:
    m = VERSION_RX.search(diet_id)
    n = int(m.group(1)) if m else None
    return n if n is not None and n < 1000 else None          # 'vYYYY' ids are dates, not sequence numbers


def run_recurrent(args):
    """Recurrent-client scenario: the hidden diet is a version with at least one STRICTLY earlier version of the same client.
    History = earlier versions (asserted). Candidates for retrieval = corpus minus the hidden diet, its same-number re-issues, every later
    version of the client and the template groups; the client's earlier versions ARE candidates (in production the professional has them).
    Variants: copy_previous (baseline), cold composer (E5 protocol: client fully excluded), composer with own history as candidates,
    rotation composer (previous version + rotation policy, stats without this client), rotation validated.
    Novelty = Jaccard against the previous version (human target = hidden vs previous)."""
    root, pid, diets, profiles, queries, rules = setup()
    catalog = root.catalog
    engine = RuleEngine(catalog)
    k = args.k or root.composer.params.k
    t = args.threshold or root.composer.params.inclusion_threshold
    params = CompositionParams(k=k, inclusion_threshold=t)
    cold = composer_like(root, params)
    stats_all = root.rotation_stats.load(pid)
    rot = RotationComposer(catalog, stats_all, params, notes=root.composer._notes)  # noqa: SLF001
    validator = DietValidator(catalog, RestrictionMode.STRICT, True)
    env = root.envelope.load(pid) if root.envelope is not None else None
    assert env is not None, "plausibility_envelope.json missing: run pipeline/src/pipeline/plausibility_envelope.py (make envelope)"
    svc = root.retrieve_similar_cases_service
    by_client: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for d in diets.values():
        n = version_number(d.id)
        if n is not None and d.template_group_id is None:
            by_client[d.client_code].append((n, d.id))
    records = []
    skipped_unscorable_previous = 0
    t_start = time.perf_counter()
    for hidden in queries:
        n_h = version_number(hidden.id)
        if n_h is None:
            continue
        earlier = [i for n, i in by_client[hidden.client_code] if n < n_h]
        if not earlier:
            continue
        later_or_same = {i for n, i in by_client[hidden.client_code] if n >= n_h}          # hidden, its re-issues and every later version
        history = tuple(diets[i] for i in earlier)
        assert all(version_number(h.id) < n_h for h in history), hidden.id                  # leak guard: strictly earlier versions only
        previous = max(history, key=lambda d: (version_number(d.id), d.id))
        # The recurrent baseline is "copy the previous version", so the PREVIOUS diet has to be scorable too. One
        # client's v03 sits entirely inside the non-composable bucket: copying it proposes nothing, the Jaccard of
        # two empty sets reads 0, and the baseline that is identical to its target by construction scored 0,9986
        # instead of 1. Excluding the hidden diet is not enough; the history it is measured against counts.
        if not scorable_keys(previous):
            skipped_unscorable_previous += 1
            continue
        profile = as_of_profile(root, pid, profiles[hidden.client_code], hidden.goal, hidden.id)
        cases_cold = svc.retrieve(pid, profile, k)                                          # E5 protocol (client excluded)
        cases_rec = svc.retrieve(pid, profile, k, exclude_diet_ids=frozenset(later_or_same), include_own_history=True)
        assert not ({c.diet.id for c in cases_rec} & later_or_same), hidden.id              # leak guard: no later version among the candidates
        stats = stats_all.without_client(hidden.client_code)
        prop_cold = cold.propose(profile, cases_cold, rules)
        prop_hist = cold.propose(profile, cases_rec, rules)
        prop_rot = rot.propose(profile, cases_rec, rules, history=history, stats=stats)
        prop_rot_cons = rot.propose(profile, cases_rec, rules, history=history, stats=stats, rotation=RotationParams(use_repertoire=False))
        prop_rot_val = validator.validate(prop_rot, rules, profile, cases=cases_rec)
        prop_routed = prop_hist if previous.goal != hidden.goal else prop_rot                # routing rule: goal changed -> archetype (history as candidates); same goal -> rotate previous
        prop_routed_val = validator.validate(prop_routed, rules, profile, cases=cases_rec)
        prop_routed_plaus, changes = apply_plausibility(prop_routed, cases_rec, env, catalog)   # S2 layer in the use-case order: strategy -> plausibility -> validator
        prop_delivered = validator.validate(prop_routed_plaus, rules, profile, cases=cases_rec)
        variants = {"copy_previous": previous, "cold_composer": to_diet(prop_cold), "composer_history_candidates": to_diet(prop_hist),
                    "rotation_composer": to_diet(prop_rot), "rotation_validated": to_diet(prop_rot_val), "rotation_consensus_only": to_diet(prop_rot_cons),
                    "routed": to_diet(prop_routed), "routed_validated": to_diet(prop_routed_val), "routed_delivered": to_diet(prop_delivered)}   # routed_delivered = delivered configuration
        fns = metric_fns(hidden, catalog)
        prev_keys, prev_foods = key_set(previous), food_set(previous)
        rec = {"diet_id": hidden.id, "client_code": hidden.client_code, "goal": hidden.goal.value, "previous_id": previous.id, "goal_changed": previous.goal != hidden.goal,
               "history_size": len(history), "hidden_items": len(key_set(hidden)), "previous_items": len(prev_keys),
               "own_versions_among_cases": sum(1 for c in cases_rec if c.diet.client_code == hidden.client_code),
               "rotation": {kk: prop_rot.parameters.get(kk) for kk in ("renewal_target", "rotated_items", "renewal_applied", "goal_changed")},
               "rotation_consensus_only": {kk: prop_rot_cons.parameters.get(kk) for kk in ("rotated_items", "renewal_applied")},
               "novelty_human": {"j_key": round(jaccard(key_set(hidden), prev_keys), 4), "j_food": round(jaccard(food_set(hidden), prev_foods), 4)},
               "plausibility": {"routed": plausibility_summary(prop_routed, env, catalog, rules), "routed_validated": plausibility_summary(prop_routed_val, env, catalog, rules),
                                "routed_delivered": plausibility_summary(prop_delivered, env, catalog, rules)},
               "plausibility_changes": dict(Counter(c.kind for c in changes)),
               "variants": {}}
        for name, d in variants.items():
            v = {m: round(fns[m](d), 4) for m in ("j_key", "j_food", "j_family", "per_slot")}
            v["novelty_j_key"] = round(jaccard(key_set(d), prev_keys), 4); v["novelty_j_food"] = round(jaccard(food_set(d), prev_foods), 4)
            v["size"] = round(len(key_set(d)) / max(1, len(key_set(hidden))), 4)
            v["compliance_cond"] = engine.compliance(rules, d, profile, only=CONDITIONAL_RULES)[0]
            rec["variants"][name] = v
        rec["variants"]["rotation_validated"]["forced"] = len(prop_rot_val.validation.forced_changes)
        rec["variants"]["routed_validated"]["forced"] = len(prop_routed_val.validation.forced_changes)
        rec["variants"]["routed_delivered"]["forced"] = len(prop_delivered.validation.forced_changes)
        records.append(rec)
    out = DATASET_DIR / "recurrent_per_query.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "queries": len(records), "params": params.as_dict(), "k": k,
            "skipped_unscorable_previous": skipped_unscorable_previous, "harness_s": round(time.perf_counter() - t_start, 1),
            "renewal_targets": {"same_goal": stats_all.renewal_same_goal, "goal_change": stats_all.renewal_goal_change},
            "protocol": "hidden = version with >= 1 strictly earlier version; history = earlier versions (asserted); candidates exclude hidden, same-number re-issues, later versions and template groups",
            "delivered_variant": "routed_delivered", "pipeline": "routing -> strategy -> plausibility layer -> validator (strict, enforcement)"}
    (DATASET_DIR / "recurrent_per_query_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {n: mean([r["variants"][n]["j_key"] for r in records]) for n in variants}
    summary["novelty_human_j_key"] = mean([r["novelty_human"]["j_key"] for r in records])
    summary["novelty_rotation_j_key"] = mean([r["variants"]["rotation_composer"]["novelty_j_key"] for r in records])
    summary["novelty_cold_j_key"] = mean([r["variants"]["cold_composer"]["novelty_j_key"] for r in records])
    print(json.dumps({**meta, "j_key_vs_hidden": summary}, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--recurrent", action="store_true", help="recurrent-client scenario (2.4) -> _dataset/recurrent_per_query.jsonl")
    ap.add_argument("--k", type=int, default=None, help="defaults to Settings.composer_k")
    ap.add_argument("--threshold", type=float, default=None, help="defaults to Settings.composer_inclusion_threshold")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.grid:
        return run_grid(args)
    if args.final:
        return run_final(args)
    if args.recurrent:
        return run_recurrent(args)
    ap.error("choose --grid, --final or --recurrent")
    return 2


if __name__ == "__main__":
    sys.exit(main())
