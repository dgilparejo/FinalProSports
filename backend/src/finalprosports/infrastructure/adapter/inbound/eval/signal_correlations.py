# -*- coding: utf-8 -*-
"""Bloques 3.1 y 3.2 -- que sabe el sistema de una persona: cada senal, por separado, contra el parecido REAL.

Por que se rehace. `method`, `height` y `sport` se pusieron a 0,00 porque no mejoraban el J top-1, y el J top-1 lo
calcula un ordenador cuya correlacion con el parecido real de las dietas es **+0,0429**. Elegir pesos optimizando una
metrica que depende del propio ordenador que se esta evaluando es circular. Aqui la referencia es directa: el Jaccard
entre las DOS DIETAS de un par de clientes distintos, que es lo que de verdad se quiere predecir.

Por cada senal se reportan tres numeros, y los tres hacen falta:

* **cobertura** -- en cuantos pares es evaluable. Una correlacion alta sobre el 4 % de los pares no sirve para ordenar.
* **r global** -- Spearman contra el Jaccard real. Se usa rango y no Pearson porque casi ninguna senal es lineal en el
  parecido y varias son binarias.
* **r condicionada al MISMO objetivo** -- que es donde de verdad hace falta discriminar: el objetivo ya lo filtra la
  recuperacion, asi que una senal que solo sepa distinguir volumen de definicion no aporta nada dentro del estrato.

Los pares son SIEMPRE de clientes DISTINTOS (dos versiones del mismo cliente se parecen por serlo, no por ninguna
senal) y de la particion apartada, para que ninguna de estas correlaciones haya visto los clientes con los que se
eligieron los pesos.

3.2 anade la senal que no es del cliente: la DISTANCIA EN DIAS entre las dos dietas. Si la fecha predice mejor que
cualquier atributo, su criterio depende mas de su epoca que de quien tiene delante. Se mide aunque salga cero.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.signal_correlations [--pairs 200000]
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

from finalprosports.domain.composition.policy.body_type_policy import read as read_body_type
from finalprosports.infrastructure.adapter.inbound.eval.body_signals import doc_dates
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import as_of_profile, key_set, setup
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()
SEED = 42
MIN_PAIRS = 500                 # por debajo de esto una correlacion no se reporta: no se puede sostener


def _tokens(text) -> frozenset:
    if not text:
        return frozenset()
    if isinstance(text, (list, tuple)):
        text = " ".join(str(x) for x in text)
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return frozenset(w for w in re.findall(r"[a-z]{3,}", t))


def _span(a, b, span) -> float | None:
    if a is None or b is None:
        return None
    return max(0.0, 1.0 - min(abs(float(a) - float(b)), span) / span)


def _eq(a, b) -> float | None:
    if not a or not b:
        return None
    return 1.0 if a == b else 0.0


def _jac(a: frozenset, b: frozenset) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def spearman(xs, ys) -> tuple[float, float]:
    from scipy.stats import spearmanr
    r = spearmanr(xs, ys)
    return float(r.statistic), float(r.pvalue)


def build_features(root, pid, profiles, queries, dates, raw_profiles, labs_by_client, top_labs):
    """Un vector de senales por CONSULTA. Todo lo fechado se resuelve a la fecha de SU dieta."""
    feats = {}
    for q in queries:
        p = as_of_profile(root, pid, profiles[q.client_code], q.goal, q.id)
        raw = raw_profiles.get(q.client_code, {})
        bt = read_body_type(raw.get("body_type"))
        cut = dates.get(q.id)
        labs = {}
        if cut:
            for r in labs_by_client.get(q.client_code, []):
                if r["report_date"] and r["report_date"] < cut:
                    for v in r["values"]:
                        name = v.get("indicator") or v.get("analyte")
                        if name in top_labs and v.get("value") is not None:
                            labs[name] = float(v["value"])           # la mas reciente anterior gana
        feats[q.id] = {
            "goal": q.goal, "sex": p.sex, "age": p.age, "activity": p.activity_level,
            "restr": (bool(p.has_allergies), bool(p.has_intolerances), bool(p.has_medical_restrictions)),
            "methods": frozenset(p.methods or ()), "height": p.height_cm, "sport": (p.sport or "").strip().lower() or None,
            "training_time": (raw.get("training_time") or "").strip().lower() or None,
            "body_type_raw": raw.get("body_type"), "body_type_norm": bt.somatotype, "body_type_clean": bt.is_clean,
            "liked": _tokens(raw.get("liked_foods")), "disliked": _tokens(raw.get("disliked_foods")),
            "supplements": _tokens(raw.get("own_supplements")),
            "free_text": _tokens(" ".join(str(raw.get(f) or "") for f in
                                          ("goals", "liked_foods", "disliked_foods", "food_vices", "work_schedule",
                                           "training_schedule", "sport_achievements"))),
            "weight": p.weight_kg, "fat": p.fat_pct, "muscle": p.muscle_mass_kg, "hydration": p.hydration_pct,
            "visceral": p.visceral_fat_rating, "metabolic_age": p.metabolic_age, "basal": p.basal_met_kcal,
            "labs": labs, "date": cut, "client": q.client_code, "keys": key_set(q),
        }
    return feats


def signal_values(a: dict, b: dict, top_labs) -> dict:
    """La similitud de CADA senal para un par. `None` = la senal no es evaluable en este par."""
    out = {
        "objetivo": 1.0 if a["goal"] == b["goal"] else 0.0,
        "sexo": _eq(a["sex"], b["sex"]),
        "edad": _span(a["age"], b["age"], 30),
        "actividad": _span(a["activity"], b["activity"], 5),
        "restricciones": sum(1.0 for x, y in zip(a["restr"], b["restr"]) if x == y) / 3.0,
        "metodo": (1.0 if a["methods"] & b["methods"] else 0.0) if (a["methods"] and b["methods"]) else None,
        "complexion_cruda": _eq(a["body_type_raw"], b["body_type_raw"]),
        "complexion_validos": _eq(a["body_type_norm"], b["body_type_norm"]) if (a["body_type_clean"] and b["body_type_clean"]) else None,
        "complexion_normalizada": _eq(a["body_type_norm"], b["body_type_norm"]),
        "altura": _span(a["height"], b["height"], 25),
        "deporte": _eq(a["sport"], b["sport"]),
        "horario_entreno": _eq(a["training_time"], b["training_time"]),
        "gustos_positivos": _jac(a["liked"], b["liked"]),
        "gustos_negativos": _jac(a["disliked"], b["disliked"]),
        "suplementos_propios": _jac(a["supplements"], b["supplements"]),
        "texto_libre_solapamiento": _jac(a["free_text"], b["free_text"]),
        "peso": _span(a["weight"], b["weight"], 30),
        "grasa_pct": _span(a["fat"], b["fat"], 15),
        "masa_muscular": _span(a["muscle"], b["muscle"], 20),
        "grasa_visceral": _span(a["visceral"], b["visceral"], 8),
        "edad_metabolica": _span(a["metabolic_age"], b["metabolic_age"], 20),
        "metabolismo_basal": _span(a["basal"], b["basal"], 800),
        "hidratacion": _span(a["hydration"], b["hydration"], 10),
    }
    if a["date"] and b["date"]:
        from datetime import date as _d
        dias = abs((_d.fromisoformat(a["date"]) - _d.fromisoformat(b["date"])).days)
        out["_dias"] = dias
        out["proximidad_temporal"] = max(0.0, 1.0 - min(dias, 3650) / 3650)
    for name in top_labs:
        va, vb = a["labs"].get(name), b["labs"].get(name)
        out[f"lab · {name}"] = _span(va, vb, top_labs[name]) if (va is not None and vb is not None) else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=int, default=250_000, help="pares muestreados (todos si hay menos)")
    ap.add_argument("--labs", type=int, default=12, help="parametros de analitica de mayor cobertura que se prueban")
    ap.add_argument("--holdout-only", action="store_true", default=True)
    ap.add_argument("--all-clients", dest="holdout_only", action="store_false")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "signal_correlations.json")
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    dates = doc_dates(DATASET_DIR)
    raw_profiles = {}
    for line in (DATASET_DIR / "profiles.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        raw_profiles[r["client_code"]] = r
    labs_by_client = collections.defaultdict(list)
    freq = collections.Counter()
    rango = collections.defaultdict(list)
    path = DATASET_DIR / "lab_results.jsonl"
    if path.exists():
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if r["client_code"] and r["report_date"] and r["values"] and not r.get("values_unreliable"):
                labs_by_client[r["client_code"]].append(r)
                for v in r["values"]:
                    name = v.get("indicator") or v.get("analyte")
                    if v.get("value") is not None:
                        freq[name] += 1
                        rango[name].append(float(v["value"]))
    top_labs = {}
    for name, _ in freq.most_common(args.labs):
        vals = sorted(rango[name])
        span = vals[int(len(vals) * 0.95)] - vals[int(len(vals) * 0.05)]
        top_labs[name] = span or 1.0

    # particion POR CLIENTE, la misma semilla y el mismo corte que el barrido
    codes = sorted({q.client_code for q in queries})
    random.Random(SEED).shuffle(codes)
    hold = set(codes[int(len(codes) * 0.6):])
    pool = [q for q in queries if q.client_code in hold] if args.holdout_only else list(queries)
    print(f"consultas del conjunto usado: {len(pool)} de {len(queries)} · clientes {len({q.client_code for q in pool})}")
    print(f"parametros de analitica probados: {len(top_labs)}")

    feats = build_features(root, pid, profiles, pool, dates, raw_profiles, labs_by_client, top_labs)
    ids = [q.id for q in pool]
    todos = [(i, j) for a, i in enumerate(ids) for j in ids[a + 1:]
             if feats[i]["client"] != feats[j]["client"]]
    rng = random.Random(SEED)
    if len(todos) > args.pairs:
        todos = rng.sample(todos, args.pairs)
    print(f"pares de clientes DISTINTOS: {len(todos):,}\n")

    filas = collections.defaultdict(lambda: {"x": [], "y": [], "x_same": [], "y_same": []})
    dias_x, dias_y, dias_x_s, dias_y_s = [], [], [], []
    for i, j in todos:
        a, b = feats[i], feats[j]
        real = jaccard(a["keys"], b["keys"])
        mismo = a["goal"] == b["goal"]
        vals = signal_values(a, b, top_labs)
        if "_dias" in vals:
            dias_x.append(vals["_dias"]); dias_y.append(real)
            if mismo:
                dias_x_s.append(vals["_dias"]); dias_y_s.append(real)

        for name, v in vals.items():
            if name.startswith("_") or v is None:
                continue
            f = filas[name]
            f["x"].append(v); f["y"].append(real)
            if mismo:
                f["x_same"].append(v); f["y_same"].append(real)

    print(f"{'senal':34}{'cobertura':>11}{'%':>8}{'r global':>11}{'p':>10}{'r mismo obj.':>14}{'p':>10}")
    out = {}
    for name in sorted(filas, key=lambda n: -len(filas[n]["x"])):
        f = filas[name]
        n = len(f["x"])
        if n < MIN_PAIRS or len(set(f["x"])) < 2:
            continue
        r, p = spearman(f["x"], f["y"])
        if len(f["x_same"]) >= MIN_PAIRS and len(set(f["x_same"])) > 1:
            rs, ps = spearman(f["x_same"], f["y_same"])
        else:
            rs = ps = float("nan")
        out[name] = {"pairs": n, "coverage": n / len(todos), "r": r, "p": p,
                     "r_same_goal": rs, "p_same_goal": ps, "pairs_same_goal": len(f["x_same"])}
        print(f"  {name[:32]:34}{n:>11,}{n/len(todos):>8.1%}{r:>+11.4f}{p:>10.2g}{rs:>+14.4f}{ps:>10.2g}")

    # ------------------------------------------------------------------------------------------ 3.2 · la prueba temporal
    print("\n## 3.2 · LA PRUEBA TEMPORAL (distancia en dias entre dos dietas de clientes DISTINTOS)\n")
    if len(dias_x) >= MIN_PAIRS:
        r, p = spearman(dias_x, dias_y)
        print(f"  |dias| vs Jaccard, global        : r = {r:+.4f}  p = {p:.3g}  n = {len(dias_x):,}")
        out["_temporal_global"] = {"r": r, "p": p, "n": len(dias_x)}
        if len(dias_x_s) >= MIN_PAIRS:
            rs, ps = spearman(dias_x_s, dias_y_s)
            print(f"  |dias| vs Jaccard, MISMO objetivo: r = {rs:+.4f}  p = {ps:.3g}  n = {len(dias_x_s):,}")
            out["_temporal_same_goal"] = {"r": rs, "p": ps, "n": len(dias_x_s)}
        mejor = max((v for k, v in out.items() if not k.startswith("_")), key=lambda v: abs(v["r"]))
        nombre = next(k for k, v in out.items() if v is mejor)
        print(f"\n  el mejor atributo del CLIENTE es «{nombre}» con r = {mejor['r']:+.4f}")
        print(f"  la fecha da |r| = {abs(r):.4f} -> {'LA FECHA PREDICE MEJOR' if abs(r) > abs(mejor['r']) else 'el atributo predice mejor'}")
        # por tramos, que es como se ve si hay un efecto de epoca
        tramos = [(0, 30), (30, 90), (90, 365), (365, 1095), (1095, 10**9)]
        print(f"\n  {'tramo (dias)':18}{'n':>9}{'J medio':>10}")
        for lo, hi in tramos:
            sel = [y for x, y in zip(dias_x, dias_y) if lo <= x < hi]
            if sel:
                print(f"  {f'{lo}-{hi if hi < 10**9 else ''}':18}{len(sel):>9,}{sum(sel)/len(sel):>10.4f}")
    else:
        print("  (no hay pares suficientes con fecha en los dos lados)")

    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
