# -*- coding: utf-8 -*-
"""Deriva del corpus PRIVADO los parámetros gruesos con los que se genera la base de casos sintética.

Se ejecuta UNA VEZ, en la máquina del titular, y su salida (`synthetic_params.json`, unas decenas de KB) es lo único
de este paso que viaja al repositorio público. Lo que sale son DISTRIBUCIONES, no filas: cuántos hombres y mujeres,
qué tramos de edad, qué altura media, qué objetivos, qué franjas usa cada objetivo, qué alimentos aparecen en cada
franja y cuántas veces, cuántas lecturas de báscula tiene la gente, qué marcadores de laboratorio existen y en qué
rango se mueven.

**CELDA MÍNIMA 10.** Ninguna combinación con menos de diez observaciones sale del script: una celda de una persona es
esa persona. El corte se aplica a cada tabla y lo que no llega se agrega al nivel de arriba o se descarta. Es el mismo
criterio (`min_n = 10`) con el que ya se minó la envolvente de plausibilidad, y por eso las dos casan.

Lo que NO sale, ni agregado ni transformado:
  * ningún texto libre del corpus (gustos, aversiones, vicios, deporte, horarios, logros, notas de dieta): el generador
    compone esos campos con el catálogo público y un vocabulario inventado, no con las palabras de nadie;
  * ninguna fecha real: solo el NÚMERO de lecturas y el hueco típico entre ellas;
  * ningún seudónimo, ninguna medida individual.

Uso (una vez):
  python pipeline/src/data_tools/derive_synthetic_params.py --dataset $FPS_DATASET_DIR --out seed/dataset_public/synthetic_params.json
"""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

MIN_CELL = 10
# Los cuatro objetivos que el motor puede servir (neighbourhood_policy, medido sobre dataset-v3). Los demás se
# descartan aquí y no en el generador: si un objetivo no es servible, generar casos suyos solo produce pantallas 422.
SERVABLE = ("definicion_grasa", "volumen_masa", "ayuno_intermitente", "cetosis_keto")
PSEUDONYM = re.compile(r"CLIENTE_\d+")


def jl(path: Path):
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def shares(counter: Counter, min_cell: int = MIN_CELL) -> dict:
    """Proporciones, tirando las celdas por debajo del mínimo y renormalizando lo que queda."""
    kept = {str(k): n for k, n in counter.items() if n >= min_cell and k is not None}
    total = sum(kept.values())
    return {k: round(n / total, 4) for k, n in sorted(kept.items(), key=lambda kv: -kv[1])} if total else {}


def spread(values: list[float]) -> dict | None:
    vals = [float(v) for v in values if v is not None]
    if len(vals) < MIN_CELL:
        return None
    vals.sort()
    q = lambda p: round(vals[min(len(vals) - 1, int(p * (len(vals) - 1)))], 2)
    return {"n": len(vals), "mean": round(st.fmean(vals), 2), "sd": round(st.pstdev(vals), 2) if len(vals) > 1 else 0.0,
            "p05": q(0.05), "p50": q(0.50), "p95": q(0.95), "min": vals[0], "max": vals[-1]}


