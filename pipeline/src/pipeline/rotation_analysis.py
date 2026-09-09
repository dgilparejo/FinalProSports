# -*- coding: utf-8 -*-
"""
Rotation analysis (2.2): the professional's deliberate variation policy between successive versions of a client's diet.

Input:  _dataset/diets.jsonl (client, version, template flag), _dataset/diet_items.jsonl (canonical food per slot), _dataset/foods.json
Output: _dataset/rotation_analysis.json (all tables) and docs/data/rotation_analysis.md — GENERATED, not versioned (report, Spanish)

Protocol
  - Pairs = consecutive versions (v_n, v_{n+1}) of the same client, ordered by version number, `v` series only (the `s` series are
    supplement/special sheets), template diets excluded (the same document delivered to several clients is not a version step).
  - Persistence of a food = P(food in v_{n+1} | food in v_n), with n = number of pairs where the food is in v_n.
    Expected persistence by chance = the food's prevalence among the diets of the same goal (how often it would appear anyway):
    lift = persistence / prevalence separates "anchor because ubiquitous" from "kept on purpose".
  - Classification (same convention as the rule constitution: prevalence, n, confidence):
        ancla        persistence >= 0.80        rotatorio  persistence <= 0.50        intermedio otherwise
        confidence   high n >= 30 · medium 10-29 · low < 10 (low-confidence rows are reported but not classified)
  - Per family and per slot: the same persistence, and the renewal rate of the slot.
  - Global renewal per pair: dropped = 1 - |A ∩ B| / |A| (share of v_n foods that disappear), new = 1 - |A ∩ B| / |B|, Jaccard(A, B).
  - Alternative groups («150 gr pollo / 160 gr pavo / 180 gr lomo», same slot, same position): what the professional himself treats as
    interchangeable. Share of groups whose members belong to different families, share of those that still share a macro group (group or
    secondary group of the catalogue = the same role in the meal), share with no macro group in common; per goal; most frequent family pairs.
    This is the finding that nuances "rotation is intra-family" (section 6): the unit of interchangeability is the role in the meal.
Nothing printed but aggregates (pseudonymous ids never printed).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from itertools import combinations

MIN_INTERCHANGEABLE = 2      # once can be a typo of his; twice is a choice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR, DOCS_DIR  # noqa: E402

DOCS = DOCS_DIR / "data" / "rotation_analysis.md"
ANCHOR, ROTATORY = 0.80, 0.50
SLOT_ORDER = ["DESAYUNO", "MEDIA MAÑANA", "ALMUERZO", "COMIDA", "MERIENDA", "ANTES DE ENTRENAR", "DESPUES DE ENTRENAR", "CENA", "BATIDO", "OTHER"]
VERSION_RX = re.compile(r"::v(\d+)(?:-\d+)?$")


def jl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def pct(xs, p):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 4)


def confidence(n: int) -> str:
    return "high" if n >= 30 else "medium" if n >= 10 else "low"


def classify(persist: float, n: int) -> str:
    if n < 10:
        return "no_concluyente"
    return "ancla" if persist >= ANCHOR else "rotatorio" if persist <= ROTATORY else "intermedio"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=DATASET_DIR)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "rotation_analysis.json")
    ap.add_argument("--doc", type=Path, default=DOCS)
    args = ap.parse_args()

    diets = {d["id"]: d for d in jl(args.dataset / "diets.jsonl")}
    items = jl(args.dataset / "diet_items.jsonl")
    foods = {f["id"]: f for f in json.load(open(args.dataset / "foods.json", encoding="utf-8"))["foods"]}
    by_diet: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))     # diet -> slot -> food ids
    for it in items:
        if it["food_id"] is not None:
            by_diet[it["diet_id"]][it["meal_slot"]].add(it["food_id"])
    all_foods = {d: set().union(*s.values()) if s else set() for d, s in by_diet.items()}
    fam_of = {fid: f["family"] for fid, f in foods.items()}

    # ---- alternative groups: what he writes as interchangeable inside one meal (same measure as pipeline/plausibility_envelope.py)
    goal_of_diet = {d["id"]: d["meta"]["goal"] for d in diets.values()}
    alt_members: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for it in items:
        if it["food_id"] is not None and it.get("alternative_group"):
            alt_members[(it["diet_id"], it["meal_slot"], it["alternative_group"])].add(it["food_id"])

    def macro(fid: int) -> set[str]:
        f = foods[fid]
        return {f["group"]} | ({f["secondary_group"]} if f.get("secondary_group") else set())

    alt_by_goal: dict[str, Counter] = defaultdict(Counter)
    pair_n, pair_shared_macro = Counter(), Counter()
    food_pair_n: Counter = Counter()          # the FOOD pairs he writes as alternatives of each other: the rotation's own criterion
    for (diet_id, _, _), fs in alt_members.items():
        if len(fs) < 2:
            continue
        fams = {fam_of[f] for f in fs}
        shared_macro = bool(set.intersection(*[macro(f) for f in fs]))
        c = alt_by_goal[goal_of_diet.get(diet_id, "sin_clasificar")]
        c["groups"] += 1
        c["mixed_family"] += len(fams) > 1
        c["mixed_family_shared_macro"] += (len(fams) > 1) and shared_macro
        c["no_common_macro"] += not shared_macro
        for a, b in combinations(sorted(fs), 2):
            food_pair_n[(a, b)] += 1
        if len(fams) > 1:
            for a, b in combinations(sorted(fams), 2):
                pair_n[(a, b)] += 1; pair_shared_macro[(a, b)] += shared_macro
    alt_total = sum((c for c in alt_by_goal.values()), Counter())

    def alt_row(name: str, c: Counter) -> dict:
        g = c["groups"]
        return {"goal": name, "groups": g, "mixed_family_share": round(c["mixed_family"] / g, 3) if g else None,
                "mixed_family_shared_macro_share": round(c["mixed_family_shared_macro"] / c["mixed_family"], 3) if c["mixed_family"] else None,
                "no_common_macro_share": round(c["no_common_macro"] / g, 3) if g else None, "confidence": confidence(g)}
    alternative_groups = {"total": alt_row("todos", alt_total),
                          "by_goal": [alt_row(g, c) for g, c in sorted(alt_by_goal.items(), key=lambda kv: -kv[1]["groups"])],
                          "top_family_pairs": [{"families": list(k), "n": n, "shared_macro_share": round(pair_shared_macro[k] / n, 3)}
                                               for k, n in pair_n.most_common(15)],
                          # Pairs of FOODS he himself offers as alternatives, seen at least MIN_INTERCHANGEABLE times. The rotation
                          # uses them to decide what may replace what: the catalogue's families cannot, because «condimento» holds
                          # garlic, turmeric, parsley, salt and sweetener together and a family-only rule offered sweetener in place
                          # of garlic. His own practice is both stricter (he uses 38 % of the same-family pairs the catalogue allows)
                          # and richer (only 24 % of the pairs he writes share a family: ave/pescado_blanco, arroz/pasta).
                          "interchangeable_foods": {"min_times": MIN_INTERCHANGEABLE,
                                                    "pairs": sorted([a, b] for (a, b), n in food_pair_n.items() if n >= MIN_INTERCHANGEABLE)}}

    # ---- consecutive pairs
    versions: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for d in diets.values():
        m = VERSION_RX.search(d["id"])
        if not m or d["meta"].get("template_group_id"):
            continue
        versions[d["meta"]["client_code"]].append((int(m.group(1)), d["id"]))
    pairs, excluded_pairs = [], Counter()
    for c, vs in versions.items():
        vs.sort()
        for (n1, a), (n2, b) in zip(vs, vs[1:]):
            if not (a in all_foods and b in all_foods and all_foods[a] and all_foods[b]):
                excluded_pairs["empty_diet"] += 1; continue
            gap = n2 - n1
            if gap == 0:                      # re-issue of the same version number (v19 / v19-2): a revision, not a version step
                excluded_pairs["same_version_reissue"] += 1; continue
            if gap >= 50 or n1 >= 1000 or n2 >= 1000:   # 'vYYYY' ids are dates, not sequence numbers: order not guaranteed
                excluded_pairs["year_like_version"] += 1; continue
            pairs.append((c, a, b, gap))
    clients = {c for c, *_ in pairs}

    # ---- prevalence by goal (chance persistence)
    goal_diets: dict[str, list[str]] = defaultdict(list)
    for d in diets.values():
        if d["id"] in all_foods and not d["meta"].get("template_group_id"):
            goal_diets[d["meta"]["goal"]].append(d["id"])
    prevalence = {}
    for g, ids in goal_diets.items():
        cnt = Counter(f for i in ids for f in all_foods[i])
        prevalence[g] = {f: cnt[f] / len(ids) for f in cnt}

    # ---- persistence per food, per family, per slot
    food_n, food_keep, food_chance = Counter(), Counter(), defaultdict(list)
    per_client: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # client -> food -> [n, kept] (leave-one-client-out)
    fam_n, fam_keep = Counter(), Counter()
    slot_n, slot_keep = Counter(), Counter()
    slot_food_n, slot_food_keep = Counter(), Counter()
    slot_renewal = defaultdict(list)
    renewal_dropped, renewal_new, jac, same_goal_pairs = [], [], [], 0
    dropped_same_goal, dropped_goal_change, jac_same_goal = [], [], []
    for c, a, b, gap in pairs:
        A, B = all_foods[a], all_foods[b]
        goal_b = diets[b]["meta"]["goal"]
        same = diets[a]["meta"]["goal"] == goal_b
        same_goal_pairs += same
        inter = A & B
        d = 1 - len(inter) / len(A)
        renewal_dropped.append(d); renewal_new.append(1 - len(inter) / len(B)); jac.append(len(inter) / len(A | B))
        (dropped_same_goal if same else dropped_goal_change).append(d)
        if same:
            jac_same_goal.append(len(inter) / len(A | B))
        for f in A:
            food_n[f] += 1; food_keep[f] += f in B; food_chance[f].append(prevalence[goal_b].get(f, 0.0))
            per_client[c][str(f)][0] += 1; per_client[c][str(f)][1] += int(f in B)
        famA = {fam_of[f] for f in A if f in fam_of}; famB = {fam_of[f] for f in B if f in fam_of}
        for fm in famA:
            fam_n[fm] += 1; fam_keep[fm] += fm in famB
        for slot, sa in by_diet[a].items():
            sb = by_diet[b].get(slot, set())
            if sb:
                slot_renewal[slot].append(1 - len(sa & sb) / len(sa))
            for f in sa:
                slot_n[slot] += 1; slot_keep[slot] += f in sb
                slot_food_n[(slot, f)] += 1; slot_food_keep[(slot, f)] += f in sb

    food_rows = []
    for f, n in food_n.items():
        p = food_keep[f] / n; ch = statistics.fmean(food_chance[f])
        food_rows.append({"food_id": f, "canonical_name": foods[f]["canonical_name"], "family": fam_of.get(f), "n": n, "persistence": round(p, 3),
                          "chance_prevalence_same_goal": round(ch, 3), "lift": round(p / ch, 2) if ch else None, "confidence": confidence(n), "class": classify(p, n)})
    food_rows.sort(key=lambda r: (-r["n"], -r["persistence"]))
    fam_rows = sorted(({"family": fm, "n": n, "persistence": round(fam_keep[fm] / n, 3), "confidence": confidence(n), "class": classify(fam_keep[fm] / n, n)}
                       for fm, n in fam_n.items()), key=lambda r: -r["n"])
    slot_rows = [{"slot": s, "n_food_occurrences": slot_n[s], "food_persistence": round(slot_keep[s] / slot_n[s], 3), "pairs_with_slot": len(slot_renewal[s]),
                  "renewal_dropped_mean": round(statistics.fmean(slot_renewal[s]), 3) if slot_renewal[s] else None, "renewal_dropped_p50": pct(slot_renewal[s], .5)}
                 for s in SLOT_ORDER if slot_n[s]]
    slot_food_rows = sorted(({"slot": s, "canonical_name": foods[f]["canonical_name"], "n": n, "persistence": round(slot_food_keep[(s, f)] / n, 3),
                              "confidence": confidence(n), "class": classify(slot_food_keep[(s, f)] / n, n)}
                             for (s, f), n in slot_food_n.items() if n >= 10), key=lambda r: (r["slot"], -r["n"]))
    classified = [r for r in food_rows if r["class"] != "no_concluyente"]
    summary = {"pairs": len(pairs), "clients": len(clients), "same_goal_pairs": same_goal_pairs, "excluded_pairs": dict(excluded_pairs),
               "version_gap_distribution": dict(sorted(Counter(g for *_, g in pairs).items())),
               "renewal_dropped_same_goal": {"n": len(dropped_same_goal), "mean": round(statistics.fmean(dropped_same_goal), 4), "p50": pct(dropped_same_goal, .5)},
               "renewal_dropped_goal_change": {"n": len(dropped_goal_change), "mean": round(statistics.fmean(dropped_goal_change), 4) if dropped_goal_change else None, "p50": pct(dropped_goal_change, .5)},
               "jaccard_consecutive_same_goal": {"mean": round(statistics.fmean(jac_same_goal), 4), "p50": pct(jac_same_goal, .5)},
               "renewal_dropped": {"mean": round(statistics.fmean(renewal_dropped), 4), "p10": pct(renewal_dropped, .1), "p25": pct(renewal_dropped, .25), "p50": pct(renewal_dropped, .5),
                                   "p75": pct(renewal_dropped, .75), "p90": pct(renewal_dropped, .9)},
               "renewal_new": {"mean": round(statistics.fmean(renewal_new), 4), "p50": pct(renewal_new, .5)},
               "jaccard_consecutive": {"mean": round(statistics.fmean(jac), 4), "p50": pct(jac, .5), "p10": pct(jac, .1), "p90": pct(jac, .9)},
               "foods_classified": len(classified), "anchors": sum(r["class"] == "ancla" for r in classified), "rotatory": sum(r["class"] == "rotatorio" for r in classified),
               "intermediate": sum(r["class"] == "intermedio" for r in classified), "foods_low_n": sum(r["class"] == "no_concluyente" for r in food_rows),
               "weighted_persistence": round(sum(food_keep.values()) / sum(food_n.values()), 4)}
    out = {"protocol": {"pairs": "consecutive versions of the same client (v series, templates excluded)", "anchor_threshold": ANCHOR, "rotatory_threshold": ROTATORY,
                        "confidence": "high n>=30, medium 10-29, low <10 (not classified)", "chance": "prevalence of the food among the diets of the same goal"},
           "summary": summary, "foods": food_rows, "families": fam_rows, "slots": slot_rows, "slot_foods": slot_food_rows,
           "per_client": {c: dict(v) for c, v in per_client.items()},
           "food_prevalence_same_goal": {str(f): round(statistics.fmean(v), 4) for f, v in food_chance.items()},
           "alternative_groups": alternative_groups}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    args.doc.write_text(render(out), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def render(out: dict) -> str:  # noqa: C901
    s = out["summary"]; L = []
    L.append("# Política de variación entre dietas sucesivas: análisis de rotación\n")
    L.append(f"Generado por `pipeline/rotation_analysis.py` sobre `dataset-v1` (E1 con marcas genericadas). Metodología idéntica a la de la constitución de "
             f"reglas: prevalencia (aquí persistencia), n y confianza. Fuente de datos: `_dataset/rotation_analysis.json`.\n")
    L.append("## 1. Protocolo\n")
    L.append(f"- Pares = versiones **consecutivas** del mismo cliente (serie `v`, ordenadas por número de versión; plantillas excluidas): **{s['pairs']} pares de {s['clients']} clientes**; "
             f"{s['same_goal_pairs']} pares mantienen el objetivo ({100*s['same_goal_pairs']/s['pairs']:.0f} %). Salto de versión: {s['version_gap_distribution']}. "
             f"Excluidos: {s['excluded_pairs']} (re-emisiones de la misma versión `vNN-2`, identificadores `vAAAA` con fecha en lugar de secuencia, dietas sin ítems mapeados).")
    L.append("- Persistencia de un alimento = P(aparece en v_{n+1} | apareció en v_n), con n = pares en los que aparecía en v_n. Persistencia esperada por azar = "
             "prevalencia del alimento entre las dietas del mismo objetivo; *lift* = persistencia / azar separa «ancla porque está en todas partes» de «se mantiene a propósito».")
    L.append(f"- Clasificación: **ancla** ≥ {ANCHOR:.2f} · **rotatorio** ≤ {ROTATORY:.2f} · intermedio entre ambos; confianza alta n ≥ 30, media 10–29, baja < 10 (no se clasifica).\n")
    L.append("## 2. Tasa de renovación global\n")
    r = s["renewal_dropped"]; j = s["jaccard_consecutive"]
    L.append(f"De una versión a la siguiente **desaparece de media el {100*r['mean']:.1f} % de los alimentos** (p10 {100*r['p10']:.0f} % · p25 {100*r['p25']:.0f} % · "
             f"**p50 {100*r['p50']:.0f} %** · p75 {100*r['p75']:.0f} % · p90 {100*r['p90']:.0f} %) y el {100*s['renewal_new']['mean']:.1f} % de los alimentos de la nueva versión son nuevos. "
             f"Jaccard entre versiones consecutivas: media **{j['mean']:.3f}** (p10 {j['p10']:.3f} · p50 {j['p50']:.3f} · p90 {j['p90']:.3f}). "
             f"Persistencia ponderada por ocurrencias: {100*s['weighted_persistence']:.1f} %.\n")
    sg, gc = s["renewal_dropped_same_goal"], s["renewal_dropped_goal_change"]
    L.append(f"Con el **mismo objetivo** en ambas versiones (n = {sg['n']}) desaparece el {100*sg['mean']:.1f} % (p50 {100*sg['p50']:.0f} %; Jaccard {s['jaccard_consecutive_same_goal']['mean']:.3f}); "
             f"cuando **cambia el objetivo** (n = {gc['n']}) desaparece el {100*(gc['mean'] or 0):.1f} % (p50 {100*(gc['p50'] or 0):.0f} %).\n")
    L.append(f"Alimentos con n ≥ 10: {s['foods_classified']} → **{s['anchors']} anclas**, **{s['rotatory']} rotatorios**, {s['intermediate']} intermedios "
             f"({s['foods_low_n']} alimentos con n < 10, no concluyentes).\n")
    L.append("## 3. Anclas y rotatorios por alimento (n ≥ 10)\n")
    L.append("| Alimento | familia | n | persistencia | azar (mismo obj.) | lift | confianza | clase |")
    L.append("|---|---|---|---|---|---|---|---|")
    rows = [x for x in out["foods"] if x["class"] != "no_concluyente"]
    for x in sorted(rows, key=lambda x: (-x["persistence"], -x["n"])):
        L.append(f"| {x['canonical_name']} | {x['family']} | {x['n']} | **{x['persistence']:.2f}** | {x['chance_prevalence_same_goal']:.2f} | {x['lift'] if x['lift'] is not None else '—'} | {x['confidence']} | {x['class']} |")
    L.append("")
    L.append("## 4. Por familia\n")
    L.append("| Familia | n | persistencia | confianza | clase |")
    L.append("|---|---|---|---|---|")
    for x in out["families"]:
        L.append(f"| {x['family']} | {x['n']} | {x['persistence']:.2f} | {x['confidence']} | {x['class']} |")
    L.append("")
    L.append("## 5. Por franja\n")
    L.append("| Franja | ocurrencias | persistencia del alimento en la franja | pares con la franja | renovación media (desaparecen) | renovación p50 |")
    L.append("|---|---|---|---|---|---|")
    for x in out["slots"]:
        rm = f"{100*x['renewal_dropped_mean']:.0f} %" if x['renewal_dropped_mean'] is not None else '—'
        rp = f"{100*x['renewal_dropped_p50']:.0f} %" if x['renewal_dropped_p50'] is not None else '—'
        L.append(f"| {x['slot']} | {x['n_food_occurrences']} | **{x['food_persistence']:.2f}** | {x['pairs_with_slot']} | {rm} | {rp} |")
    L.append("")
    L.append("### Alimentos por franja (n ≥ 10)\n")
    L.append("| Franja | Alimento | n | persistencia | confianza | clase |")
    L.append("|---|---|---|---|---|---|")
    for x in out["slot_foods"]:
        L.append(f"| {x['slot']} | {x['canonical_name']} | {x['n']} | {x['persistence']:.2f} | {x['confidence']} | {x['class']} |")
    L.append("")
    L.append("## 6. Lectura (generada desde los datos)\n")
    anchors = [x for x in out["foods"] if x["class"] == "ancla"]; rot = [x for x in out["foods"] if x["class"] == "rotatorio" and x["confidence"] == "high"]
    fam_anchor = [x for x in out["families"] if x["class"] == "ancla"]; fam_rot = [x for x in out["families"] if x["class"] == "rotatorio"]
    slots = sorted([x for x in out["slots"] if x["renewal_dropped_mean"] is not None and x["pairs_with_slot"] >= 30], key=lambda x: -x["renewal_dropped_mean"])
    L.append(f"- **Anclas** ({len(anchors)}): " + ", ".join(f"{x['canonical_name']} ({x['persistence']:.2f}, n={x['n']}, lift {x['lift']})" for x in sorted(anchors, key=lambda x: -x['n'])) + ".")
    high_lift = [x for x in anchors if x["lift"] and x["lift"] >= 1.15]
    L.append(f"  El *lift* separa dos tipos de ancla: las de lift ≈ 1 (arroz, pollo, AOVE…) persisten porque están en casi todas las dietas del objetivo —ubicuidad, no retención deliberada—; "
             f"las de lift claramente > 1 ({', '.join(f'{x[chr(99)+chr(97)+chr(110)+chr(111)+chr(110)+chr(105)+chr(99)+chr(97)+chr(108)+chr(95)+chr(110)+chr(97)+chr(109)+chr(101)]} {x[chr(108)+chr(105)+chr(102)+chr(116)]}' for x in high_lift) or 'ninguna'}) se mantienen más de lo que su prevalencia explica: retención deliberada.")
    L.append(f"- **Rotatorios con confianza alta** ({len(rot)}): " + ", ".join(f"{x['canonical_name']} ({x['persistence']:.2f}, n={x['n']})" for x in sorted(rot, key=lambda x: x['persistence'])[:25]) + (" …" if len(rot) > 25 else "") + ".")
    n_fam = len([x for x in out['families'] if x['class'] != 'no_concluyente'])
    L.append(f"- **La rotación es intra-familia**: {len(fam_anchor)} de {n_fam} familias clasificadas son ancla ({', '.join(x['family'] for x in fam_anchor[:8])}…) "
             f"mientras que la mayoría de los alimentos individuales rotan: el profesional mantiene la estructura (una proteína, una grasa, una verdura, un fruto seco) "
             f"y cambia la especie. Familias rotatorias: {', '.join(x['family'] for x in fam_rot) or 'ninguna'}. "
             f"**Matiz (sección 7):** la familia es la unidad que se conserva ENTRE versiones; DENTRO de una comida, lo que él ofrece como intercambiable "
             f"cruza familias en el {100*out['alternative_groups']['total']['mixed_family_share']:.0f} % de sus grupos de alternativas, así que la unidad de "
             f"intercambiabilidad para él es el papel en la comida, no la familia botánica.")
    cena = next(x['renewal_dropped_mean'] for x in out['slots'] if x['slot'] == 'CENA'); des = next(x['renewal_dropped_mean'] for x in out['slots'] if x['slot'] == 'DESAYUNO')
    L.append(f"- **Por franja** (franjas con ≥ 30 pares): renovación mayor en {slots[0]['slot']} ({100*slots[0]['renewal_dropped_mean']:.0f} %) y {slots[1]['slot']} ({100*slots[1]['renewal_dropped_mean']:.0f} %); "
             f"menor en {slots[-1]['slot']} ({100*slots[-1]['renewal_dropped_mean']:.0f} %). CENA {100*cena:.0f} % frente a DESAYUNO {100*des:.0f} %.")
    L.append("")
    ag = out["alternative_groups"]; t = ag["total"]
    L.append("## 7. Grupos de alternativas: la unidad de intercambiabilidad es el papel en la comida, no la familia\n")
    L.append(f"El plan asumía que las alternativas que el profesional escribe en una misma línea («150 gr pollo / 160 gr pavo / 180 gr lomo») pertenecen a la misma "
             f"familia. El corpus lo refuta: de **{t['groups']} grupos de alternativas** con ≥ 2 alimentos canónicos, **el {100*t['mixed_family_share']:.0f} % mezcla familias**; "
             f"de esos grupos mixtos, el {100*t['mixed_family_shared_macro_share']:.0f} % comparte al menos un macrogrupo del catálogo (grupo o grupo secundario: proteína, hidrato, grasa…), "
             f"es decir, son alternativas por **papel en la comida** (pollo o atún son intercambiables como proteína aunque sean ave y pescado); "
             f"solo el {100*t['no_common_macro_share']:.0f} % del total no comparte ningún macrogrupo. Consecuencias ya aplicadas: la política de rotación sustituye dentro de la familia "
             f"(un subconjunto conservador de lo que él considera intercambiable), y la envolvente de plausibilidad no exige «misma familia» sino la cuota por dieta de grupos sin "
             f"macrogrupo común, con el p95 de cada objetivo como límite (la envolvente de plausibilidad). Misma medida que en `pipeline/plausibility_envelope.py`.\n")
    L.append("| Objetivo | grupos | mezclan familias | de ellos, con macrogrupo común | sin macrogrupo común | confianza |")
    L.append("|---|---|---|---|---|---|")
    for x in ag["by_goal"] + [t]:
        name = "**todos**" if x["goal"] == "todos" else x["goal"]
        L.append(f"| {name} | {x['groups']} | {100*x['mixed_family_share']:.0f} % | {100*(x['mixed_family_shared_macro_share'] or 0):.0f} % | {100*x['no_common_macro_share']:.0f} % | {x['confidence']} |")
    L.append("")
    L.append("Pares de familias más frecuentes dentro de los grupos mixtos (n = grupos que contienen ambas; «macro común» = cuota de esos grupos cuyos miembros comparten un macrogrupo):\n")
    L.append("| Familia A | Familia B | n | macro común |")
    L.append("|---|---|---|---|")
    for x in ag["top_family_pairs"]:
        L.append(f"| {x['families'][0]} | {x['families'][1]} | {x['n']} | {100*x['shared_macro_share']:.0f} % |")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
