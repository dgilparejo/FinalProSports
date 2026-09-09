# -*- coding: utf-8 -*-
"""
S2 — Plausibility envelope mined from the corpus: THE DATA SETS THE LIMITS, not the author's judgement.

Input:  $FPS_DATASET_DIR/diet_items.jsonl + foods.json (whatever dataset FPS_DATASET_DIR points at; the tag travels into `source`)
Output: $FPS_DATASET_DIR/plausibility_envelope.json
        docs/data/plausibility_envelope.md — GENERATED, not versioned (aggregates only)

What is measured
  quantities        per (food_id, unit) with n >= MIN_N observations: p05 / p50 / p95 of the quantity written by the professional.
                    This is what catches «3 g de pollo» or «2 kg de arroz» in a generated proposal.
  items_per_slot    per meal slot: p05 / p50 / p95 of the number of DISTINCT catalogue foods per (diet, slot) — distinct, because
                    the corpus repeats a line per weekday in some documents.
  slots_per_diet    p05 / p50 / p95 of the number of slots per diet.
  repeats_per_slot  per meal slot (and per goal x slot): p05 / p50 / p95 of the number of REPEATED food occurrences in a (diet, slot),
                    i.e. components - distinct foods, alternatives included («aceite» written on two lines, «pollo» as dish and as
                    alternative). The plan's assertion «no food repeated inside a slot» was refuted by the corpus (Fase 9): the
                    professional repeats 3.5 times per diet in 65 % of his diets, so the demandable limit is his own p95, per goal.
  units_per_food    the units observed for each food (a proposal using an unseen unit is reported).
  alternative_groups how the professional writes alternatives («150 gr Pollo / 160 gr Pavo / 180 gr Lomo»): share of groups whose members
                    belong to different FAMILIES and share of groups with NO macro group in common, plus the per-diet p95 of the latter.
                    (Measured 2026-08-26: 63 % of his alternative groups mix families, 21 % mix macro groups; so a proposal may not be
                    required to keep alternatives inside one family — the data-driven limit is the per-diet share of mixed groups.)
  alternative_groups how the professional writes alternatives («150 gr Pollo / 160 gr Pavo / 180 gr Lomo»): share of groups whose members
                    belong to different FAMILIES and share of groups with NO macro group in common, plus the per-diet p95 of the latter.
                    (Measured 2026-08-26: 63 % of his alternative groups mix families, 21 % mix macro groups; so a proposal may not be
                    required to keep alternatives inside one family — the data-driven limit is the per-diet share of mixed groups.)
Nothing personal is read or printed: pseudonymous ids, canonical food names and counts only.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR, DOCS_DIR  # noqa: E402

MIN_N = 10


def pct(values: list[float]) -> dict:
    vs = sorted(values)
    if len(vs) < 2:
        return {"n": len(vs), "p05": vs[0], "p50": vs[0], "p95": vs[0], "min": vs[0], "max": vs[0]}
    q = statistics.quantiles(vs, n=20, method="inclusive")          # q[0] = p05, q[9] = p50, q[18] = p95
    return {"n": len(vs), "p05": round(q[0], 2), "p50": round(q[9], 2), "p95": round(q[18], 2), "min": vs[0], "max": vs[-1]}


def build(dataset: Path) -> dict:
    items = [json.loads(l) for l in (dataset / "diet_items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    foods = {f["id"]: f for f in json.loads((dataset / "foods.json").read_text(encoding="utf-8"))["foods"]}
    goal_of = {d["id"]: d["meta"]["goal"] for d in (json.loads(l) for l in (dataset / "diets.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    by_food_unit: dict[tuple[int, str], list[float]] = defaultdict(list)
    units_per_food: dict[int, Counter] = defaultdict(Counter)
    per_slot_foods: dict[tuple[str, str], set[int]] = defaultdict(set)
    per_slot_components: dict[tuple[str, str], int] = defaultdict(int)          # mapped components per (diet, slot), alternatives included
    slots_per_diet: dict[str, set[str]] = defaultdict(set)
    alt_groups: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for it in items:
        fid = it.get("food_id")
        slots_per_diet[it["diet_id"]].add(it["meal_slot"])
        if fid is None:
            continue
        per_slot_foods[(it["diet_id"], it["meal_slot"])].add(fid)
        per_slot_components[(it["diet_id"], it["meal_slot"])] += 1
        if it.get("alternative_group"):
            alt_groups[(it["diet_id"], it["meal_slot"], it["alternative_group"])].add(fid)
        if it.get("alternative_group"):
            alt_groups[(it["diet_id"], it["meal_slot"], it["alternative_group"])].add(fid)
        if it.get("quantity") is not None and it.get("unit"):
            by_food_unit[(fid, it["unit"])].append(float(it["quantity"]))
            units_per_food[fid][it["unit"]] += 1
    quantities = {}
    for (fid, unit), vals in sorted(by_food_unit.items()):
        if len(vals) >= MIN_N:
            quantities[f"{fid}|{unit}"] = {"food_id": fid, "canonical_name": foods[fid]["canonical_name"], "unit": unit, **pct(vals)}
    slots: dict[str, list[int]] = defaultdict(list)
    for (_, slot), fs in per_slot_foods.items():
        slots[slot].append(len(fs))
    items_per_slot = {slot: pct([float(v) for v in vals]) for slot, vals in sorted(slots.items()) if len(vals) >= MIN_N}
    repeats: dict[str, list[float]] = defaultdict(list)
    repeats_goal: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (diet_id, slot), fs in per_slot_foods.items():
        r = float(per_slot_components[(diet_id, slot)] - len(fs))
        repeats[slot].append(r)
        repeats_goal[goal_of.get(diet_id, "sin_clasificar")][slot].append(r)
    repeats_per_slot = {slot: pct(vals) for slot, vals in sorted(repeats.items()) if len(vals) >= MIN_N}
    repeats_per_slot_by_goal = {g: {slot: pct(vals) for slot, vals in sorted(d.items()) if len(vals) >= MIN_N} for g, d in sorted(repeats_goal.items())}
    repeats_per_slot_by_goal = {g: d for g, d in repeats_per_slot_by_goal.items() if d}
    diets_with_repeat = len({diet_id for (diet_id, slot), fs in per_slot_foods.items() if per_slot_components[(diet_id, slot)] > len(fs)})
    repeats_summary = {"per_diet_mean": round(sum(v for vals in repeats.values() for v in vals) / len(slots_per_diet), 2),
                       "diets_with_any_repeat_share": round(diets_with_repeat / len(slots_per_diet), 3)}
    n_slots = [float(len(s)) for s in slots_per_diet.values()]
    def macro(fid):
        f = foods[fid]
        return {f["group"]} | ({f["secondary_group"]} if f.get("secondary_group") else set())
    per_diet: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for (diet_id, _, _), fs in alt_groups.items():
        if len(fs) >= 2:
            per_diet[diet_id].append((not set.intersection(*[macro(f) for f in fs]), len({foods[f]["family"] for f in fs}) > 1))
    all_groups = [g for gs in per_diet.values() for g in gs]
    by_goal: dict[str, list[float]] = defaultdict(list)
    for diet_id, gs in per_diet.items():
        by_goal[goal_of.get(diet_id, "sin_clasificar")].append(sum(1 for m, _ in gs if m) / len(gs))
    per_goal = {g: pct(v) for g, v in sorted(by_goal.items()) if len(v) >= MIN_N}       # the professional mixes more in some goals (alta_en_fibra 0,62 vs volumen 0,50)
    alternative_groups = {"groups": len(all_groups), "mixed_macro_share": round(sum(1 for m, _ in all_groups if m) / len(all_groups), 3) if all_groups else None,
                          "family_differs_share": round(sum(1 for _, d in all_groups if d) / len(all_groups), 3) if all_groups else None,
                          "per_diet_mixed_macro_share": pct([sum(1 for m, _ in gs if m) / len(gs) for gs in per_diet.values()]),
                          "per_goal_mixed_macro_share": per_goal,
                          "fallback_p95": max((v["p95"] for v in per_goal.values()), default=None)}    # goals with n < MIN_N: anything he does in some goal is acceptable
    # The source is READ from the dataset, not written here. A hardcoded label survived the change of dataset and the
    # artefact went on claiming «dataset-v1» while it had been mined from another corpus; a stale label on an artefact
    # the engine reads is how a wrong food id goes unnoticed.
    tag = None
    version = dataset / "VERSION.json"
    if version.exists():
        tag = json.loads(version.read_text(encoding="utf-8")).get("tag")
    return {"source": f"diet_items.jsonl ({tag or dataset.name}, E1 catalogue)", "min_n": MIN_N,
            "summary": {"diets": len(slots_per_diet), "components": len(items), "food_unit_pairs_total": len(by_food_unit), "food_unit_pairs_with_envelope": len(quantities),
                        "slots_with_envelope": len(items_per_slot)},
            "quantities": quantities, "items_per_slot": items_per_slot, "slots_per_diet": pct(n_slots), "alternative_groups": alternative_groups,
            "repeats_per_slot": repeats_per_slot, "repeats_per_slot_by_goal": repeats_per_slot_by_goal, "repeats_summary": repeats_summary,
            "units_per_food": {str(fid): dict(c.most_common()) for fid, c in sorted(units_per_food.items())}}


def markdown(env: dict) -> str:
    s = env["summary"]
    lines = ["# Envolvente de plausibilidad (S2)", "",
             f"Minada de `diet_items.jsonl` (dataset-v1): {s['diets']} dietas, {s['components']} componentes. Los límites los pone el dato: para cada par "
             f"(alimento, unidad) con n ≥ {env['min_n']} observaciones se registran p05 / p50 / p95 de la cantidad; {s['food_unit_pairs_with_envelope']} de "
             f"{s['food_unit_pairs_total']} pares tienen envolvente. Por franja, p05 / p95 del número de alimentos distintos; "
             f"franjas por dieta p05 {env['slots_per_diet']['p05']:.0f} / p50 {env['slots_per_diet']['p50']:.0f} / p95 {env['slots_per_diet']['p95']:.0f}.", "",
             "## Alimentos distintos por franja", "", "| Franja | n | p05 | p50 | p95 |", "|---|---|---|---|---|"]
    for slot, v in env["items_per_slot"].items():
        lines.append(f"| {slot} | {v['n']} | {v['p05']:.0f} | {v['p50']:.0f} | {v['p95']:.0f} |")
    rp = env["repeats_per_slot"]; rs = env["repeats_summary"]
    lines += ["", "## Alimentos repetidos dentro de la franja (componentes − alimentos distintos; alternativas incluidas)", "",
              f"La aserción del plan «ningún alimento repetido en la misma franja» queda refutada por el corpus: el profesional repite de media "
              f"{rs['per_diet_mean']:.2f} veces por dieta y lo hace en el {rs['diets_with_any_repeat_share']:.0%} de sus dietas («aceite» en dos líneas, "
              f"«pollo» como plato y como alternativa). El límite exigible es su p95 por franja y objetivo (objetivos o franjas con n < {env['min_n']}: p95 global de la franja).", "",
              "| Franja | n | p50 | p95 | p95 por objetivo |", "|---|---|---|---|---|"]
    for slot, v in rp.items():
        per_goal = ", ".join(f"{g} {d[slot]['p95']:.0f}" for g, d in env["repeats_per_slot_by_goal"].items() if slot in d)
        lines.append(f"| {slot} | {v['n']} | {v['p50']:.0f} | **{v['p95']:.0f}** | {per_goal} |")
    ag = env["alternative_groups"]
    lines += ["", f"**Grupos de alternativas** («pollo / pavo / lomo»): {ag['groups']} grupos con ≥ 2 alimentos; el {ag['family_differs_share']:.0%} mezcla familias y el "
              f"{ag['mixed_macro_share']:.0%} no comparte ningún macrogrupo (p95 por dieta {ag['per_diet_mixed_macro_share']['p95']:.2f}). La aserción «alternativas de la misma "
              "familia» del plan queda refutada por el corpus: el límite exigible es la cuota por dieta de grupos sin macrogrupo común, p95 POR OBJETIVO "
              "(" + ", ".join(f"{g} {v['p95']:.2f}" for g, v in ag["per_goal_mixed_macro_share"].items()) + f"; objetivos con n < {env['min_n']}: {ag['fallback_p95']:.2f})."]
    lines += ["", "## Cantidades: los 40 pares (alimento, unidad) más observados", "", "| Alimento | Unidad | n | p05 | p50 | p95 |", "|---|---|---|---|---|---|"]
    for q in sorted(env["quantities"].values(), key=lambda q: -q["n"])[:40]:
        lines.append(f"| {q['canonical_name']} | {q['unit']} | {q['n']} | {q['p05']:g} | {q['p50']:g} | {q['p95']:g} |")
    lines += ["", "La envolvente la consume `domain/composition/policy/plausibility_policy.py` (tests golden, `make golden`): una cantidad fuera de "
              "[p05, p95] para su alimento y unidad es una violación con nombre de perfil, alimento, cantidad y rango.", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=DATASET_DIR)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--doc", type=Path, default=DOCS_DIR / "data" / "plausibility_envelope.md")
    args = ap.parse_args()
    env = build(args.dataset)
    out = args.out or (args.dataset / "plausibility_envelope.json")
    out.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    # Explicit, like rotation_analysis's --doc. Writing to docs/ unconditionally overwrote the PUBLISHED v2 report
    # the first time this ran against another dataset, and guarding on `args.dataset == DATASET_DIR` does not help
    # because DATASET_DIR follows FPS_DATASET_DIR and is therefore whatever the caller just pointed it at.
    args.doc.write_text(markdown(env), encoding="utf-8", newline="\n")
    print(json.dumps(env["summary"] | {"slots_per_diet": env["slots_per_diet"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
