# -*- coding: utf-8 -*-
"""Bloque 3.3 -- peso, sexo y gramos: ¿escala EL las raciones con el cuerpo, o no?

La decision que cuelga de esto esta escrita en el encargo: **no se implementa escalado por peso salvo que se demuestre
que EL lo hace.** Reproducir al profesional, no corregirlo. Asi que esto es una medicion, no una propuesta.

Se separan dos cosas que la correlacion agregada confunde:

  A. **¿escala las RACIONES con el cuerpo?**  peso ~ gramos DEL MISMO ALIMENTO, dentro del mismo objetivo y sexo. Si
     el escribe 180 gr de pollo a uno de 95 kg y 120 gr al de 60 kg, sale aqui.
  B. **¿usa el cuerpo para decidir cuanto RECORTA?**  peso ~ total diario dentro del mismo objetivo y sexo, y peso ~
     distancia del total diario a la mediana de ese objetivo. Son dos preguntas distintas: se puede no escalar
     raciones y aun asi dar mas comida al que pesa mas.

Y aparte, la que decide si el 0,15 del sexo hace algo: **¿hay diferencia de gramos entre hombres y mujeres en el mismo
objetivo y el mismo alimento?**, con n e intervalo por remuestreo.

Todo con el peso de la BASCULA resuelto a la fecha de cada dieta (bloque 0), no con el 10,7 % de perfiles que traian
peso anotado a mano y sin fecha. Se repite con % de grasa y masa muscular, que antes no existian.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.weight_and_grams
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
from pathlib import Path

from finalprosports.domain.model import Unit
from finalprosports.infrastructure.adapter.inbound.eval.body_signals import doc_dates
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import as_of_profile, setup
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()
SEED = 42
MIN_N = 30                       # por debajo de esto no se reporta una correlacion por celda
BODY = (("peso", "weight"), ("grasa_pct", "fat"), ("masa_muscular", "muscle"))


def spearman(xs, ys):
    from scipy.stats import spearmanr
    r = spearmanr(xs, ys)
    return float(r.statistic), float(r.pvalue)


def boot_ci(values, reps=2000, seed=SEED):
    if len(values) < 3:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    medias = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(reps))
    return medias[int(reps * 0.025)], medias[int(reps * 0.975)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "weight_and_grams.json")
    ap.add_argument("--top-foods", type=int, default=25)
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    dates = doc_dates(DATASET_DIR)
    catalog = root.catalog

    # ---------------------------------------------------------------- una fila por (dieta, alimento) con gramos
    filas = []
    por_dieta = []
    for q in queries:
        p = as_of_profile(root, pid, profiles[q.client_code], q.goal, q.id)
        if p.weight_kg is None or p.sex is None:
            continue
        total = 0.0
        items = []
        for m in q.meals:
            for it in m.items:
                qty = it.quantity
                if qty is None or qty.unit is not Unit.GRAM or not qty.value:
                    continue
                gramos = float(qty.value)
                total += gramos
                items.append((it.food_id, gramos))
        if not items:
            continue
        por_dieta.append({"diet": q.id, "goal": q.goal.value, "sex": p.sex, "weight": p.weight_kg,
                          "fat": p.fat_pct, "muscle": p.muscle_mass_kg, "total": total, "n_items": len(items)})
        for food_id, gramos in items:
            filas.append({"goal": q.goal.value, "sex": p.sex, "weight": p.weight_kg, "fat": p.fat_pct,
                          "muscle": p.muscle_mass_kg, "food": food_id, "grams": gramos})
    print(f"dietas con peso de bascula anterior Y gramos: {len(por_dieta)} de {len(queries)}")
    print(f"filas (dieta, alimento) en gramos: {len(filas):,}\n")
    out = {"diets": len(por_dieta), "rows": len(filas), "queries": len(queries)}

    # ------------------------------------------------------------------------------- A · ¿escala las RACIONES?
    print("## A · ¿escala las RACIONES con el cuerpo?  (peso ~ gramos del MISMO alimento, mismo objetivo y sexo)\n")
    por_celda = collections.defaultdict(list)
    for f in filas:
        por_celda[(f["goal"], f["sex"], f["food"])].append(f)
    celdas = [(k, v) for k, v in por_celda.items() if len(v) >= MIN_N]
    celdas.sort(key=lambda kv: -len(kv[1]))
    print(f"celdas (objetivo x sexo x alimento) con n >= {MIN_N}: {len(celdas)}")
    out["rations"] = {}
    for etiqueta, campo in BODY:
        rs, ns, sig = [], 0, 0
        for (goal, sex, food), v in celdas:
            xs = [f[campo] for f in v if f[campo] is not None]
            ys = [f["grams"] for f in v if f[campo] is not None]
            if len(xs) < MIN_N or len(set(xs)) < 3:
                continue
            r, p = spearman(xs, ys)
            rs.append(r); ns += 1
            sig += 1 if p < 0.05 else 0
        if rs:
            lo, hi = boot_ci(rs)
            out["rations"][etiqueta] = {"cells": ns, "mean_r": statistics.fmean(rs), "ci95": [lo, hi],
                                        "significant_cells": sig, "significant_frac": sig / ns}
            print(f"  {etiqueta:15} celdas {ns:>4}  r medio {statistics.fmean(rs):+.4f}  "
                  f"IC [{lo:+.4f}, {hi:+.4f}]  celdas con p<0,05: {sig}/{ns} ({sig/ns:.1%})")
    print("\n  lectura: si NO escalara, el r medio estaria en 0 y la fraccion de celdas significativas cerca del 5 %,")
    print("  que es lo que sale por azar con ese umbral.\n")

    # --------------------------------------------------------------------------------- B · ¿decide cuanto RECORTA?
    print("## B · ¿usa el cuerpo para decidir cuanto RECORTA?  (peso ~ total diario, y ~ distancia a la mediana)\n")
    por_obj_sexo = collections.defaultdict(list)
    for d in por_dieta:
        por_obj_sexo[(d["goal"], d["sex"])].append(d)
    medianas = {k: statistics.median([d["total"] for d in v]) for k, v in por_obj_sexo.items()}
    out["totals"] = {}
    print(f"  {'objetivo x sexo':28}{'n':>6}{'mediana g':>11}   " + "".join(f"{e:>26}" for e, _ in BODY))
    for k, v in sorted(por_obj_sexo.items(), key=lambda kv: -len(kv[1])):
        if len(v) < MIN_N:
            continue
        linea = f"  {k[0] + ' · ' + k[1]:28}{len(v):>6}{medianas[k]:>11.0f}   "
        celda = {}
        for etiqueta, campo in BODY:
            xs = [d[campo] for d in v if d[campo] is not None]
            ys = [d["total"] for d in v if d[campo] is not None]
            if len(xs) < MIN_N or len(set(xs)) < 3:
                linea += f"{'—':>26}"
                continue
            r, p = spearman(xs, ys)
            celda[etiqueta] = {"n": len(xs), "r": r, "p": p}
            linea += f"{f'r {r:+.3f} p {p:.2g}':>26}"
        out["totals"][f"{k[0]}|{k[1]}"] = {"n": len(v), "median_grams": medianas[k], **celda}
        print(linea)

    print(f"\n  y contra la DISTANCIA del total a la mediana de su celda (|total - mediana|):")
    for etiqueta, campo in BODY:
        xs, ys = [], []
        for k, v in por_obj_sexo.items():
            if len(v) < MIN_N:
                continue
            for d in v:
                if d[campo] is not None:
                    xs.append(d[campo]); ys.append(abs(d["total"] - medianas[k]))
        if len(xs) >= MIN_N:
            r, p = spearman(xs, ys)
            out.setdefault("distance_to_median", {})[etiqueta] = {"n": len(xs), "r": r, "p": p}
            print(f"    {etiqueta:15} n {len(xs):>5}  r {r:+.4f}  p {p:.3g}")

    # ------------------------------------------------------------------- ¿hay diferencia de gramos por SEXO?
    print("\n## ¿Diferencia de gramos entre hombres y mujeres, mismo objetivo y mismo alimento?\n")
    por_of = collections.defaultdict(lambda: {"M": [], "F": []})
    for f in filas:
        if f["sex"] in ("M", "F"):
            por_of[(f["goal"], f["food"])][f["sex"]].append(f["grams"])
    comparables = [(k, v) for k, v in por_of.items() if len(v["M"]) >= MIN_N and len(v["F"]) >= MIN_N]
    comparables.sort(key=lambda kv: -(len(kv[1]["M"]) + len(kv[1]["F"])))
    print(f"  celdas (objetivo x alimento) con n >= {MIN_N} en LOS DOS sexos: {len(comparables)}")
    difs, mayores_h = [], 0
    print(f"\n  {'objetivo':20}{'alimento':26}{'n H':>6}{'n M':>6}{'g H':>8}{'g M':>8}{'H - M':>9}{'IC 95 %':>22}")
    out["sex_difference"] = {"cells": len(comparables), "rows": []}
    for (goal, food), v in comparables[: args.top_foods]:
        mh, mf = statistics.fmean(v["M"]), statistics.fmean(v["F"])
        d = mh - mf
        difs.append(d); mayores_h += 1 if d > 0 else 0
        rng = random.Random(SEED)
        boots = sorted(statistics.fmean(rng.choices(v["M"], k=len(v["M"]))) - statistics.fmean(rng.choices(v["F"], k=len(v["F"])))
                       for _ in range(1000))
        lo, hi = boots[25], boots[975]
        nombre = catalog.get(food).canonical_name if catalog.get(food) else str(food)
        cruza = "" if (lo > 0 or hi < 0) else "  (cruza 0)"
        print(f"  {goal[:18]:20}{nombre[:24]:26}{len(v['M']):>6}{len(v['F']):>6}{mh:>8.0f}{mf:>8.0f}{d:>+9.1f}"
              f"{f'[{lo:+.1f}, {hi:+.1f}]':>22}{cruza}")
        out["sex_difference"]["rows"].append({"goal": goal, "food": nombre, "n_m": len(v["M"]), "n_f": len(v["F"]),
                                              "mean_m": mh, "mean_f": mf, "diff": d, "ci95": [lo, hi]})
    if difs:
        todas = [statistics.fmean(v["M"]) - statistics.fmean(v["F"]) for _, v in comparables]
        lo, hi = boot_ci(todas)
        print(f"\n  sobre las {len(todas)} celdas comparables: diferencia media H - M = {statistics.fmean(todas):+.1f} g "
              f"IC [{lo:+.1f}, {hi:+.1f}] · el hombre lleva mas en {sum(1 for d in todas if d > 0)}/{len(todas)} celdas")
        out["sex_difference"]["overall"] = {"cells": len(todas), "mean_diff": statistics.fmean(todas),
                                            "ci95": [lo, hi], "male_higher": sum(1 for d in todas if d > 0)}

    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
