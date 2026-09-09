# -*- coding: utf-8 -*-
"""Bloque 8.1 -- ¿tiene EL en cuenta los gustos que anota en el cuestionario?

La disciplina es la misma que con el escalado por peso: **primero medir si el lo hace**, y solo despues decidir si se
implementa. Preguntar algo en un cuestionario no significa usarlo al escribir, y ese hallazgo tambien vale.

La medida. Para cada cliente con gustos anotados y para cada alimento de esa lista que el catalogo sepa resolver, se
compara:

    tasa OBSERVADA   -- en que fraccion de las dietas DE ESE CLIENTE aparece el alimento
    tasa BASE        -- en que fraccion de las dietas del MISMO OBJETIVO, de OTROS clientes, aparece ese alimento

El efecto es la diferencia. La tasa base tiene que ser por objetivo: el pollo aparece en casi todas las dietas de
volumen, asi que «aparece en las suyas» no dice nada por si solo.

**El control es la mitad negativa.** Con los gustos NEGATIVOS el efecto tiene que salir claramente por DEBAJO de cero:
si el declara que no come algo y ese algo aparece igual que en cualquier otra dieta, la medicion esta mal montada y
tampoco valdria la mitad positiva. Un control que no puede fallar no controla nada.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.food_preferences
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
from pathlib import Path

from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import setup
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()
SEED = 42
MIN_BASE_DIETS = 30          # por debajo de esto la tasa base no se puede estimar


def boot_ci(values, reps=2000, seed=SEED):
    if len(values) < 3:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    medias = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(reps))
    return medias[int(reps * 0.025)], medias[int(reps * 0.975)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "food_preferences.json")
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    catalog = root.catalog
    matcher = getattr(root, "food_matcher", None)

    # nombre canonico -> id, y los sinonimos, para resolver el texto libre del cuestionario
    por_nombre = {}
    for fid, f in catalog.items():
        por_nombre[f.canonical_name.lower()] = fid
        for syn in (f.synonyms or ()):
            por_nombre.setdefault(str(syn).lower(), fid)

    def resolver(texto) -> set[int]:
        if not texto:
            return set()
        if isinstance(texto, (list, tuple)):
            texto = " , ".join(str(x) for x in texto)
        out = set()
        for trozo in str(texto).replace(";", ",").replace("/", ",").split(","):
            t = trozo.strip().lower()
            if not t:
                continue
            if t in por_nombre:
                out.add(por_nombre[t])
                continue
            for nombre, fid in por_nombre.items():          # contencion: el nombre canonico dentro del texto
                if len(nombre) >= 5 and nombre in t:
                    out.add(fid)
                    break
        return out

    raw = {}
    for line in (DATASET_DIR / "profiles.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        raw[r["client_code"]] = r

    # alimentos por dieta, y dietas por cliente y por objetivo
    foods_of = {d.id: {i.food_id for m in d.meals for i in m.items if i.food_id is not None} for d in diets.values()}
    por_cliente = collections.defaultdict(list)
    por_objetivo = collections.defaultdict(list)
    for d in diets.values():
        por_cliente[d.client_code].append(d)
        por_objetivo[d.goal].append(d)

    print(f"corpus: {len(diets)} dietas · {len(por_cliente)} clientes · catalogo {len(catalog)} alimentos\n")
    out = {}
    for etiqueta, campo, signo in (("gustos POSITIVOS", "liked_foods", +1), ("gustos NEGATIVOS (control)", "disliked_foods", -1)):
        con_gustos, tamanos, efectos, detalle = 0, [], [], []
        for code, ds in por_cliente.items():
            resueltos = resolver(raw.get(code, {}).get(campo))
            if not resueltos:
                continue
            con_gustos += 1
            tamanos.append(len(resueltos))
            for fid in resueltos:
                suyas = [d for d in ds if fid in foods_of[d.id]]
                observada = len(suyas) / len(ds)
                # la base: dietas del MISMO objetivo, de OTROS clientes
                objetivos = {d.goal for d in ds}
                base_pool = [d for g in objetivos for d in por_objetivo[g] if d.client_code != code]
                if len(base_pool) < MIN_BASE_DIETS:
                    continue
                base = sum(1 for d in base_pool if fid in foods_of[d.id]) / len(base_pool)
                efectos.append(observada - base)
                detalle.append({"food": catalog[fid].canonical_name, "observed": observada, "base": base,
                                "effect": observada - base, "client_diets": len(ds)})
        if not efectos:
            print(f"## {etiqueta}: sin pares evaluables\n")
            continue
        lo, hi = boot_ci(efectos)
        pos = sum(1 for e in efectos if e > 0)
        print(f"## {etiqueta}\n")
        print(f"  clientes con la lista anotada        : {con_gustos} de {len(por_cliente)}")
        print(f"  alimentos resueltos por cliente      : media {statistics.fmean(tamanos):.1f} · mediana {statistics.median(tamanos):.0f}")
        print(f"  pares (cliente, alimento) evaluables : {len(efectos)}")
        print(f"  EFECTO medio (observada - base)      : {statistics.fmean(efectos):+.4f}  IC 95 % [{lo:+.4f}, {hi:+.4f}]")
        print(f"  pares con efecto POSITIVO            : {pos}/{len(efectos)} = {pos/len(efectos):.1%}")
        cruza = lo <= 0 <= hi
        veredicto = ("NO se distingue de cero" if cruza else
                     ("POR ENCIMA de la tasa base" if statistics.fmean(efectos) > 0 else "POR DEBAJO de la tasa base"))
        print(f"  veredicto                            : {veredicto}\n")
        out[campo] = {"clients": con_gustos, "foods_per_client_mean": statistics.fmean(tamanos),
                      "pairs": len(efectos), "effect": statistics.fmean(efectos), "ci95": [lo, hi],
                      "positive_fraction": pos / len(efectos), "verdict": veredicto,
                      "top": sorted(detalle, key=lambda d: -abs(d["effect"]))[:12]}

    pos_ok = out.get("liked_foods", {}).get("ci95", [0, 0])[0] > 0
    neg_ok = out.get("disliked_foods", {}).get("ci95", [0, 0])[1] < 0
    print("## Lectura conjunta\n")
    print(f"  control (los NEGATIVOS salen por debajo): {'SI' if neg_ok else 'NO'}")
    if not neg_ok:
        print("  -> si el control no sale, la medicion no esta bien montada y la mitad positiva TAMPOCO vale.")
    print(f"  los POSITIVOS salen por encima          : {'SI' if pos_ok else 'NO'}")
    out["control_passes"] = bool(neg_ok)
    out["positive_effect_confirmed"] = bool(pos_ok and neg_ok)
    # Los flotantes se REDONDEAN antes de escribir: una fraccion como 0,066796875 son nueve digitos seguidos y
    # el detector de telefonos de la auditoria PII los marca. No es un falso positivo del detector: es ruido
    # nuestro, y la precision de mas no aporta nada a una cifra que se lee al cuarto decimal.
    def redondear(x):
        if isinstance(x, float):
            return round(x, 4)
        if isinstance(x, dict):
            return {k: redondear(v) for k, v in x.items()}
        if isinstance(x, list):
            return [redondear(v) for v in x]
        return x

    args.out.write_text(json.dumps(redondear(out), ensure_ascii=False, indent=1) + chr(10),
                        encoding="utf-8", newline=chr(10))
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
