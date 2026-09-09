# -*- coding: utf-8 -*-
"""
E1.5 / evaluation design — Discriminative power of the representation, human ceiling, floors and normalised score.

Reframing (data owner): the ceiling of any overlap metric is the professional's SELF-CONSISTENCY — how much
two diets he wrote for the SAME client agree. No system can exceed it. Every overlap metric is therefore reported as a
triplet floor / system / ceiling plus the normalised score

    normalised = (system - floor) / (ceiling - floor)

Protocol (all measures): 1.033 clean diets minus the 31 template diets; queries = diets of clients with >= 3 diets;
"same client" (ceiling) = mean over the other diets of the client EXCLUDING the nearest neighbour (the near-identical
consecutive version); "different clients" (floor) = mean over K random diets of other clients (seed 42).

Measures
  1. Whole-diet Jaccard at four granularities: food_text, normalized_key, food_id, family.
  2. Per-slot Jaccard (mean over the query's slots; a slot absent in the other diet scores 0), normalized_key and food_id.
  3. Structure: number of slots (MAE), slot-set F1, items per slot (MAE), placement agreement (carbs in the first half of
     the day, fruit absent at dinner) — independent of catalogue granularity.
  4. Rule compliance: (a) all constraint rules (own diet vs random other-client diet evaluated with the query profile's
     rules); (b) CONDITIONAL rules only, floor = random diet of a client with a DIFFERENT goal.

Output: _dataset/discriminative_power.json + tables on stdout.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR  # noqa: E402

FIRST_HALF = {"DESAYUNO", "MEDIA MAÑANA", "ALMUERZO", "COMIDA", "MERIENDA"}
CARB_GOALS = {"volumen_masa", "descarga_carga", "mantenimiento", "hipocalorica"}
NO_CARB_GOALS = {"cetosis_keto", "ayuno_intermitente"}
GLOBAL_RULES = ["prohibido_azucar_procesados", "hidratos_primera_mitad_dia", "fruta_no_en_cena", "cena_proteina_verdura",
                "desayuno_avena_cereales", "soja_prohibida"]


def load_jsonl(p: Path):
    if not p.exists():
        raise FileNotFoundError(f"Required input file not found: {p}")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def r4(x):
    return None if x is None else round(x, 4)


def normalised(system, floor, ceiling):
    if system is None or floor is None or ceiling is None or ceiling == floor:
        return None
    return round((system - floor) / (ceiling - floor), 3)


# ------------------------------------------------------------------ rules
def conditional_rules_for(goal: str) -> list[str]:
    rules = []
    if goal in NO_CARB_GOALS:
        rules.append("sin_hidratos_cena")
    if goal in CARB_GOALS:
        rules.append("hidratos_en_cena")
    if goal == "volumen_masa":
        rules.append("suplementacion_pre_post")
    if goal == "cetosis_keto":
        rules.append("sal_himalaya")
    return rules


def rules_for(goal: str) -> list[str]:
    return GLOBAL_RULES + conditional_rules_for(goal)


def evaluate(rule: str, d: dict):
    slots = d["slots"]
    items = [it for its in slots.values() for it in its]
    cena = slots.get("CENA", [])
    if rule == "prohibido_azucar_procesados":
        return not any(it["flags"]["is_processed_sugar"] or it["flags"]["is_soft_drink"] for it in items)
    if rule == "soja_prohibida":
        return not any(it["flags"]["contains_soy"] for it in items)
    if rule == "hidratos_primera_mitad_dia":
        carb_slots = {s for s, its in slots.items() if any(it["group"] == "CARB" for it in its)}
        return bool(carb_slots & FIRST_HALF) if carb_slots else None
    if rule in ("fruta_no_en_cena", "cena_proteina_verdura", "sin_hidratos_cena", "hidratos_en_cena"):
        if not cena:
            return None
        groups = {it["group"] for it in cena}
        if rule == "fruta_no_en_cena":
            return "FRUIT" not in groups
        if rule == "cena_proteina_verdura":
            return "PROTEIN" in groups and "VEGETABLE" in groups
        if rule == "sin_hidratos_cena":
            return "CARB" not in groups
        return "CARB" in groups
    if rule == "desayuno_avena_cereales":
        des = slots.get("DESAYUNO")
        return any(it["family"] == "cereal" for it in des) if des else None
    if rule == "suplementacion_pre_post":
        pre = slots.get("ANTES DE ENTRENAR", []) + slots.get("DESPUES DE ENTRENAR", [])
        return any(it["group"] == "SUPPLEMENT" for it in pre) if pre else None
    if rule == "sal_himalaya":
        names = {it["canonical"] for it in items}
        if "sal" not in names and "sal del himalaya" not in names:
            return None
        return "sal del himalaya" in names
    raise KeyError(rule)


def compliance(diet: dict, rules: list[str]):
    res = [evaluate(r, diet) for r in rules]
    res = [r for r in res if r is not None]
    return (sum(res) / len(res), len(res)) if res else (None, 0)


# ------------------------------------------------------------------ structure
def slot_f1(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    tp = len(a & b)
    if tp == 0:
        return 0.0
    p, r = tp / len(b), tp / len(a)
    return 2 * p * r / (p + r)


def placement(d: dict) -> tuple[bool | None, bool | None]:
    slots = d["slots"]
    carb_slots = {s for s, its in slots.items() if any(it["group"] == "CARB" for it in its)}
    carbs_first_half = bool(carb_slots & FIRST_HALF) if carb_slots else None
    cena = slots.get("CENA")
    fruit_absent_dinner = (not any(it["group"] == "FRUIT" for it in cena)) if cena else None
    return carbs_first_half, fruit_absent_dinner


def structure_sim(q: dict, o: dict) -> dict:
    qs, os_ = set(q["slot_counts"]), set(o["slot_counts"])
    common = qs & os_
    items_mae = mean(abs(q["slot_counts"][s] - o["slot_counts"][s]) for s in common) if common else None
    pq, po = q["placement"], o["placement"]
    agree = [pq[i] == po[i] for i in range(2) if pq[i] is not None and po[i] is not None]
    return {"n_slots_mae": abs(len(qs) - len(os_)), "slot_f1": slot_f1(qs, os_), "items_per_slot_mae": items_mae,
            "placement_agreement": (sum(agree) / len(agree)) if agree else None}


def per_slot_jaccard(q_slots: dict, o_slots: dict) -> float:
    if not q_slots:
        return 0.0
    return mean(jaccard(q_slots[s], o_slots.get(s, set())) for s in q_slots) or 0.0


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "discriminative_power.json")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    diets = {d["id"]: d for d in load_jsonl(DATASET_DIR / "diets.jsonl")}
    items = load_jsonl(DATASET_DIR / "diet_items.jsonl")
    foods = {f["id"]: f for f in json.loads((DATASET_DIR / "foods.json").read_text(encoding="utf-8"))["foods"]}

    excluded_tpl = {i for i, d in diets.items() if d["meta"].get("template_group_id")}
    keep = [i for i in diets if i not in excluded_tpl]
    by_client = defaultdict(list)
    for i in keep:
        by_client[diets[i]["meta"]["client_code"]].append(i)

    sets = {g: defaultdict(set) for g in ("food_text", "normalized_key", "food_id", "family")}
    slot_sets = {g: defaultdict(lambda: defaultdict(set)) for g in ("normalized_key", "food_id")}
    struct = {i: {"slots": defaultdict(list), "goal": diets[i]["meta"]["goal"], "slot_counts": defaultdict(int)} for i in keep}
    for it in items:
        i = it["diet_id"]
        if i not in struct:
            continue
        struct[i]["slot_counts"][it["meal_slot"]] += 1
        sets["food_text"][i].add(it["food_text"].lower().strip())
        if it["normalized_key"]:
            sets["normalized_key"][i].add(it["normalized_key"])
            slot_sets["normalized_key"][i][it["meal_slot"]].add(it["normalized_key"])
        if it["food_id"] is not None:
            sets["food_id"][i].add(it["food_id"])
            sets["family"][i].add(it["family"])
            slot_sets["food_id"][i][it["meal_slot"]].add(it["food_id"])
            f = foods[it["food_id"]]
            struct[i]["slots"][it["meal_slot"]].append({"group": f["group"], "family": f["family"], "flags": f["flags"], "canonical": f["canonical_name"]})
    for i in keep:
        struct[i]["placement"] = placement(struct[i])

    queries = [i for i in keep if len(by_client[diets[i]["meta"]["client_code"]]) >= 3]
    others_of = {c: [j for j in keep if diets[j]["meta"]["client_code"] != c] for c in by_client}
    samples = {i: rng.sample(others_of[diets[i]["meta"]["client_code"]], min(args.k, len(others_of[diets[i]["meta"]["client_code"]]))) for i in queries}

    def same_others(i):
        c = diets[i]["meta"]["client_code"]
        return [j for j in by_client[c] if j != i]

    def ceiling_floor(score_fn, i):
        """mean over same-client diets excluding the nearest neighbour (max score), mean over random other clients."""
        same = sorted((score_fn(i, j) for j in same_others(i)), reverse=True)
        return mean(same[1:]), mean(same), mean(score_fn(i, j) for j in samples[i])

    results = {"protocol": {"diets_clean": len(diets), "template_diets_excluded": len(excluded_tpl), "diets_used": len(keep),
                            "clients_used": len(by_client), "queries_same_client_ge3": len(queries), "k_random_other_clients": args.k, "seed": args.seed,
                            "ceiling": "mean Jaccard with the other diets of the same client, nearest neighbour excluded",
                            "floor": "mean Jaccard with K random diets of other clients",
                            "normalised_score": "(system - floor) / (ceiling - floor); the ceiling is the professional's self-consistency"},
               "overlap_whole_diet": {}, "overlap_per_slot": {}, "structure": {}, "rule_compliance": {}}

    # 1. whole-diet
    for gran, S in sets.items():
        c, c_nn, f = [], [], []
        for i in queries:
            a, b, d = ceiling_floor(lambda x, y: jaccard(S[x], S[y]), i)
            c.append(a); c_nn.append(b); f.append(d)
        results["overlap_whole_diet"][gran] = {
            "classes": len({x for s in S.values() for x in s}),
            "floor_different_clients": r4(mean(f)), "ceiling_same_client": r4(mean(c)), "ceiling_including_nearest_neighbour": r4(mean(c_nn)),
            "ratio": round(mean(c) / mean(f), 2), "ratio_including_nn": round(mean(c_nn) / mean(f), 2),
            "example_normalised_score_for_system_0_19": normalised(0.19, mean(f), mean(c)) if gran == "food_text" else None}
    # 2. per slot
    for gran, SS in slot_sets.items():
        c, f = [], []
        for i in queries:
            a, _, d = ceiling_floor(lambda x, y: per_slot_jaccard(SS[x], SS[y]), i)
            c.append(a); f.append(d)
        per_slot = {}
        for slot in ("DESAYUNO", "MEDIA MAÑANA", "COMIDA", "MERIENDA", "CENA", "ANTES DE ENTRENAR", "DESPUES DE ENTRENAR"):
            cs, fs = [], []
            for i in queries:
                if slot not in SS[i]:
                    continue
                same = sorted((jaccard(SS[i][slot], SS[j].get(slot, set())) for j in same_others(i)), reverse=True)
                cs.append(mean(same[1:])); fs.append(mean(jaccard(SS[i][slot], SS[j].get(slot, set())) for j in samples[i]))
            if cs:
                per_slot[slot] = {"queries": len(cs), "floor": r4(mean(fs)), "ceiling": r4(mean(cs)), "ratio": round(mean(cs) / mean(fs), 2) if mean(fs) else None}
        results["overlap_per_slot"][gran] = {"floor_different_clients": r4(mean(f)), "ceiling_same_client": r4(mean(c)),
                                             "ratio": round(mean(c) / mean(f), 2), "by_slot": per_slot}
    # 3. structure
    keys = ("n_slots_mae", "slot_f1", "items_per_slot_mae", "placement_agreement")
    acc_c, acc_f = {k: [] for k in keys}, {k: [] for k in keys}
    for i in queries:
        same = [structure_sim(struct[i], struct[j]) for j in same_others(i)]
        # nearest neighbour = highest slot_f1 with lowest items MAE
        same.sort(key=lambda s: (-(s["slot_f1"]), s["items_per_slot_mae"] if s["items_per_slot_mae"] is not None else 99))
        same = same[1:]
        diff = [structure_sim(struct[i], struct[j]) for j in samples[i]]
        for k in keys:
            acc_c[k].append(mean(s[k] for s in same)); acc_f[k].append(mean(s[k] for s in diff))
    for k in keys:
        c, f = mean(acc_c[k]), mean(acc_f[k])
        results["structure"][k] = {"ceiling_same_client": r4(c), "floor_different_clients": r4(f),
                                   "direction": "higher is better" if k in ("slot_f1", "placement_agreement") else "lower is better"}
    # 4. rules
    own_all, rnd_all, own_cond, rnd_cond_other_goal, rnd_cond_same_goal, n_cond = [], [], [], [], [], []
    for i in keep:
        goal = struct[i]["goal"]
        c_own, _ = compliance(struct[i], rules_for(goal))
        c = diets[i]["meta"]["client_code"]
        others = others_of[c]
        if c_own is not None:
            own_all.append(c_own)
            vals = [compliance(struct[j], rules_for(goal))[0] for j in rng.sample(others, min(20, len(others)))]
            rnd_all.append(mean(vals))
        cond = conditional_rules_for(goal)
        if cond:
            c_c, n = compliance(struct[i], cond)
            if c_c is not None:
                own_cond.append(c_c); n_cond.append(n)
                other_goal = [j for j in others if struct[j]["goal"] != goal]
                vals = [compliance(struct[j], cond)[0] for j in rng.sample(other_goal, min(20, len(other_goal)))]
                rnd_cond_other_goal.append(mean(vals))
                same_goal = [j for j in others if struct[j]["goal"] == goal]
                if same_goal:
                    vals = [compliance(struct[j], cond)[0] for j in rng.sample(same_goal, min(20, len(same_goal)))]
                    rnd_cond_same_goal.append(mean(vals))
    results["rule_compliance"] = {
        "all_constraint_rules": {"rules": GLOBAL_RULES + ["sin_hidratos_cena", "hidratos_en_cena", "suplementacion_pre_post", "sal_himalaya"],
                                 "diets": len(own_all), "own_diet": r4(mean(own_all)), "random_other_client_same_rules": r4(mean(rnd_all)),
                                 "ratio": round(mean(own_all) / mean(rnd_all), 2), "points": round(100 * (mean(own_all) - mean(rnd_all)), 1)},
        "conditional_rules_only": {"rules": ["sin_hidratos_cena (cetosis/ayuno)", "hidratos_en_cena (volumen/descarga/mant/hipo)", "suplementacion_pre_post (volumen)", "sal_himalaya (cetosis)"],
                                   "diets_with_applicable_conditional_rules": len(own_cond), "mean_applicable": r4(mean(n_cond)),
                                   "own_diet": r4(mean(own_cond)), "floor_random_diet_of_DIFFERENT_goal": r4(mean(rnd_cond_other_goal)),
                                   "random_diet_of_same_goal": r4(mean(rnd_cond_same_goal)),
                                   "ratio_vs_different_goal": round(mean(own_cond) / mean(rnd_cond_other_goal), 2) if mean(rnd_cond_other_goal) else None,
                                   "points_vs_different_goal": round(100 * (mean(own_cond) - mean(rnd_cond_other_goal)), 1)},
    }
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    print(json.dumps(results["protocol"], ensure_ascii=False))
    print(f"\n{'whole-diet Jaccard':18s} {'classes':>8s} {'floor':>7s} {'ceiling':>8s} {'ratio':>6s} {'ceil(NN)':>9s}")
    for g, v in results["overlap_whole_diet"].items():
        print(f"{g:18s} {v['classes']:8d} {v['floor_different_clients']:7.3f} {v['ceiling_same_client']:8.3f} {v['ratio']:6.2f} {v['ceiling_including_nearest_neighbour']:9.3f}")
    print(f"\n{'per-slot Jaccard':18s} {'floor':>7s} {'ceiling':>8s} {'ratio':>6s}")
    for g, v in results["overlap_per_slot"].items():
        print(f"{g:18s} {v['floor_different_clients']:7.3f} {v['ceiling_same_client']:8.3f} {v['ratio']:6.2f}")
        for s, sv in v["by_slot"].items():
            print(f"   {s:20s} n={sv['queries']:4d} floor {sv['floor']:.3f} ceiling {sv['ceiling']:.3f} ratio {sv['ratio']}")
    print("\nstructure:", json.dumps(results["structure"], ensure_ascii=False))
    print("\nrules:", json.dumps(results["rule_compliance"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
