# -*- coding: utf-8 -*-
"""La fecha, en su version CAUSAL. La objecion del titular es correcta y cambia la pregunta.

El −0,3795 se midio sobre la distancia ABSOLUTA entre dos dietas. **Esa cifra no se puede hacer causal moviendo el
signo**, y conviene decir por que antes de dar ninguna otra: `|dias|` es SIMETRICO. Para un par no ordenado, la
antiguedad del mas viejo respecto del mas nuevo es la MISMA cifra mirada desde cualquiera de los dos lados, asi que
restringir los pares a «el caso es anterior a la consulta» deja exactamente los mismos pares con exactamente los
mismos valores, y la correlacion sale identica. Repetirla como si fuera una comprobacion nueva seria hacer trampa a la
pregunta.

**La pregunta causal de verdad es OTRA, y es por consulta**: fijada una consulta, entre los candidatos que existian
ANTES de ella, ¿los mas recientes se parecen mas a la dieta oculta? Eso es lo unico que un ordenador puede explotar en
produccion, y es directamente comparable con el `+0,0429` que da hoy la similitud (que tambien es una media de
correlaciones DENTRO de cada consulta).

Tres medidas, en este orden:

  1. **la correlacion por consulta** de la antiguedad del candidato con su parecido real, sobre el conjunto causal, y
     al lado la de la similitud actual sobre el MISMO conjunto, para que la comparacion sea justa;
  2. **la metrica aprendida restringida**: se entrena y se evalua solo con pares causales y con la antiguedad del
     CASO como rasgo, y se reproduce la tabla del oraculo sobre el conjunto causal;
  3. el brazo D3 + recencia se mide en `arms_compare` (RS / RR / RB) y se analiza en `arms_report`, como los demas.

Lo que NO se hace: rellenar con posteriores una consulta sin candidatos anteriores suficientes. Se cuenta aparte.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.causal_recency
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import date
from pathlib import Path

from finalprosports.infrastructure.adapter.inbound.eval.body_signals import doc_dates
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import as_of_profile, key_set, setup
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()
SEED = 42
K = 20
POOL = 400
MIN_POOL = 25


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", type=int, default=120)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "causal_recency.json")
    args = ap.parse_args()

    from scipy.stats import spearmanr

    root, pid, diets, profiles, queries, rules = setup()
    dates = doc_dates(DATASET_DIR)
    svc = root.retrieve_similar_cases_service
    con_fecha = [q for q in queries if dates.get(q.id)]
    muestra = random.Random(SEED).sample(con_fecha, min(args.queries, len(con_fecha)))
    print(f"consultas con fecha de documento: {len(con_fecha)} de {len(queries)}")
    print(f"muestra: {len(muestra)} · conjunto de candidatos {POOL} · k = {K}\n")

    r_rec, r_sim, sin_pool, tam = [], [], 0, []
    mejor_sim, mejor_rec, mejor_ora = [], [], []
    media_sim, media_rec, media_ora = [], [], []
    for q in muestra:
        perfil = as_of_profile(root, pid, profiles[q.client_code], q.goal, q.id)
        excl = frozenset(svc.mandatory_exclusions(pid, perfil) | {q.id})
        cands = root.case_repository.find_similar(pid, svc.query_for(perfil), POOL, excl)
        corte = date.fromisoformat(dates[q.id]).toordinal()
        pool = [(c, corte - date.fromisoformat(dates[c.diet.id]).toordinal())
                for c in cands if dates.get(c.diet.id) and date.fromisoformat(dates[c.diet.id]).toordinal() < corte]
        if len(pool) < MIN_POOL:
            sin_pool += 1
            continue
        tam.append(len(pool))
        oculta = key_set(q)
        reales = [jaccard(key_set(c.diet), oculta) for c, _ in pool]
        edades = [-d for _, d in pool]                    # mas reciente = mayor valor, para que el signo sea legible
        sims = [c.score.total for c, _ in pool]
        if len(set(reales)) > 1:
            if len(set(edades)) > 1:
                r_rec.append(float(spearmanr(edades, reales).statistic))
            if len(set(sims)) > 1:
                r_sim.append(float(spearmanr(sims, reales).statistic))
        por_rec = sorted(range(len(pool)), key=lambda i: -edades[i])[:K]
        por_sim = sorted(range(len(pool)), key=lambda i: -sims[i])[:K]
        por_real = sorted(range(len(pool)), key=lambda i: -reales[i])[:K]
        mejor_rec.append(max(reales[i] for i in por_rec)); media_rec.append(statistics.fmean(reales[i] for i in por_rec))
        mejor_sim.append(max(reales[i] for i in por_sim)); media_sim.append(statistics.fmean(reales[i] for i in por_sim))
        mejor_ora.append(max(reales[i] for i in por_real)); media_ora.append(statistics.fmean(reales[i] for i in por_real))

    n = len(mejor_rec)
    print(f"consultas evaluadas: {n} · descartadas por menos de {MIN_POOL} candidatos ANTERIORES: {sin_pool}")
    print(f"tamano del conjunto causal: mediana {statistics.median(tam):.0f} de {POOL}\n")
    print("## 1 · Correlacion DENTRO de cada consulta, sobre el conjunto causal\n")
    print(f"  {'ordenador':28}{'r medio':>10}{'r mediana':>12}{'consultas con r < 0':>22}")
    out = {"queries": n, "dropped_small_pool": sin_pool, "pool_median": statistics.median(tam)}
    for nombre, serie, clave in (("RECENCIA (mas reciente)", r_rec, "recency"), ("similitud ACTUAL", r_sim, "similarity")):
        if not serie:
            continue
        neg = sum(1 for x in serie if x < 0)
        out[f"within_query_{clave}"] = {"mean": statistics.fmean(serie), "median": statistics.median(serie),
                                        "negative": neg, "n": len(serie)}
        print(f"  {nombre:28}{statistics.fmean(serie):>+10.4f}{statistics.median(serie):>+12.4f}"
              f"{f'{neg}/{len(serie)} = {100*neg/len(serie):.1f} %':>22}")

    print("\n## 2 · Tabla del oraculo sobre el conjunto CAUSAL\n")
    print(f"  {'ordenador':30}{'mejor de los k':>16}{'media de los k':>16}")
    filas = {}
    for nombre, mej, med, clave in (("similitud ACTUAL", mejor_sim, media_sim, "similarity"),
                                    ("RECENCIA sola", mejor_rec, media_rec, "recency"),
                                    ("ORACULO (cota)", mejor_ora, media_ora, "oracle")):
        filas[clave] = [statistics.fmean(mej), statistics.fmean(med)]
        print(f"  {nombre:30}{statistics.fmean(mej):>16.4f}{statistics.fmean(med):>16.4f}")
    out["oracle_table_causal"] = filas
    hueco = filas["oracle"][0] - filas["similarity"][0]
    if hueco > 0:
        rec_gap = (filas["recency"][0] - filas["similarity"][0]) / hueco
        out["recency_gap_recovered_best"] = rec_gap
        print(f"\n  hueco hasta el oraculo que recupera la RECENCIA sola: {rec_gap:.1%}")
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
