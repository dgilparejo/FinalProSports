# -*- coding: utf-8 -*-
"""Bloque 4 -- ¿se puede APRENDER una metrica que ordene mejor que la similitud escrita a mano?

El planteamiento: un regresor sobre PARES. Entrada `(perfil_i, perfil_j)`, salida `Jaccard(dieta_i, dieta_j)`. Si
aprende algo, ordena los candidatos mejor que la puntuacion actual, cuya correlacion con el parecido real es **+0,0429**.

**LA FUGA ES EL RIESGO PRINCIPAL Y SE DECLARA COMO SE EVITA.** Hay 115 pares del MISMO cliente con J >= 0,90 y 19
entre clientes DISTINTOS. Un modelo que vea a un cliente en entrenamiento y en prueba aprende a ese cliente, no la
relacion. Tres candados, y los tres se afirman en tiempo de ejecucion:

  1. la particion es **por cliente**: se barajan los CODIGOS con semilla fija y se cortan; ningun cliente puede caer a
     los dos lados porque los conjuntos de codigos son disjuntos por construccion, y se comprueba que la interseccion
     este vacia (`assert`);
  2. un par entra en entrenamiento solo si **SUS DOS clientes** estan en el lado de entrenamiento, y en prueba solo si
     **SUS DOS** estan en el de prueba. Los pares mixtos SE TIRAN -- son el 48 % y tirarlos es el precio de no filtrar;
  3. **ningun par es del mismo cliente**, ni en entrenamiento ni en prueba. Dos versiones del mismo cliente se parecen
     por serlo, y aprender eso seria aprender la identidad.

Se compara contra dos referencias, y las dos hacen falta:
  * la **similitud actual** (`attribute_score`), que es a quien hay que ganar;
  * un **predictor constante** (la media del entrenamiento), que es el suelo: un R2 negativo contra el constante
    significa que el modelo es peor que no mirar nada.

Y si gana, se reproduce la tabla del oraculo con la metrica aprendida como ordenador, sobre las MISMAS 120 consultas.

**Si no supera a la similitud actual, se dice y se para.** No se ajustan hiperparametros hasta que gane: eso es
elegir sobre el conjunto de prueba con pasos extra.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.learned_metric
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
from pathlib import Path

import numpy as np

from finalprosports.domain.composition.policy.attribute_similarity_policy import DEFAULT_WEIGHTS, attribute_score
from finalprosports.infrastructure.adapter.inbound.eval.body_signals import doc_dates
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import as_of_profile, key_set, setup
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()
SEED = 42
K = 20


def pair_features(a, b) -> list[float]:
    """Las senales del par, en el mismo espiritu que la similitud escrita a mano: SIMETRICAS en los dos perfiles.

    Simetricas a proposito: `f(i, j)` tiene que valer lo mismo que `f(j, i)`, porque el parecido entre dos dietas lo
    es. Con rasgos asimetricos (por ejemplo «la edad de i») el modelo aprenderia a identificar al cliente i.
    """
    def dif(x, y):
        return abs(x - y) if (x is not None and y is not None) else -1.0

    def med(x, y):
        return (x + y) / 2 if (x is not None and y is not None) else -1.0

    def eq(x, y):
        return 1.0 if (x and y and x == y) else (0.0 if (x and y) else -1.0)

    pa, pb = a["p"], b["p"]
    return [
        1.0 if pa.goal == pb.goal else 0.0,
        eq(pa.sex, pb.sex),
        dif(pa.age, pb.age), med(pa.age, pb.age),
        dif(pa.activity_level, pb.activity_level),
        sum(1.0 for x, y in zip(a["restr"], b["restr"]) if x == y),
        1.0 if (a["methods"] & b["methods"]) else (0.0 if (a["methods"] and b["methods"]) else -1.0),
        eq(a["body_type"], b["body_type"]),
        dif(pa.height_cm, pb.height_cm), med(pa.height_cm, pb.height_cm),
        eq(a["sport"], b["sport"]),
        eq(a["training_time"], b["training_time"]),
        dif(pa.weight_kg, pb.weight_kg), med(pa.weight_kg, pb.weight_kg),
        dif(pa.fat_pct, pb.fat_pct), med(pa.fat_pct, pb.fat_pct),
        dif(pa.muscle_mass_kg, pb.muscle_mass_kg), med(pa.muscle_mass_kg, pb.muscle_mass_kg),
        dif(pa.visceral_fat_rating, pb.visceral_fat_rating),
        dif(pa.metabolic_age, pb.metabolic_age),
        dif(pa.basal_met_kcal, pb.basal_met_kcal),
        dif(pa.hydration_pct, pb.hydration_pct),
        len(a["liked"] & b["liked"]) / max(1, len(a["liked"] | b["liked"])) if (a["liked"] or b["liked"]) else -1.0,
        len(a["disliked"] & b["disliked"]) / max(1, len(a["disliked"] | b["disliked"])) if (a["disliked"] or b["disliked"]) else -1.0,
        a["days"] if a["days"] is not None and b["days"] is not None else -1.0,   # sustituido abajo por |dias|
        attribute_score(pa, pb, DEFAULT_WEIGHTS),
    ]


FEATURE_NAMES = ["mismo objetivo", "mismo sexo", "|d edad|", "edad media", "|d actividad|", "restricciones iguales",
                 "mismo metodo", "misma complexion", "|d altura|", "altura media", "mismo deporte", "mismo horario",
                 "|d peso|", "peso medio", "|d grasa|", "grasa media", "|d musculo|", "musculo medio",
                 "|d visceral|", "|d edad metab.|", "|d basal|", "|d hidratacion|",
                 "J gustos +", "J gustos -", "antiguedad del caso (dias)", "similitud ACTUAL"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=int, default=120_000)
    ap.add_argument("--with-date", action="store_true", default=True,
                    help="incluye |dias| entre las dos dietas como rasgo (bloque 3.2: es la senal mas fuerte)")
    ap.add_argument("--no-date", dest="with_date", action="store_false")
    ap.add_argument("--causal", action="store_true",
                    help="version CAUSAL: solo pares en los que el CASO es anterior a la consulta, y el rasgo de fecha "
                         "es la ANTIGUEDAD del caso, no la distancia absoluta. Es lo unico que se puede usar en "
                         "produccion, donde para un cliente que entra hoy solo existen dietas anteriores.")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "learned_metric.json")
    args = ap.parse_args()

    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import r2_score
    from scipy.stats import spearmanr

    root, pid, diets, profiles, queries, rules = setup()
    dates = doc_dates(DATASET_DIR)
    raw = {json.loads(l)["client_code"]: json.loads(l) for l in (DATASET_DIR / "profiles.jsonl").open(encoding="utf-8")}

    import re
    import unicodedata

    def toks(v):
        if not v:
            return frozenset()
        t = unicodedata.normalize("NFD", str(v).lower())
        return frozenset(re.findall(r"[a-z]{3,}", "".join(c for c in t if unicodedata.category(c) != "Mn")))

    feats = {}
    for q in queries:
        p = as_of_profile(root, pid, profiles[q.client_code], q.goal, q.id)
        r = raw.get(q.client_code, {})
        d = dates.get(q.id)
        feats[q.id] = {"p": p, "client": q.client_code, "keys": key_set(q), "date": d,
                       "restr": (p.has_allergies, p.has_intolerances, p.has_medical_restrictions),
                       "methods": frozenset(p.methods or ()), "body_type": r.get("body_type"),
                       "sport": (p.sport or "").lower() or None,
                       "training_time": (r.get("training_time") or "").lower() or None,
                       "liked": toks(r.get("liked_foods")), "disliked": toks(r.get("disliked_foods")),
                       "days": 0}

    # ---------------------------------------------------------------------------------- LOS TRES CANDADOS
    codes = sorted({q.client_code for q in queries})
    random.Random(SEED).shuffle(codes)
    cut = int(len(codes) * 0.6)
    train_c, test_c = set(codes[:cut]), set(codes[cut:])
    assert not (train_c & test_c), "CANDADO 1: un cliente en los dos lados"
    print(f"clientes: {len(train_c)} entrenamiento · {len(test_c)} prueba · interseccion {len(train_c & test_c)}")

    ids = [q.id for q in queries]
    rng = random.Random(SEED)
    todos = [(i, j) for a, i in enumerate(ids) for j in ids[a + 1:] if feats[i]["client"] != feats[j]["client"]]
    if args.causal:
        # El par se ORIENTA: el primero es el CASO y el segundo la CONSULTA, y solo entra si el caso es anterior.
        # Un par sin fecha en los dos lados no entra; no se rellena con nada.
        orientados = []
        for i, j in todos:
            di, dj = feats[i]["date"], feats[j]["date"]
            if not di or not dj or di == dj:
                continue
            orientados.append((i, j) if di < dj else (j, i))
        print(f"pares orientables (caso ANTERIOR a la consulta): {len(orientados):,} de {len(todos):,}")
        todos = orientados
    if len(todos) > args.pairs:
        todos = rng.sample(todos, args.pairs)
    tr = [(i, j) for i, j in todos if feats[i]["client"] in train_c and feats[j]["client"] in train_c]
    te = [(i, j) for i, j in todos if feats[i]["client"] in test_c and feats[j]["client"] in test_c]
    mixtos = len(todos) - len(tr) - len(te)
    print(f"pares (clientes distintos, CANDADO 3): {len(todos):,}")
    print(f"  entrenamiento (los DOS en train, CANDADO 2): {len(tr):,}")
    print(f"  prueba        (los DOS en test)            : {len(te):,}")
    print(f"  MIXTOS, descartados                        : {mixtos:,} ({mixtos/len(todos):.1%})")
    assert not ({feats[i]['client'] for i, _ in tr} | {feats[j]['client'] for _, j in tr}) & \
           ({feats[i]['client'] for i, _ in te} | {feats[j]['client'] for _, j in te}), "CANDADO 2: cliente compartido"
    print("  los tres candados se cumplen\n")

    def build(pares):
        X, y, sim = [], [], []
        for i, j in pares:
            a, b = feats[i], feats[j]
            v = pair_features(a, b)
            if args.with_date and a["date"] and b["date"]:
                from datetime import date as _d
                dias = (_d.fromisoformat(b["date"]) - _d.fromisoformat(a["date"])).days
                # En causal el par ya viene orientado (a = caso, b = consulta), asi que `dias` es POSITIVO y es la
                # antiguedad del caso. Fuera de causal se conserva el valor absoluto, que es lo que se publico.
                v[-2] = dias if args.causal else abs(dias)
            else:
                v[-2] = -1.0
            X.append(v)
            y.append(jaccard(a["keys"], b["keys"]))
            sim.append(v[-1])
        return np.array(X, dtype=float), np.array(y, dtype=float), np.array(sim, dtype=float)

    Xtr, ytr, _ = build(tr)
    Xte, yte, sim_te = build(te)
    modelo = HistGradientBoostingRegressor(random_state=SEED, max_iter=300, learning_rate=0.06)
    modelo.fit(Xtr, ytr)
    pred = modelo.predict(Xte)

    const = np.full_like(yte, ytr.mean())
    r_model = spearmanr(pred, yte)
    r_sim = spearmanr(sim_te, yte)
    print("## Sobre el conjunto de PRUEBA (clientes nunca vistos)\n")
    print(f"  {'predictor':28}{'Spearman r':>13}{'p':>12}{'R2':>10}")
    print(f"  {'constante (media de train)':28}{'—':>13}{'—':>12}{r2_score(yte, const):>10.4f}")
    print(f"  {'similitud ACTUAL':28}{r_sim.statistic:>+13.4f}{r_sim.pvalue:>12.2g}{r2_score(yte, sim_te):>10.4f}")
    print(f"  {'METRICA APRENDIDA':28}{r_model.statistic:>+13.4f}{r_model.pvalue:>12.2g}{r2_score(yte, pred):>10.4f}")

    gana = r_model.statistic > r_sim.statistic
    out = {"train_clients": len(train_c), "test_clients": len(test_c), "pairs_train": len(tr), "pairs_test": len(te),
           "pairs_discarded_mixed": mixtos, "with_date": bool(args.with_date),
           "spearman_learned": float(r_model.statistic), "spearman_current": float(r_sim.statistic),
           "r2_learned": float(r2_score(yte, pred)), "r2_current": float(r2_score(yte, sim_te)),
           "r2_constant": float(r2_score(yte, const)), "beats_current": bool(gana)}

    # importancia, que es informativa aunque pierda
    try:
        from sklearn.inspection import permutation_importance
        idx = rng.sample(range(len(yte)), min(20_000, len(yte)))
        imp = permutation_importance(modelo, Xte[idx], yte[idx], n_repeats=3, random_state=SEED, scoring="r2")
        orden = sorted(zip(FEATURE_NAMES, imp.importances_mean), key=lambda t: -t[1])
        print("\n  importancia por permutacion (R2 perdido al barajar el rasgo):")
        for nombre, v in orden[:10]:
            print(f"    {nombre:26}{v:>+10.5f}")
        out["importance"] = {n: float(v) for n, v in orden}
    except Exception as exc:                                     # noqa: BLE001
        print(f"  (importancia no calculada: {exc})")

    if not gana:
        print(f"\n## LA METRICA APRENDIDA NO SUPERA A LA ACTUAL ({r_model.statistic:+.4f} frente a {r_sim.statistic:+.4f}).")
        print("   Se para aqui: ajustar hiperparametros hasta que gane seria elegir sobre el conjunto de prueba.")
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"\n-> {args.out}")
        return 0

    print("\n## Supera a la actual. Tabla del ORACULO con la metrica aprendida como ordenador.\n")
    consultas = [q for q in queries if q.client_code in test_c]
    consultas = rng.sample(consultas, min(120, len(consultas)))
    mejor_sim, mejor_ap, mejor_ora, media_sim, media_ap, media_ora = [], [], [], [], [], []
    pool = [q for q in queries if q.client_code in test_c]
    for q in consultas:
        a = feats[q.id]
        cands = [o for o in pool if o.client_code != q.client_code]
        if args.causal:
            # La tabla del oraculo tambien tiene que ser causal: si el conjunto de candidatos incluye dietas
            # POSTERIORES a la consulta, el ordenador puede lucirse con casos que en produccion no existirian.
            cands = [o for o in cands if feats[o.id]["date"] and a["date"] and feats[o.id]["date"] < a["date"]]
        if len(cands) < K + 5:
            continue
        filas = []
        for o in cands:
            b = feats[o.id]
            v = pair_features(a, b)
            if args.with_date and a["date"] and b["date"]:
                from datetime import date as _d
                v[-2] = abs((_d.fromisoformat(a["date"]) - _d.fromisoformat(b["date"])).days)
            else:
                v[-2] = -1.0
            filas.append((v, jaccard(a["keys"], b["keys"])))
        X = np.array([f[0] for f in filas], dtype=float)
        real = [f[1] for f in filas]
        aprend = modelo.predict(X)
        actual = X[:, -1]
        por_ap = sorted(range(len(real)), key=lambda i: -aprend[i])[:K]
        por_sim = sorted(range(len(real)), key=lambda i: -actual[i])[:K]
        por_real = sorted(range(len(real)), key=lambda i: -real[i])[:K]
        mejor_ap.append(max(real[i] for i in por_ap)); media_ap.append(statistics.fmean(real[i] for i in por_ap))
        mejor_sim.append(max(real[i] for i in por_sim)); media_sim.append(statistics.fmean(real[i] for i in por_sim))
        mejor_ora.append(max(real[i] for i in por_real)); media_ora.append(statistics.fmean(real[i] for i in por_real))
    print(f"  consultas: {len(mejor_ap)}")
    print(f"  {'ordenador':30}{'mejor de los k':>16}{'media de los k':>16}")
    for nombre, mej, med in (("similitud ACTUAL", mejor_sim, media_sim), ("METRICA APRENDIDA", mejor_ap, media_ap),
                             ("ORACULO", mejor_ora, media_ora)):
        print(f"  {nombre:30}{statistics.fmean(mej):>16.4f}{statistics.fmean(med):>16.4f}")
    out["oracle_table"] = {"n": len(mejor_ap),
                           "current": [statistics.fmean(mejor_sim), statistics.fmean(media_sim)],
                           "learned": [statistics.fmean(mejor_ap), statistics.fmean(media_ap)],
                           "oracle": [statistics.fmean(mejor_ora), statistics.fmean(media_ora)]}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