def derive(dataset: Path) -> dict:
    perfiles = list(jl(dataset / "profiles.jsonl"))
    dietas = list(jl(dataset / "diets.jsonl"))
    comidas = list(jl(dataset / "meals.jsonl"))
    items = list(jl(dataset / "diet_items.jsonl"))
    bascula = list(jl(dataset / "body_measurements.jsonl"))
    labs = list(jl(dataset / "lab_results.jsonl"))
    foods = json.loads((dataset / "foods.json").read_text(encoding="utf-8"))["foods"]
    fam_of = {f["id"]: f["family"] for f in foods}

    out: dict = {
        "source": {"dataset": dataset.name, "min_cell": MIN_CELL, "servable_goals": list(SERVABLE),
                   "profiles": len(perfiles), "diets": len(dietas), "components": len(items),
                   "note": ("Distribuciones gruesas, celda mínima 10. Ni una fila por persona, ni una fecha real, ni "
                            "una palabra del texto libre del corpus. Ver derive_synthetic_params.py.")},
        "derived": {}, "modelled": {},
    }
    D = out["derived"]

    # --- 1 · demografía
    D["sex"] = shares(Counter(p.get("sex") for p in perfiles))
    D["age_bucket"] = shares(Counter(p.get("age_bucket") for p in perfiles))
    edades = defaultdict(list)
    for p in perfiles:
        if p.get("age_bucket") and p.get("age") is not None:
            edades[p["age_bucket"]].append(p["age"])
    D["age_in_bucket"] = {b: s for b, v in edades.items() if (s := spread(v))}
    D["height_cm_by_sex"] = {s: sp for s in ("M", "F")
                             if (sp := spread([p.get("height_cm") for p in perfiles if p.get("sex") == s]))}
    D["activity_level"] = shares(Counter(p.get("activity_level") for p in perfiles))
    D["is_athlete_share"] = round(sum(1 for p in perfiles if p.get("is_athlete")) / len(perfiles), 4)
    D["body_type"] = shares(Counter(p.get("body_type") for p in perfiles))
    D["health_flags_share"] = {k: round(sum(1 for p in perfiles if p.get(k)) / len(perfiles), 4)
                               for k in ("has_allergies", "has_intolerances", "has_medical_restrictions")}
    D["diets_per_client"] = shares(Counter(min(int(p.get("diet_count") or 0), 8) for p in perfiles), min_cell=MIN_CELL)

    # --- 2 · objetivos y estructura por objetivo
    D["goal_mix"] = shares(Counter(d["meta"].get("goal") for d in dietas if d["meta"].get("goal") in SERVABLE))
    slots_por_dieta = defaultdict(list)
    slots_usados = defaultdict(Counter)
    for d in dietas:
        goal = d["meta"].get("goal")
        if goal not in SERVABLE:
            continue
        slots = [s for s in (d.get("meals") or ()) if s != "OTHER"]      # OTHER es dato, no franja componible
        slots_por_dieta[goal].append(len(slots))
        for s in slots:
            slots_usados[goal][s] += 1
    D["slots_per_diet_by_goal"] = {g: sp for g, v in slots_por_dieta.items() if (sp := spread(v))}
    D["slot_mix_by_goal"] = {g: shares(c) for g, c in slots_usados.items() if shares(c)}

    # --- 3 · ítems por (objetivo, franja) y alimentos por (objetivo, franja)
    por_dieta_goal = {d["id"]: d["meta"].get("goal") for d in dietas}
    n_items = defaultdict(list)
    for m in comidas:
        meta = m["meta"]
        g = por_dieta_goal.get(meta.get("diet_id"))
        if g in SERVABLE and meta.get("meal_slot") != "OTHER":
            n_items[(g, meta["meal_slot"])].append(meta.get("item_count") or 0)
    D["items_per_slot_by_goal"] = {f"{g}|{s}": sp for (g, s), v in n_items.items() if (sp := spread(v))}

    comida_de = defaultdict(Counter)     # (goal, slot) -> food_id -> nº de dietas distintas que lo usan ahí
    vistos = defaultdict(set)
    fam_de = defaultdict(Counter)
    for i in items:
        g, s, fid = por_dieta_goal.get(i.get("diet_id")), i.get("meal_slot"), i.get("food_id")
        if g not in SERVABLE or not s or s == "OTHER" or fid is None:
            continue
        clave = (g, s)
        if (i["diet_id"], fid) not in vistos[clave]:
            vistos[clave].add((i["diet_id"], fid))
            comida_de[clave][fid] += 1
            if fam_of.get(fid):
                fam_de[clave][fam_of[fid]] += 1
    D["foods_by_goal_slot"] = {f"{g}|{s}": {str(k): n for k, n in c.items() if n >= MIN_CELL}
                               for (g, s), c in comida_de.items() if any(n >= MIN_CELL for n in c.values())}
    D["families_by_goal_slot"] = {f"{g}|{s}": shares(c) for (g, s), c in fam_de.items() if shares(c)}
    # respaldo global por franja, para las celdas que no llegan al mínimo
    global_slot = defaultdict(Counter)
    for i in items:
        if i.get("meal_slot") and i["meal_slot"] != "OTHER" and i.get("food_id") is not None:
            global_slot[i["meal_slot"]][i["food_id"]] += 1
    D["foods_by_slot_fallback"] = {s: {str(k): n for k, n in c.items() if n >= MIN_CELL} for s, c in global_slot.items()}

    # --- 4 · grupos de alternativas y notas
    tam = Counter()
    grupos = defaultdict(int)
    for i in items:
        if i.get("alternative_group"):
            grupos[(i["diet_id"], i["meal_slot"], i["alternative_group"])] += 1
    for n in grupos.values():
        tam[min(n, 12)] += 1
    D["alternative_group_size"] = shares(tam)
    D["items_in_a_group_share"] = round(sum(1 for i in items if i.get("alternative_group")) / len(items), 4)
    D["notes_per_diet"] = spread([len(d.get("notes") or ()) for d in dietas])

    # --- 5 · báscula: cuántas lecturas y con qué hueco, y en qué rango se mueven peso y grasa
    por_cliente = defaultdict(list)
    for r in bascula:
        if r.get("client_code") and r.get("date"):
            por_cliente[r["client_code"]].append(r)
    D["scale"] = {
        "clients_with_scale_share": round(len(por_cliente) / len(perfiles), 4),
        "readings_per_client": spread([len(v) for v in por_cliente.values()]),
        "days_between_readings": spread([
            abs((date.fromisoformat(str(a["date"])[:10]) - date.fromisoformat(str(b["date"])[:10])).days)
            for v in por_cliente.values() for a, b in zip(sorted(v, key=lambda r: str(r["date"]))[1:], sorted(v, key=lambda r: str(r["date"])))
        ]),
    }
    sexo_de = {p["client_code"]: p.get("sex") for p in perfiles}
    for campo, etq in (("weight_kg", "weight_kg"), ("fat_pct", "fat_pct"), ("muscle_mass_kg", "muscle_mass_kg"),
                       ("hydration_pct", "hydration_pct"), ("bone_mass_kg", "bone_mass_kg")):
        D["scale"][etq + "_by_sex"] = {s: sp for s in ("M", "F")
                                       if (sp := spread([r.get(campo) for r in bascula if sexo_de.get(r.get("client_code")) == s]))}

    # --- 6 · laboratorio: el CATÁLOGO de marcadores (nombre, unidad, rango y dispersión), no los valores de nadie
    por_marcador = defaultdict(list)
    unidades = defaultdict(Counter)
    rangos = defaultdict(list)
    tipos = Counter()
    informes_por_cliente = Counter()
    for r in labs:
        tipos[r.get("source_type") or "desconocido"] += 1
        if r.get("client_code"):
            informes_por_cliente[r["client_code"]] += 1
        for v in (r.get("values") or ()):
            nombre = (v.get("indicator") or v.get("analyte") or "").strip()
            if not nombre or v.get("value") is None:
                continue
            try:
                por_marcador[nombre].append(float(v["value"]))
            except (TypeError, ValueError):
                continue
            if v.get("unit"):
                unidades[nombre][str(v["unit"])] += 1
            if v.get("range_low") is not None or v.get("range_high") is not None:
                rangos[nombre].append((v.get("range_low"), v.get("range_high")))
    marcadores = []
    for nombre, vals in por_marcador.items():
        sp = spread(vals)
        if not sp:                                        # menos de diez observaciones: fuera
            continue
        rango = Counter(rangos[nombre]).most_common(1)
        marcadores.append({"marker": nombre[:200], "unit": (unidades[nombre].most_common(1) or [(None, 0)])[0][0],
                           "ref_low": rango[0][0][0] if rango else None, "ref_high": rango[0][0][1] if rango else None,
                           **{k: sp[k] for k in ("n", "mean", "sd", "p05", "p50", "p95")}})
    marcadores.sort(key=lambda m: -m["n"])
    D["labs"] = {"clients_with_labs_share": round(len(informes_por_cliente) / len(perfiles), 4),
                 "reports_per_client": spread(list(informes_por_cliente.values())),
                 "source_type_mix": shares(tipos),
                 "markers": marcadores}

    # --- 7 · lo que NO se deriva y se declara como modelado
    out["modelled"] = {
        "restriction_kinds": {"contains_lactose": 0.30, "contains_gluten": 0.22, "is_tree_nut": 0.14, "is_peanut": 0.10,
                              "contains_fish": 0.08, "contains_shellfish": 0.08, "contains_egg": 0.05, "contains_soy": 0.03},
        "why": ("Las banderas de salud sí se derivan (prevalencia real), pero el REPARTO por tipo de restricción no está "
                "en el corpus público como tabla y con celdas de una persona no se puede publicar. Estas proporciones "
                "son una elección de modelado, declarada, no una medición."),
        "free_text": ("Gustos, aversiones, deporte, horarios y logros se componen en el generador con el catálogo "
                      "público y un vocabulario inventado. Ni una palabra del texto libre del corpus viaja."),
    }

    blob = json.dumps(out, ensure_ascii=False)
    fugas = sorted(set(PSEUDONYM.findall(blob)))
    if fugas:
        print(f"ABORTADO: los parámetros llevan {len(fugas)} seudónimos", file=sys.stderr)
        raise SystemExit(2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    params = derive(args.dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(params, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    D = params["derived"]
    print(f"escrito {args.out} ({args.out.stat().st_size / 1024:.1f} KB)")
    print(f"  sexo {D['sex']} · tramos {len(D['age_bucket'])} · objetivos {D['goal_mix']}")
    print(f"  franjas por objetivo: {[(g, len(v)) for g, v in D['slot_mix_by_goal'].items()]}")
    print(f"  celdas (objetivo,franja) con alimentos: {len(D['foods_by_goal_slot'])} · respaldo por franja: {len(D['foods_by_slot_fallback'])}")
    print(f"  marcadores de laboratorio publicables: {len(D['labs']['markers'])} de {len(D['labs']['markers'])} con n>=10")
    return 0


if __name__ == "__main__":
    sys.exit(main())
