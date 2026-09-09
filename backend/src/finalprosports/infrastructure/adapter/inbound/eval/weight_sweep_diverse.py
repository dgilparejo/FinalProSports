# -*- coding: utf-8 -*-
"""Bloque 1.1 -- el barrido de pesos, rehecho SOBRE D3 y con todos los pesos NOMBRADOS.

Dos defectos del barrido anterior, y los dos cambian el resultado:

1. **El vecindario.** Los pesos de `method`, `height` y `sport` se pusieron a 0,00 midiendo el J top-1 sobre el
   vecindario que produce el motor actual, el que concentra veinte huecos en siete clientes. La ablacion del punto 2
   mostro que esa concentracion deforma la medicion hasta invertir el signo de la contribucion de la similitud entera.
   Aqui se barre sobre **D3** (un caso por cliente, agotando el objetivo correcto antes de admitir a nadie de fuera),
   que es el brazo entregable.

2. **La rama «sin el rasgo» no estaba construida sin el rasgo.** `AttributeWeights` trae `body_type = 0.10` por
   defecto, asi que `AttributeWeights(**BASE)` NO es «los cinco originales»: es la configuracion actual escrita de otra
   manera. Con eso, tres filas de la rejilla eran la misma configuracion y la pregunta «influye body_type?» comparaba
   0,10 contra 0,10 y respondia que no. **Toda configuracion se construye nombrando TODOS los pesos, el cero incluido**
   (`_w()`), y el propio programa lo comprueba antes de medir nada (`_assert_grid_is_distinct`).

Ademas, y porque D3 agota el mismo objetivo antes de salir de el, **el filtro por objetivo se comporta casi como un
veto**: el 0,45 de `goal` puede estar pagando por algo que la seleccion de candidatos ya garantiza. Por eso la rejilla
lo baja hasta 0,00.

Protocolo: particion POR CLIENTE con semilla fija (ningun cliente en los dos lados, y se afirma la interseccion
vacia), se elige sobre DESARROLLO y el APARTADO se mide UNA sola vez. Se reporta el J de la PROPUESTA COMPLETA -- que
es lo que decide -- y ademas el J top-1, para poder comparar con la cifra publicada.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.weight_sweep_diverse [--sample 150]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.domain.composition.policy.attribute_similarity_policy import AttributeWeights, DEFAULT_WEIGHTS
from finalprosports.domain.model import CaseQuery, RestrictionMode
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import (apply_plausibility, as_of_profile, composer_like, key_set, setup)
from finalprosports.infrastructure.adapter.inbound.eval.near_duplicate_leak import paired_ci
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard
from finalprosports.domain.composition.policy.neighbourhood_policy import OVERFETCH, select
from finalprosports.infrastructure.config.paths import dataset_dir

SEED = 42
DATASET_DIR = dataset_dir()

# TODOS los pesos, con su valor por defecto EXPLICITO. Ninguna configuracion se construye por omision.
ALL = dict(goal=0.45, sex=0.15, age=0.20, activity=0.10, restrictions=0.10,
           method=0.0, body_type=0.0, height=0.0, sport=0.0,
           weight=0.0, fat=0.0, muscle=0.0, visceral=0.0, metabolic_age=0.0, basal_met=0.0, hydration=0.0,
           likes=0.0, labs=0.0)


def _w(**overrides) -> AttributeWeights:
    """La UNICA forma de construir una configuracion en este modulo: se parte de los dieciseis pesos nombrados."""
    unknown = set(overrides) - set(ALL)
    assert not unknown, f"peso desconocido: {unknown}"
    return AttributeWeights(**{**ALL, **overrides})


def _assert_grid_is_distinct(grid) -> None:
    """Dos filas con los mismos pesos son la misma medicion escrita dos veces, y fue exactamente el defecto de ayer."""
    seen = {}
    for nombre, w in grid:
        key = tuple(sorted((f, getattr(w, f)) for f in ALL))
        if key in seen:
            raise AssertionError(f"«{nombre}» tiene los MISMOS pesos que «{seen[key]}»: la rejilla se mide dos veces")
        seen[key] = nombre


def partition(queries):
    codes = sorted({q.client_code for q in queries})
    random.Random(SEED).shuffle(codes)
    cut = int(len(codes) * 0.6)
    dev, hold = set(codes[:cut]), set(codes[cut:])
    assert not (dev & hold), "un cliente en los dos lados"
    return ([q for q in queries if q.client_code in dev], [q for q in queries if q.client_code in hold], dev, hold)


def d3(repo, pid, perfil, goal, k, exclude, enrich=None):
    """El brazo entregable: candidatos por similitud descendente, un caso por cliente, PUREZA primero.

    `enrich` puebla el lado del CASO con lo que `CANDIDATE_SQL` no trae. Hace falta para los rasgos cuyo dato no es
    una columna del perfil sino una serie fechada: sin el, el rasgo nunca seria evaluable en ningun par y el barrido
    diria «no aporta» por un motivo que no es el que se quiere medir. Se aplica ANTES de puntuar, que es donde
    importa.
    """
    if enrich is not None:
        cands = repo.find_similar(pid, CaseQuery(profile=perfil), k * OVERFETCH, exclude, enrich=enrich)
    else:
        cands = (repo.find_similar(pid, CaseQuery(profile=perfil), k * OVERFETCH, exclude, enrich=enrich)
             if enrich is not None else repo.find_similar(pid, CaseQuery(profile=perfil), k * OVERFETCH, exclude))
    return select(cands, goal, k).cases


def case_enricher(root, pid):
    """Puebla cada candidato con sus gustos y con sus analiticas VIGENTES a la fecha de SU dieta.

    Los gustos son una columna y llegarian igual; las analiticas no, y son las que obligan a esto. La regla temporal
    es la misma que en el lado de la consulta -- la mas reciente ANTERIOR a la fecha de ESA dieta --, y aqui se ve por
    que tiene que ser por candidato: dos dietas del mismo cliente separadas por dos anos ven analiticas distintas.

    Sin esto el rasgo `labs` no seria evaluable en NINGUN par y el barrido diria «no aporta» por un motivo que no es
    el que se quiere medir.
    """
    import dataclasses as _dc

    from finalprosports.domain.composition.policy.lab_measurement_policy import as_of as _lab_as_of
    from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import _labs
    from finalprosports.infrastructure.adapter.outbound.persistence.service.client.client_repository_output_adapter import (
        ClientRepositoryOutputAdapter)
    labs, spans = _labs(root, pid)
    dates = root.case_repository.doc_dates(pid)
    gustos = ClientRepositoryOutputAdapter(root.case_repository._sf).liked_food_ids_by_client(pid)   # noqa: SLF001
    cache = {}

    def enrich(c):
        if c.diet_id in cache:
            return cache[c.diet_id]
        code = c.diet_id.split("::")[0]
        vigentes = _lab_as_of(labs.get(code, ()), dates.get(c.diet_id))
        nuevo = _dc.replace(c, profile=_dc.replace(
            c.profile, liked_food_ids=gustos.get(code, ()),
            lab_values={k: v.value for k, v in vigentes.items()} or None,
            lab_spans=spans if vigentes else None))
        cache[c.diet_id] = nuevo
        return nuevo
    return enrich


def evaluate(root, pid, profiles, sample, weights, rules, catalog, composer, validador, env, svc, k, arm="D3", enrich=None):
    from finalprosports.infrastructure.adapter.outbound.persistence.service.case.retrieval_strategy_adapters import (
        AttributeCaseRepositoryAdapter)
    repo = AttributeCaseRepositoryAdapter(root.case_repository._sf, weights=weights)      # noqa: SLF001
    js_prop, js_top1, stds, per_query = [], [], [], {}
    for q in sample:
        perfil = as_of_profile(root, pid, profiles[q.client_code], q.goal, q.id)
        excl = svc.mandatory_exclusions(pid, perfil) | {q.id}
        casos = d3(repo, pid, perfil, q.goal, k, frozenset(excl), enrich) if arm == "D3" else \
            repo.find_similar(pid, CaseQuery(profile=perfil), k, frozenset(excl))
        if len(casos) < 3:
            continue
        oculta = key_set(q)
        js_top1.append(jaccard(key_set(casos[0].diet), oculta))
        stds.append(statistics.pstdev([c.score.total for c in casos]))
        cruda = composer.propose(perfil, casos, rules)
        plaus, _ = apply_plausibility(cruda, casos, env, catalog)
        d = to_diet(validador.validate(plaus, rules, perfil, cases=casos), q.id + "::x")
        j = jaccard(key_set(d), oculta)
        js_prop.append(j)
        per_query[q.id] = j
    return {"j_propuesta": statistics.fmean(js_prop), "j_top1": statistics.fmean(js_top1),
            "std_vecindario": statistics.fmean(stds), "n": len(js_prop), "_per_query": per_query}


def build_grid() -> list[tuple[str, AttributeWeights]]:
    # La fila «actual» ES «+complexion 0,10»: la configuracion entregada son los cinco originales mas la complexion.
    # No se escribe dos veces -- el guarda de rejilla lo rechaza, y con razon: era justo el defecto de ayer.
    # Desde el 2026-08-30 la configuracion ENTREGADA son los cinco originales; la de la complexion es la ANTERIOR.
    grid = [("ENTREGADA = los cinco originales", _w()),
            ("anterior (cinco + complexion 0,10)", _w(body_type=0.10))]
    for nombre, extra in (("+metodo 0,10", dict(method=0.10)),
                          ("+altura 0,10", dict(height=0.10)), ("+deporte 0,10", dict(sport=0.10)),
                          ("+complexion 0,20", dict(body_type=0.20)),
                          ("+los cuatro 0,05", dict(method=0.05, body_type=0.05, height=0.05, sport=0.05)),
                          ("+los cuatro 0,10", dict(method=0.10, body_type=0.10, height=0.10, sport=0.10)),
                          # --- bascula (bloque 0): siete rasgos nuevos, uno a uno y en grupo
                          ("+peso 0,10", dict(weight=0.10)), ("+grasa 0,10", dict(fat=0.10)),
                          ("+musculo 0,10", dict(muscle=0.10)), ("+visceral 0,10", dict(visceral=0.10)),
                          ("+edad metabolica 0,10", dict(metabolic_age=0.10)),
                          ("+basal 0,10", dict(basal_met=0.10)), ("+hidratacion 0,10", dict(hydration=0.10)),
                          ("+bascula: peso+grasa 0,10", dict(weight=0.10, fat=0.10)),
                          ("+bascula: los siete 0,05", dict(weight=0.05, fat=0.05, muscle=0.05, visceral=0.05,
                                                            metabolic_age=0.05, basal_met=0.05, hydration=0.05)),
                          ("+complexion 0,10 +peso 0,10", dict(body_type=0.10, weight=0.10)),
                          ("+complexion 0,10 +grasa 0,10", dict(body_type=0.10, fat=0.10)),
                          # --- las dos entradas nuevas de la 2a ronda
                          ("+gustos 0,10", dict(likes=0.10)), ("+gustos 0,20", dict(likes=0.20)),
                          ("+analiticas 0,10", dict(labs=0.10)), ("+analiticas 0,20", dict(labs=0.20)),
                          ("+gustos 0,10 +analiticas 0,10", dict(likes=0.10, labs=0.10))):
        grid.append((nombre, _w(**extra)))
    # el 0,45 del objetivo: bajo D3 la seleccion ya agota el objetivo correcto, asi que el peso puede sobrar
    for v in (0.30, 0.15, 0.00):
        grid.append((f"objetivo={v:.2f} (+complexion 0,10)", _w(goal=v, body_type=0.10)))
        grid.append((f"objetivo={v:.2f} (cinco originales)", _w(goal=v)))
    for campo, valores in (("age", (0.10, 0.30)), ("sex", (0.05, 0.25)),
                           ("activity", (0.00, 0.20)), ("restrictions", (0.00, 0.20))):
        for v in valores:
            grid.append((f"{campo}={v:.2f} (+complexion 0,10)", _w(**{campo: v}, body_type=0.10)))
    _assert_grid_is_distinct(grid)
    return grid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=150)
    ap.add_argument("--arm", choices=("D3", "motor"), default="D3")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "weight_sweep_d3.json")
    ap.add_argument("--rows", nargs="*", default=None,
                    help="mide solo las filas cuyo nombre empiece por alguno de estos prefijos (1.2: aislar el brazo)")
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    catalog, params = root.catalog, root.composer.params
    composer = composer_like(root, params)
    validador = DietValidator(catalog, RestrictionMode.STRICT, True)
    env = root.envelope.load(pid)
    svc = root.retrieve_similar_cases_service
    dev, hold, dev_codes, hold_codes = partition(queries)
    rng = random.Random(SEED)
    dev_s = rng.sample(dev, min(args.sample, len(dev)))
    hold_s = rng.sample(hold, min(args.sample, len(hold)))
    print(f"brazo: {args.arm} · k = {params.k}")
    print(f"particion POR CLIENTE · desarrollo {len(dev_codes)} clientes / {len(dev)} consultas · "
          f"apartado {len(hold_codes)} clientes / {len(hold)} consultas")
    print(f"interseccion de clientes entre los dos lados: {len(dev_codes & hold_codes)}  (tiene que ser 0)")
    print(f"muestra: {len(dev_s)} desarrollo · {len(hold_s)} apartado\n")

    enrich = case_enricher(root, pid)
    grid = build_grid()
    if args.rows:
        grid = [(n, w) for n, w in grid if any(n.startswith(pref) for pref in args.rows)]
    print(f"rejilla de {len(grid)} configuraciones, todas con los {len(ALL)} pesos nombrados y todas distintas\n")
    print(f"{'configuracion':40}{'J propuesta':>13}{'J top-1':>10}{'std vecind.':>13}{'n':>6}")
    resultados = []
    for nombre, w in grid:
        r = evaluate(root, pid, profiles, dev_s, w, rules, catalog, composer, validador, env, svc, params.k, args.arm, enrich)
        resultados.append((nombre, w, r))
        print(f"  {nombre:38}{r['j_propuesta']:>13.4f}{r['j_top1']:>10.4f}{r['std_vecindario']:>13.5f}{r['n']:>6}")

    mejor = max(resultados, key=lambda x: x[2]["j_propuesta"])
    actual = next(x for x in resultados if x[0].startswith("ENTREGADA"))
    print(f"\nelegida sobre DESARROLLO por J de la propuesta: {mejor[0]}")
    if mejor[0] == actual[0]:
        print("  -> la configuracion ENTREGADA gana el barrido; no hay cambio que medir en el apartado")

    print("\nmedido UNA sola vez sobre el APARTADO:")
    r_act = evaluate(root, pid, profiles, hold_s, actual[1], rules, catalog, composer, validador, env, svc, params.k, args.arm, enrich)
    r_mej = evaluate(root, pid, profiles, hold_s, mejor[1], rules, catalog, composer, validador, env, svc, params.k, args.arm, enrich)
    print(f"  actual  J propuesta {r_act['j_propuesta']:.4f}  top-1 {r_act['j_top1']:.4f}  n={r_act['n']}")
    print(f"  elegida J propuesta {r_mej['j_propuesta']:.4f}  top-1 {r_mej['j_top1']:.4f}  n={r_mej['n']}")
    comun = sorted(set(r_act["_per_query"]) & set(r_mej["_per_query"]))
    d = [r_mej["_per_query"][q] - r_act["_per_query"][q] for q in comun]
    media, lo, hi = paired_ci(d)
    print(f"  elegida - actual (PAREADO sobre las mismas {len(comun)} consultas): {media:+.4f}  IC 95 % [{lo:+.4f}, {hi:+.4f}]")

    args.out.write_text(json.dumps(
        {"arm": args.arm, "k": params.k, "seed": SEED,
         "partition": {"dev_clients": len(dev_codes), "hold_clients": len(hold_codes),
                       "dev_queries": len(dev), "hold_queries": len(hold), "overlap": len(dev_codes & hold_codes)},
         "weights_named": sorted(ALL),
         "dev": {n: {k: v for k, v in r.items() if k != "_per_query"} for n, _, r in resultados},
         "chosen": mejor[0],
         "holdout": {"actual": {k: v for k, v in r_act.items() if k != "_per_query"},
                     "chosen": {k: v for k, v in r_mej.items() if k != "_per_query"},
                     "paired_diff": media, "ci95": [lo, hi], "n_paired": len(comun)}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
