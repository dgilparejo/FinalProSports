# -*- coding: utf-8 -*-
"""
Phase 3b — Derived artefacts regenerated from the CLEAN diets (single source of truth).

Replaces the text-substituted copies of reglas.md / reglas_condiciones.md /
arquetipos.md / INDICE.md with artefacts recomputed on _dataset/diets.jsonl, so
that normalised goal labels, expanded meal slots and boilerplate-free notes are
consistent everywhere. Markdown reports are written in Spanish (language of the
thesis); code, file and field names are English.

Inputs:
  --diets   _dataset/diets.jsonl

Outputs (in --out-dir):
  rules.json / rules.md               every distinct note of the trainer with counts (no top-N cut)
  rules_conditions.json / .md         prevalence + lift by goal / sex / phase (phase from diet_version)
  archetypes.json / archetypes.md     sex x age_bucket x goal -> diets / clients
  INDEX.md                            master index with clean counts
  analyze_rules_log.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pii_common import load_records, require_file, write_json  # noqa: E402

# Rule patterns audited by the original condiciones.py (kept verbatim for comparability)
RULES = {
    "Ayuno >=16h": r"16\s*(a\s*17\s*)?horas|ayuno intermitente|16 h",
    "Carga de hidratos": r"carga de hidratos|carga de carbo|recarga",
    "Cetosis/keto": r"cetosis|cetog|keto",
    "Prohibido azucar/postres": r"no tomar postres|sin az[uú]car|azucares|evitar.*az[uú]car",
    "Sal del Himalaya": r"himalaya",
    "Soja prohibida": r"soja",
    "Chocolate negro (ansiedad)": r"chocolate negro|gelatina sin az",
    "Sustituir pescado/huevo por pollo": r"sustituir el pescado|sustituir el huevo|por pollo",
    "Agua ~2.5L": r"2[.,]5 litros|litros de agua|ingesta de agua",
    "Saltarse/2 comidas": r"saltarte 1 comida|dos comidas|2 comidas|saltar.*comida",
    "Alta en fibra": r"fibra",
    "Hidratos en cena (arroz/avena/patata)": None,
    "Fruta en cena": None,
    "Pre-entreno BCAAs/creatina": r"bcaa|glutamina|creatina|amilopectina|amino power",
}
CARB = re.compile(r"arroz|avena|patata|pan |boniato|quinoa|pasta|cereal")
FRUIT = re.compile(r"\b(pl[aá]tano|banana|manzana|kiwi|naranja|mandarina|pera|peras|fresa|fresas|ar[aá]ndano\w*|"
                   r"frambuesa\w*|uva\w*|mel[oó]n|sand[ií]a|pi[ñn]a|mango|melocot[oó]n|ciruela\w*|cereza\w*|higo\w*|"
                   r"frutos rojos|fruta)\b", re.I)


def phase_of(version):
    if version is None:
        return "sin_version"
    return "v1" if version == 1 else "v2-4" if version <= 4 else "v5+"


def has_in_meal(meals, slot_prefixes, rx):
    for slot, items in meals.items():
        if any(slot.upper().startswith(p) for p in slot_prefixes):
            if any(rx.search(it.lower()) for it in items):
                return True
    return False


def rule_matches(r, name, pat):
    if name == "Hidratos en cena (arroz/avena/patata)":
        return has_in_meal(r["meals"], ["CENA", "RECENA"], CARB)
    if name == "Fruta en cena":
        return has_in_meal(r["meals"], ["CENA", "RECENA"], FRUIT)
    return bool(re.search(pat, r["_blob"]))


def lift_block(sub, all_rows, dim, prev):
    gc = Counter(r[dim] for r in sub)
    allc = Counter(r[dim] for r in all_rows)
    out = {}
    for k, v in gc.most_common():
        p_in = v / allc[k] if allc[k] else 0
        out[str(k)] = {"n": v, "of": allc[k], "pct": round(100 * p_in, 1), "lift": round(p_in / prev, 2) if prev else None}
    return out


def fmt_lift(block):
    parts = []
    for k, v in block.items():
        tag = " 🔺" if v["lift"] is not None and v["lift"] >= 1.5 else (" 🔻" if v["lift"] is not None and v["lift"] <= 0.5 else "")
        parts.append(f"{k}: {v['n']}/{v['of']} ({v['pct']:.0f}%, lift {v['lift']}{tag})")
    return "; ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diets", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--min-tenure", type=int, default=5, help="min diets per client for the within-client phase analysis")
    args = ap.parse_args()
    out = args.out_dir
    rows = load_records(require_file(args.diets))
    N = len(rows)
    log = {}

    # ------------------------------------------------------------------ rules
    notes_counter, notes_diets, notes_goals = Counter(), Counter(), defaultdict(Counter)
    for r in rows:
        seen = set()
        for n in r["notes"]:
            key = re.sub(r"\s+", " ", n.lower()).strip()
            if not (5 < len(key) < 160):
                continue
            notes_counter[key] += 1
            notes_goals[key][r["meta"]["goal"]] += 1
            if key not in seen:
                notes_diets[key] += 1
                seen.add(key)
    rules = [{"note": k, "count": c, "diet_count": notes_diets[k], "goals": dict(notes_goals[k].most_common())}
             for k, c in notes_counter.most_common()]
    write_json(out / "rules.json", rules)
    log["distinct_notes"] = len(rules)
    log["notes_total"] = sum(notes_counter.values())

    goal_dist = Counter(r["meta"]["goal"] for r in rows)
    inferred = sum(1 for r in rows if r["meta"]["goal_inferred"])
    # NOTE: the legacy food vocabulary (_meta/vocabulario_alimentos.json) is NOT copied any more:
    # 46 % of its entries were corrupt (food[:30] truncation, preposition capture). The food
    # catalogue is rebuilt from scratch by pipeline/src/pipeline/build_food_catalog.py (E1).

    L = ["# Reglas inferidas (ingeniería inversa) — corpus saneado\n",
         f"_Dietas analizadas: {N} (tras excluir vacías y duplicadas). Objetivo inferido por heurística en {inferred} ({100*inferred/N:.1f} %)._\n",
         "\n## Distribución de objetivos (etiquetas normalizadas)\n"]
    for g, c in goal_dist.most_common():
        L.append(f"- **{g}**: {c}")
    L.append(f"\n## Notas/reglas del preparador (texto literal, {len(rules)} distintas, sin pie de firma)\n")
    for rr in rules:
        L.append(f"- ({rr['count']}x) {rr['note']}")
    (out / "rules.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ------------------------------------------------------------ conditions
    for r in rows:
        m = r["meta"]
        r["_goal"], r["_sex"], r["_phase"] = m["goal"], m["sex"], phase_of(m["diet_version"])
        r["_blob"] = (m.get("goal_text", "") + " \n" + " \n".join(" ".join(v) for v in r["meals"].values()) + " \n" + " ".join(r["notes"])).lower()
    diets_per_client = Counter(r["meta"]["client_code"] for r in rows)
    tenured = [r for r in rows if diets_per_client[r["meta"]["client_code"]] >= args.min_tenure and r["_phase"] != "sin_version"]
    phase_clients = {ph: len({r["meta"]["client_code"] for r in rows if r["_phase"] == ph}) for ph in ("v1", "v2-4", "v5+", "sin_version")}
    phase_tenured_share = {ph: round(100 * sum(1 for r in rows if r["_phase"] == ph and diets_per_client[r["meta"]["client_code"]] >= args.min_tenure)
                                     / max(1, sum(1 for r in rows if r["_phase"] == ph)), 1) for ph in ("v1", "v2-4", "v5+", "sin_version")}
    conditions = []
    C = ["# Ingeniería inversa CONDICIONAL: cuándo se aplica cada regla (corpus saneado)\n",
         f"_Base: {N} dietas limpias. Fase derivada de `diet_version` (v1 / v2-4 / v5+ / sin_version), no del nombre de fichero._\n",
         f"_Clientes distintos por fase: {phase_clients}. Porcentaje de dietas de cada fase que pertenecen a clientes con ≥{args.min_tenure} dietas: {phase_tenured_share} — "
         f"la fase está confundida con la permanencia del cliente, por eso se añade un análisis intra-cliente (solo clientes con ≥{args.min_tenure} dietas, {len(tenured)} dietas)._\n",
         "Para cada regla: nº dietas, % del total y desglose por objetivo/sexo/fase con **lift** = prevalencia en el grupo / prevalencia global. lift ≥ 1.5 = condición fuerte 🔺, ≤ 0.5 = 🔻.\n"]
    for name, pat in RULES.items():
        sub = [r for r in rows if rule_matches(r, name, pat)]
        prev = len(sub) / N
        entry = {"rule": name, "diets": len(sub), "pct": round(100 * prev, 1)}
        C.append(f"\n## {name}")
        if not sub:
            C.append("- 0 dietas (revisar patrón)")
            conditions.append(entry)
            continue
        C.append(f"- Aparece en **{len(sub)} dietas ({round(100*prev)} %)**")
        for dim, label in (("_goal", "objetivo"), ("_sex", "sexo"), ("_phase", "fase")):
            block = lift_block(sub, rows, dim, prev)
            entry[f"by_{label}"] = block
            C.append(f"  - por **{label}**: {fmt_lift(block)}")
        # within-client phase analysis
        sub_t = [r for r in tenured if rule_matches(r, name, pat)]
        prev_t = len(sub_t) / len(tenured) if tenured else 0
        block_t = lift_block(sub_t, tenured, "_phase", prev_t) if sub_t else {}
        entry["by_fase_intra_cliente"] = block_t
        C.append(f"  - por **fase, solo clientes con ≥{args.min_tenure} dietas** ({len(sub_t)}/{len(tenured)}): {fmt_lift(block_t) if block_t else '0 dietas'}")
        conditions.append(entry)
    write_json(out / "rules_conditions.json", {"base": N, "phase_clients": phase_clients, "phase_tenured_share_pct": phase_tenured_share,
                                               "tenured_diets": len(tenured), "min_tenure": args.min_tenure, "rules": conditions})
    (out / "rules_conditions.md").write_text("\n".join(C) + "\n", encoding="utf-8", newline="\n")

    # ------------------------------------------------------------ archetypes
    arq = defaultdict(list)
    for r in rows:
        m = r["meta"]
        arq[(m["sex"], m["age_bucket"], m["goal"])].append(m["client_code"])
    arch = [{"sex": k[0], "age_bucket": k[1], "goal": k[2], "diet_count": len(v), "client_count": len(set(v)), "clients": sorted(set(v))}
            for k, v in sorted(arq.items(), key=lambda kv: -len(kv[1]))]
    write_json(out / "archetypes.json", arch)
    A = ["# Arquetipos (perfil-tipo → patrón de dieta) — corpus saneado\n",
         "Agrupación basada en reglas: sexo × rango de edad × objetivo principal (etiquetas normalizadas).\n"]
    for a in arch:
        if a["diet_count"] < 2:
            continue
        A.append(f"\n## {a['sex']} | {a['age_bucket']} | {a['goal']}  ({a['diet_count']} dietas, {a['client_count']} clientes)")
        A.append("Clientes: " + ", ".join(a["clients"][:15]) + ("..." if a["client_count"] > 15 else ""))
    (out / "archetypes.md").write_text("\n".join(A) + "\n", encoding="utf-8", newline="\n")
    log["archetypes_total"] = len(arch)
    log["archetypes_ge2"] = sum(1 for a in arch if a["diet_count"] >= 2)

    # ----------------------------------------------------------------- index
    n_clients = len({r["meta"]["client_code"] for r in rows})
    I = ["# ÍNDICE MAESTRO — Corpus TFM Dietas (anonimizado y saneado)\n",
         f"- Clientes con dietas: **{n_clients}** | Dietas limpias: **{N}** | Comidas: **{sum(len(r['meals']) for r in rows)}** | Arquetipos con ≥2 dietas: **{log['archetypes_ge2']}**\n",
         "## Artefactos (`_dataset/`)\n",
         "- `diets.jsonl` — una dieta por línea: `id`, `text` (listo para embeber), `meta`, `meals`, `notes`",
         "- `meals.jsonl` — una comida por línea (`<id_dieta>::<FRANJA>`), regenerado desde `diets.jsonl`",
         "- `profiles.jsonl` — perfiles con esquema uniforme (datos de salud solo como booleanos)",
         "- `rules.json` / `rules.md` — notas del preparador agregadas (todas, sin corte)",
         "- `rules_conditions.json` / `.md` — prevalencia y lift por objetivo / sexo / fase",
         "- `archetypes.json` / `.md` — perfiles-tipo",
         "- `foods.json` — catálogo canónico de alimentos (E1, `pipeline/src/pipeline/`); el vocabulario heredado se descartó",
         "- `discarded_empty.jsonl`, `duplicates.json` — trazabilidad de exclusiones",
         "- `_private/` — mapeos e historias clínicas; **fuera del índice vectorial**",
         "\n## Distribución por objetivo principal\n"]
    for g, c in goal_dist.most_common():
        I.append(f"- {g}: {c}")
    I.append(f"\n_Objetivo inferido por heurística (`goal_inferred = true`): {inferred} dietas ({100*inferred/N:.1f} %)._")
    (out / "INDEX.md").write_text("\n".join(I) + "\n", encoding="utf-8", newline="\n")

    log.update({"diets": N, "clients": n_clients, "goal_distribution": dict(goal_dist.most_common()), "goal_inferred": inferred,
                "phase_clients": phase_clients, "phase_tenured_share_pct": phase_tenured_share, "tenured_diets": len(tenured)})
    write_json(out / "analyze_rules_log.json", log)
    print(json.dumps(log, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
