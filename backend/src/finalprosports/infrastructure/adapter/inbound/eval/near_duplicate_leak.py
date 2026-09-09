"""Cuanta fuga mete en la evaluacion la REUTILIZACION LITERAL de dietas entre clientes distintos.

El protocolo LOO excluye tres cosas: la dieta oculta, las demas del mismo cliente y las de su grupo de plantilla. Eso
cubre la copia declarada. Lo que no cubre es que el profesional escriba la MISMA dieta para dos personas sin que el
corpus lo marque: hay 19 pares de dietas identicas (J = 1,0 sobre (franja, alimento)) entre clientes distintos y
ninguno lleva `template_group_id`. Para esas consultas la respuesta esta literalmente dentro del conjunto recuperable
y cualquier metrica de solapamiento la premia sin que el sistema haya generalizado nada.

Este modulo mide dos cosas y no cambia el motor:

  1. **exposicion** -- cuantas de las consultas tienen un gemelo recuperable, a J >= 0,90 y a J >= 0,98;
  2. **efecto** -- el criterio de exito completo (suelo, copiar top-1, compositor, entregada, techo) recalculado
     anadiendo esos gemelos a las exclusiones, con diferencias PAREADAS sobre las mismas consultas.

La comparacion se hace sobre las consultas EXPUESTAS y sobre el total, porque son dos preguntas distintas: cuanto se
mueve el titular publicado, y cuanto se movia lo que la fuga tocaba.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.near_duplicate_leak [--threshold 0.90]
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import random
import statistics
import sys
from pathlib import Path

from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.domain.model import RestrictionMode
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import (apply_plausibility, composer_like, key_set, setup)
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard

BOOTSTRAP = 10_000
SEED = 42


def signature(diet) -> frozenset:
    """(franja, alimento) de una dieta. Es la firma con la que se detecto la reutilizacion literal."""
    return frozenset((m.slot.value, i.food_id) for m in diet.meals for i in m.items if i.food_id is not None)


def paired_ci(diffs: list[float], seed: int = SEED) -> tuple[float, float, float]:
    if not diffs:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(statistics.mean(rng.choices(diffs, k=n)) for _ in range(BOOTSTRAP))
    return statistics.mean(diffs), means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=float, default=0.90, help="J a partir del cual una dieta ajena cuenta como gemela")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    catalog = root.catalog
    params = root.composer.params
    composer = composer_like(root, params)
    svc = root.retrieve_similar_cases_service
    validador = DietValidator(catalog, RestrictionMode.STRICT, True)
    env = root.envelope.load(pid) if root.envelope is not None else None
    assert env is not None, 'falta plausibility_envelope.json'
    # El TECHO no entra en esta comparacion y no es un olvido: se calcula sobre las OTRAS dietas del mismo
    # cliente (`others` en loo_harness), nunca sobre el conjunto recuperable, asi que excluir gemelos ajenos
    # no puede moverlo. Es identico en los dos mundos por construccion.
    sigs = {d.id: signature(d) for d in diets.values()}

    # --- 1. exposicion -------------------------------------------------------------------------------------------
    gemelos: dict[str, set[str]] = {}
    expuestas_90, expuestas_98 = [], []
    for q in queries:
        propia = sigs[q.id]
        base = svc.mandatory_exclusions(pid, dataclasses.replace(profiles[q.client_code], goal=q.goal)) | {q.id}
        cerca = set()
        mejor = 0.0
        for did, s in sigs.items():
            if did in base or diets[did].client_code == q.client_code:
                continue
            j = jaccard(propia, s)
            if j >= args.threshold:
                cerca.add(did)
            mejor = max(mejor, j)
        gemelos[q.id] = cerca
        if mejor >= 0.90:
            expuestas_90.append(q.id)
        if mejor >= 0.98:
            expuestas_98.append(q.id)

    n = len(queries)
    print(f"consultas: {n}")
    print(f"  con al menos una dieta AJENA recuperable a J >= 0,90: {len(expuestas_90)} ({100*len(expuestas_90)/n:.1f} %)")
    print(f"  con al menos una dieta AJENA recuperable a J >= 0,98: {len(expuestas_98)} ({100*len(expuestas_98)/n:.1f} %)")
    print(f"  gemelos recuperables por consulta expuesta: mediana "
          f"{statistics.median([len(gemelos[q]) for q in expuestas_90]) if expuestas_90 else 0:.0f}")

    # --- 2. efecto -----------------------------------------------------------------------------------------------
    rng = random.Random(SEED)
    filas: dict[str, dict[str, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    expuestas = set(expuestas_90)
    for q in queries:
        perfil = dataclasses.replace(profiles[q.client_code], goal=q.goal)
        oculta = key_set(q)
        base = svc.mandatory_exclusions(pid, perfil) | {q.id}
        for etiqueta, extra in (("con fuga", frozenset()), ("sin gemelos", frozenset(gemelos[q.id]))):
            excl = base | extra
            casos = root.case_repository.find_similar(pid, svc.query_for(perfil), params.k, frozenset(excl))
            if not casos:
                continue
            filas[etiqueta]["copy_top1"].append(jaccard(key_set(casos[0].diet), oculta))
            propuesta = composer.propose(perfil, casos, rules)
            filas[etiqueta]["composer"].append(jaccard(key_set(to_diet(propuesta, q.id + "::prop")), oculta))
            plaus, _ = apply_plausibility(propuesta, casos, env, catalog)
            entregada = validador.validate(plaus, rules, perfil, cases=casos)
            filas[etiqueta]["entregada"].append(jaccard(key_set(to_diet(entregada, q.id + "::ent")), oculta))
            permitidas = [d for d in diets if d not in excl]
            mismo = [d for d in permitidas if diets[d].goal == q.goal] or permitidas
            filas[etiqueta]["floor"].append(jaccard(key_set(diets[rng.choice(mismo)]), oculta))
            filas[etiqueta]["_id"].append(q.id)

    print(f"\n{'variante':16}{'con fuga':>12}{'sin gemelos':>14}{'diferencia':>13}{'IC 95 % pareado':>26}")
    resumen = {}
    for var in ("floor", "copy_top1", "composer", "entregada"):
        a, b = filas["con fuga"][var], filas["sin gemelos"][var]
        m = min(len(a), len(b))
        d = [y - x for x, y in zip(a[:m], b[:m])]
        media, lo, hi = paired_ci(d)
        resumen[var] = {"con_fuga": statistics.mean(a[:m]), "sin_gemelos": statistics.mean(b[:m]),
                        "diff": media, "ci95": [lo, hi], "n": m}
        print(f"  {var:14}{statistics.mean(a[:m]):>12.4f}{statistics.mean(b[:m]):>14.4f}{media:>13.4f}"
              f"{f'[{lo:+.4f}, {hi:+.4f}]':>26}")

    ids = filas["con fuga"]["_id"]
    sub = [i for i, q in enumerate(ids) if q in expuestas]
    if sub:
        print(f"\nsolo sobre las {len(sub)} consultas EXPUESTAS:")
        for var in ("floor", "copy_top1", "composer", "entregada"):
            a, b = filas["con fuga"][var], filas["sin gemelos"][var]
            d = [b[i] - a[i] for i in sub if i < len(a) and i < len(b)]
            media, lo, hi = paired_ci(d)
            print(f"  {var:14}{statistics.mean(a[i] for i in sub):>12.4f}"
                  f"{statistics.mean(b[i] for i in sub):>14.4f}{media:>13.4f}{f'[{lo:+.4f}, {hi:+.4f}]':>26}")
            resumen[var + "_expuestas"] = {"diff": media, "ci95": [lo, hi], "n": len(d)}

    # el titular: compositor - copiar top-1, en los dos mundos
    print()
    for etiqueta in ("con fuga", "sin gemelos"):
        d = [c - t for c, t in zip(filas[etiqueta]["composer"], filas[etiqueta]["copy_top1"])]
        media, lo, hi = paired_ci(d)
        print(f"  titular (compositor − copiar top-1) {etiqueta:12}: {media:+.4f} [{lo:+.4f}, {hi:+.4f}]  n={len(d)}")
        resumen[f"titular_{etiqueta.replace(' ', '_')}"] = {"diff": media, "ci95": [lo, hi], "n": len(d)}

    resumen["exposicion"] = {"queries": n, "j090": len(expuestas_90), "j098": len(expuestas_98),
                             "threshold": args.threshold}
    if args.out:
        args.out.write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
