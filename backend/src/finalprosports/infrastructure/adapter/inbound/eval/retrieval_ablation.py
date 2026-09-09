"""PUNTO 2 · ¿El motor recupera casos parecidos, o hace consenso sobre el estrato del objetivo?

La hipotesis nace de dos medidas: la correlacion entre la puntuacion de similitud y el parecido real de las dietas es
+0,0429 (mediana +0,0196) y es NEGATIVA en el 44,2 % de las consultas. Si el orden que produce la similitud es
practicamente aleatorio, entonces lo que el compositor hace no es «componer a partir de los casos mas parecidos» sino
«componer a partir de veinte dietas cualesquiera del mismo objetivo», y eso es una afirmacion distinta y comprobable.

Tres brazos, TODO lo demas identico -- mismo compositor, mismos parametros, mismas reglas, misma envolvente, mismo
validador, mismas consultas, mismas exclusiones obligatorias:

    A) motor actual        : los k casos que entrega la recuperacion por atributos
    B) sin recuperacion    : k dietas al azar DENTRO del mismo objetivo
    C) sin nada            : k dietas al azar del corpus entero

B y C se repiten con varias semillas y se reporta la dispersion entre ellas, porque una sola muestra aleatoria no
distingue «no aporta» de «tuve suerte».

No se cambia nada del motor. Este modulo solo mide.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.retrieval_ablation [--seeds 5] [--out fichero.json]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import statistics
import sys
from pathlib import Path

from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.domain.model import RestrictionMode, RetrievedCase, SimilarityScore
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import (apply_plausibility, composer_like,
                                                                           family_set, food_set, key_set, setup)
from finalprosports.infrastructure.adapter.inbound.eval.near_duplicate_leak import paired_ci
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard

METRICS = ("normalized_key", "food_id", "familia")


def sets_of(diet, metric: str, catalog=None) -> frozenset:
    """Los MISMOS conjuntos que usa el arnes publicado, para que las cifras sean comparables con las suyas.

    La familia no esta en el item: se resuelve por el catalogo (`family_set`), igual que alli. Calcularla del atributo
    del item daba el conjunto vacio y un Jaccard de 0,0000 en los tres brazos, que es la clase de cero que parece un
    resultado y es un fallo de lectura.
    """
    if metric == "normalized_key":
        return key_set(diet)
    if metric == "food_id":
        return food_set(diet)
    return family_set(diet, catalog)


def as_cases(diets_by_id: dict, ids: list[str]) -> tuple[RetrievedCase, ...]:
    """Los mismos objetos que entrega la recuperacion, con la puntuacion neutralizada.

    La puntuacion se pone a 1,0 en los brazos aleatorios A PROPOSITO: el compositor pondera por similitud cuando
    `similarity_weighting` esta activo, y dejar la puntuacion real de un candidato tomado al azar mezclaria el efecto
    de la recuperacion con el de la ponderacion, que ya esta medido aparte y es plano.
    """
    return tuple(RetrievedCase(diets_by_id[i], SimilarityScore(0.0, 1.0, 1.0), n + 1) for n, i in enumerate(ids))


def wilcoxon(diffs: list[float]) -> float:
    """Wilcoxon de rangos con signo, dos colas, aproximacion normal con correccion de continuidad y de empates."""
    nz = [d for d in diffs if d != 0.0]
    n = len(nz)
    if n < 10:
        return float("nan")
    orden = sorted(range(n), key=lambda i: abs(nz[i]))
    rangos = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nz[orden[j + 1]]) == abs(nz[orden[i]]):
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            rangos[orden[k]] = r
        i = j + 1
    w_pos = sum(r for r, d in zip(rangos, nz) if d > 0)
    w_neg = sum(r for r, d in zip(rangos, nz) if d < 0)
    w = min(w_pos, w_neg)
    mu = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sigma == 0:
        return float("nan")
    z = (w - mu + 0.5) / sigma
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def diverse_cases(svc, pid, perfil, k):
    """El brazo E/D: los candidatos por similitud DESCENDENTE, admitiendo uno por cliente hasta llegar a k.

    Determinista: sin azar y sin semilla, misma salida ante la misma entrada. Es el unico de los brazos alternativos
    que puede entregarse, porque la memoria afirma que el sistema es reproducible ante la misma entrada.
    """
    vistos, elegidos = set(), []
    for c in svc._cases.find_similar(pid, svc.query_for(perfil), k * 8, frozenset()):    # noqa: SLF001 — crudo, sin la seleccion D3
        if c.diet.client_code in vistos:
            continue
        vistos.add(c.diet.client_code)
        elegidos.append(c)
        if len(elegidos) == k:
            break
    return tuple(elegidos)


def sweep_k(root, pid, diets, profiles, queries, rules, catalog, composer_base, validador, env, svc, ks, out):
    """Sensibilidad a k del motor y del brazo diverso.

    Con el motor, k = 20 son ~7 votantes efectivos; con seleccion diversa son 20. El k optimo con votantes
    independientes no tiene por que ser el mismo que con votantes repetidos, asi que se barre en los dos.
    """
    from finalprosports.domain.composition.policy.composition_policy import CompositionParams
    import dataclasses as dc
    filas = {}
    for k in ks:
        params = dc.replace(composer_base.params, k=k)
        composer = composer_like(root, params)
        for modo in ("motor", "diverso"):
            puntos = {m: [] for m in METRICS}
            votantes = []
            for q in queries:
                perfil = dc.replace(profiles[q.client_code], goal=q.goal)
                casos = svc.retrieve(pid, perfil, k) if modo == "motor" else diverse_cases(svc, pid, perfil, k)
                if not casos:
                    continue
                votantes.append(len({c.diet.client_code for c in casos}))
                cruda = composer.propose(perfil, casos, rules)
                plaus, _ = apply_plausibility(cruda, casos, env, catalog)
                d = to_diet(validador.validate(plaus, rules, perfil, cases=casos), q.id + "::x")
                for m in METRICS:
                    puntos[m].append(jaccard(sets_of(d, m, catalog), sets_of(q, m, catalog)))
            filas[(k, modo)] = ({m: statistics.fmean(v) for m, v in puntos.items()},
                                statistics.fmean(votantes), len(votantes))
    print(f"{'k':>4}  {'modo':10}{'votantes':>10}" + "".join(f"{m:>16}" for m in METRICS))
    for (k, modo), (medias, vot, n) in filas.items():
        print(f"{k:>4}  {modo:10}{vot:>10.2f}" + "".join(f"{medias[m]:>16.4f}" for m in METRICS) + f"   n={n}")
    if out:
        out.write_text(json.dumps({f"k={k}|{modo}": {"means": mm, "voters": vv, "n": nn}
                                   for (k, modo), (mm, vv, nn) in filas.items()},
                                  ensure_ascii=False, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=5, help="semillas para los brazos aleatorios")
    ap.add_argument("--limit", type=int, default=None, help="depuracion: solo las primeras N consultas")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--k-sweep", type=str, default=None,
                    help="lista de k separada por comas: mide SOLO el brazo diverso (E) y el motor a cada k")
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    catalog, params = root.catalog, root.composer.params
    composer = composer_like(root, params)
    validador = DietValidator(catalog, RestrictionMode.STRICT, True)
    env = root.envelope.load(pid) if root.envelope is not None else None
    assert env is not None, "falta plausibility_envelope.json"
    svc = root.retrieve_similar_cases_service
    if args.limit:
        queries = queries[:args.limit]

    # Brazo D: el MISMO orden por similitud, pero un caso por cliente. Separa las dos explicaciones posibles del
    # signo de A - B: si el dano viene de que la similitud concentra el vecindario, D recupera lo perdido; si viene
    # de que la similitud ordena mal, D se queda con A.
    if args.k_sweep:
        return sweep_k(root, pid, diets, profiles, queries, rules, catalog, composer, validador, env, svc,
                       [int(x) for x in args.k_sweep.split(",")], args.out)
    brazos = ["A_motor", "D_motor_diverso"] + [f"B_s{s}" for s in range(args.seeds)]              + [f"C_s{s}" for s in range(args.seeds)]
    puntos = {b: {m: [] for m in METRICS} for b in brazos}
    n_ok = 0

    for q in queries:
        perfil = dataclasses.replace(profiles[q.client_code], goal=q.goal)
        excl = svc.mandatory_exclusions(pid, perfil) | {q.id}
        permitidas = [i for i in diets if i not in excl]
        mismo_objetivo = [i for i in permitidas if diets[i].goal == q.goal] or permitidas
        casos_motor = svc.retrieve(pid, perfil, params.k)
        if not casos_motor:
            continue
        n_ok += 1
        objetivo = {m: sets_of(q, m, catalog) for m in METRICS}

        def entregada(casos):
            cruda = composer.propose(perfil, casos, rules)
            plaus, _ = apply_plausibility(cruda, casos, env, catalog)
            return to_diet(validador.validate(plaus, rules, perfil, cases=casos), q.id + "::x")

        for brazo in brazos:
            if brazo == "A_motor":
                casos = casos_motor
            elif brazo == "D_motor_diverso":
                casos = diverse_cases(svc, pid, perfil, params.k) or casos_motor
            else:
                # `random.Random(str)` siembra con un hash interno determinista. Usar `hash()` de Python NO vale:
                # para cadenas esta aleatorizado por proceso (PYTHONHASHSEED), y con el la misma orden daba
                # A - B = -0,0085 en una ejecucion y -0,0075 en la siguiente. Mismo signo y los IC solapados, pero
                # el proyecto exige que una reejecucion reproduzca las cifras.
                rng = random.Random(f"{q.id}|{brazo}")
                pozo = mismo_objetivo if brazo.startswith("B_") else permitidas
                casos = as_cases(diets, rng.sample(pozo, min(params.k, len(pozo))))
            d = entregada(casos)
            for m in METRICS:
                puntos[brazo][m].append(jaccard(sets_of(d, m, catalog), objetivo[m]))

    print(f"consultas: {n_ok} · k = {params.k} · semillas por brazo aleatorio: {args.seeds}\n")
    medias = {b: {m: statistics.fmean(v) for m, v in d.items()} for b, d in puntos.items()}
    resumen = {"queries": n_ok, "k": params.k, "seeds": args.seeds, "means": medias, "pairs": {}, "spread": {}}

    print(f"{'brazo':38}" + "".join(f"{m:>16}" for m in METRICS))
    print(f"  {'A · motor actual':36}" + "".join(f"{medias['A_motor'][m]:>16.4f}" for m in METRICS))
    print(f"  {'D · motor, un caso por cliente':36}" + "".join(f"{medias['D_motor_diverso'][m]:>16.4f}" for m in METRICS))
    for pref, etiqueta in (("B_", "B · azar dentro del mismo objetivo"), ("C_", "C · azar del corpus entero")):
        ss = [b for b in brazos if b.startswith(pref)]
        fila = [statistics.fmean(medias[b][m] for b in ss) for m in METRICS]
        disp = [statistics.pstdev([medias[b][m] for b in ss]) for m in METRICS]
        print(f"  {etiqueta:36}" + "".join(f"{x:>16.4f}" for x in fila))
        print(f"  {'  · dispersion entre semillas':36}" + "".join(f"{x:>16.5f}" for x in disp))
        resumen["spread"][pref] = {m: {"mean": fila[i], "pstdev": disp[i],
                                       "per_seed": [medias[b][m] for b in ss]} for i, m in enumerate(METRICS)}

    print(f"\n{'comparacion pareada':36}{'metrica':>16}{'diferencia':>13}{'IC 95 %':>24}{'Wilcoxon p':>13}")
    for m in METRICS:
        d = [x - y for x, y in zip(puntos["D_motor_diverso"][m], puntos["A_motor"][m])]
        media, lo, hi = paired_ci(d)
        print(f"  {'D − A (diversidad forzada)':34}{m:>16}{media:>+13.4f}{f'[{lo:+.4f}, {hi:+.4f}]':>24}"
              f"{wilcoxon(d):>13.3g}")
        resumen["pairs"][f"D - A | {m}"] = {"diff": media, "ci95": [lo, hi], "wilcoxon_p": wilcoxon(d), "n": len(d)}
    for pref, etiqueta in (("B_", "A − B (mismo objetivo al azar)"), ("C_", "A − C (corpus al azar)")):
        ss = [b for b in brazos if b.startswith(pref)]
        for m in METRICS:
            # se comparan las MEDIAS por consulta de las semillas: el estimador de «una dieta al azar», no una
            # realizacion concreta, que anadiria a la diferencia la varianza de un solo sorteo
            media_por_consulta = [statistics.fmean(puntos[b][m][i] for b in ss) for i in range(n_ok)]
            d = [x - y for x, y in zip(puntos["A_motor"][m], media_por_consulta)]
            media, lo, hi = paired_ci(d)
            p = wilcoxon(d)
            por_semilla = [statistics.fmean(x - y for x, y in zip(puntos["A_motor"][m], puntos[b][m])) for b in ss]
            print(f"  {etiqueta:34}{m:>16}{media:>+13.4f}{f'[{lo:+.4f}, {hi:+.4f}]':>24}{p:>13.3g}")
            if pref == "B_":
                dd = [x - y for x, y in zip(puntos["D_motor_diverso"][m], media_por_consulta)]
                m2, l2, h2 = paired_ci(dd)
                print(f"  {'D − B (diverso vs azar del objetivo)':34}{m:>16}{m2:>+13.4f}"
                      f"{f'[{l2:+.4f}, {h2:+.4f}]':>24}{wilcoxon(dd):>13.3g}")
                resumen["pairs"][f"D - B | {m}"] = {"diff": m2, "ci95": [l2, h2], "wilcoxon_p": wilcoxon(dd), "n": len(dd)}
            resumen["pairs"][f"{etiqueta} | {m}"] = {"diff": media, "ci95": [lo, hi], "wilcoxon_p": p, "n": len(d),
                                                    "per_seed_diff": por_semilla}
    if args.out:
        args.out.write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
