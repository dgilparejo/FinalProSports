"""D en los objetivos ESCASOS: estratificacion, tres variantes de relleno y el umbral de pureza.

El +0,0109 de D sobre A es un agregado sobre 815 consultas dominado por volumen (342) y definicion (331). En los
objetivos con pocos clientes, exigir un caso por cliente no baja el k -- siempre llega a 20 -- sino que rompe la
PUREZA: la recuperacion no filtra el objetivo de forma dura, asi que rellena con clientes de otros objetivos. Medido:
keto pasa de 98,9 % a 65,0 % del mismo objetivo, descarga de 34,4 % a 20,0 %.

Tres variantes de relleno, sobre las consultas afectadas:

  D1 · la actual        : k = 20, admitiendo un cliente por hueco aunque sea de otro objetivo.
  D2 · pureza estricta  : k = numero de clientes del propio objetivo (13 en keto, 4 en descarga, 1 en hipocalorica).
                          Menos votantes, todos del regimen correcto.
  D3 · pureza primero   : k = 20, pero antes de admitir un cliente de OTRO objetivo se agotan las demas versiones de
                          los clientes del objetivo correcto. Pierde independencia entre votantes, no pierde regimen.

Y el umbral de pureza: por debajo de que fraccion de casos del propio objetivo una propuesta deja de ser lo que dice
ser. Se reporta cuantas consultas caerian bajo cada umbral candidato; la decision es de diseno.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.scarce_goals
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import statistics
import sys
from pathlib import Path

from finalprosports.application.service.validation.diet_validator import DietValidator
from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.domain.composition.policy.neighbourhood_policy import select
from finalprosports.domain.model import RestrictionMode
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import (apply_plausibility, composer_like, key_set, setup)
from finalprosports.infrastructure.adapter.inbound.eval.near_duplicate_leak import paired_ci
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_ablation import wilcoxon
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard

UMBRALES = (0.90, 0.80, 0.70, 0.60, 0.50)


def variants(cands, goal, k):
    """D1, D2 y D3 a partir de los MISMOS candidatos ordenados por similitud."""
    del_objetivo = [c for c in cands if c.diet.goal == goal]
    otros = [c for c in cands if c.diet.goal != goal]

    def uno_por_cliente(pool, k, vistos=None):
        vistos = set() if vistos is None else set(vistos)
        out = []
        for c in pool:
            if c.diet.client_code in vistos:
                continue
            vistos.add(c.diet.client_code)
            out.append(c)
            if len(out) == k:
                break
        return out, vistos

    d1, _ = uno_por_cliente(cands, k)
    d2, _ = uno_por_cliente(del_objetivo, k)                      # se queda con los que haya
    # D3 ya NO se implementa aqui: es la politica de dominio que el motor aplica. Tener dos
    # implementaciones de lo que se entrega es como se acaba midiendo una cosa y sirviendo otra.
    d3 = select(cands, goal, k).cases
    return {"D1": tuple(d1), "D2": tuple(d2), "D3": tuple(d3)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    catalog, params = root.catalog, root.composer.params
    composer = composer_like(root, params)
    validador = DietValidator(catalog, RestrictionMode.STRICT, True)
    env = root.envelope.load(pid)
    svc = root.retrieve_similar_cases_service
    k = params.k

    def entregada(perfil, casos, qid):
        cruda = composer.propose(perfil, casos, rules)
        plaus, _ = apply_plausibility(cruda, casos, env, catalog)
        return to_diet(validador.validate(plaus, rules, perfil, cases=casos), qid + "::x")

    por_obj = collections.defaultdict(lambda: {"A": [], "D": []})
    escasas = collections.defaultdict(lambda: collections.defaultdict(list))
    pureza_A, pureza_D = [], []
    for q in queries:
        perfil = dataclasses.replace(profiles[q.client_code], goal=q.goal)
        excl = svc.mandatory_exclusions(pid, perfil) | {q.id}
        oculta = key_set(q)
        cands = root.case_repository.find_similar(pid, svc.query_for(perfil), k * 8,
                                                  frozenset(svc.mandatory_exclusions(pid, perfil) | {q.id}))
        A = svc.retrieve(pid, perfil, k)
        v = variants(cands, q.goal, k)
        g = str(getattr(q.goal, "value", q.goal))
        por_obj[g]["A"].append(jaccard(key_set(entregada(perfil, A, q.id)), oculta))
        por_obj[g]["D"].append(jaccard(key_set(entregada(perfil, v["D1"], q.id)), oculta))
        pa = sum(1 for c in A if c.diet.goal == q.goal) / max(1, len(A))
        pd = sum(1 for c in v["D1"] if c.diet.goal == q.goal) / max(1, len(v["D1"]))
        pureza_A.append((g, pa))
        pureza_D.append((g, pd))
        if pd < 1.0:                                              # consulta afectada por el relleno
            for nombre, casos in v.items():
                if not casos:
                    continue
                escasas[g][nombre].append({
                    "j": jaccard(key_set(entregada(perfil, casos, q.id)), oculta),
                    "votantes": len({c.diet.client_code for c in casos}), "k": len(casos),
                    "pureza": sum(1 for c in casos if c.diet.goal == q.goal) / len(casos)})
            escasas[g]["A"].append({"j": por_obj[g]["A"][-1], "votantes": len({c.diet.client_code for c in A}),
                                    "k": len(A), "pureza": pa})

    print("## 1 · D − A estratificado por objetivo\n")
    print(f"{'objetivo':22}{'n':>5}{'A':>9}{'D':>9}{'D − A':>10}{'IC 95 %':>24}{'Wilcoxon':>11}")
    resumen = {"por_objetivo": {}}
    for g, r in sorted(por_obj.items(), key=lambda kv: -len(kv[1]["A"])):
        d = [x - y for x, y in zip(r["D"], r["A"])]
        media, lo, hi = paired_ci(d)
        p = wilcoxon(d)
        print(f"{g[:21]:22}{len(d):>5}{statistics.fmean(r['A']):>9.4f}{statistics.fmean(r['D']):>9.4f}"
              f"{media:>+10.4f}{f'[{lo:+.4f}, {hi:+.4f}]':>24}{p:>11.3g}")
        resumen["por_objetivo"][g] = {"n": len(d), "A": statistics.fmean(r["A"]), "D": statistics.fmean(r["D"]),
                                      "diff": media, "ci95": [lo, hi], "wilcoxon_p": p}

    print("\n## 2 · Las tres variantes en los objetivos escasos\n")
    print(f"{'objetivo':18}{'variante':10}{'n':>4}{'J':>9}{'votantes':>10}{'k':>6}{'pureza':>9}")
    resumen["variantes"] = {}
    for g, vs in escasas.items():
        for nombre in ("A", "D1", "D2", "D3"):
            xs = vs.get(nombre) or []
            if not xs:
                continue
            print(f"{g[:17]:18}{nombre:10}{len(xs):>4}{statistics.fmean(x['j'] for x in xs):>9.4f}"
                  f"{statistics.fmean(x['votantes'] for x in xs):>10.2f}{statistics.fmean(x['k'] for x in xs):>6.1f}"
                  f"{statistics.fmean(x['pureza'] for x in xs):>9.3f}")
            resumen["variantes"].setdefault(g, {})[nombre] = {
                "n": len(xs), "j": statistics.fmean(x["j"] for x in xs),
                "votantes": statistics.fmean(x["votantes"] for x in xs),
                "k": statistics.fmean(x["k"] for x in xs), "pureza": statistics.fmean(x["pureza"] for x in xs)}
    # agregado sobre TODAS las afectadas
    print()
    for nombre in ("A", "D1", "D2", "D3"):
        xs = [x for vs in escasas.values() for x in (vs.get(nombre) or [])]
        if xs:
            print(f"{'TODAS las afectadas':18}{nombre:10}{len(xs):>4}{statistics.fmean(x['j'] for x in xs):>9.4f}"
                  f"{statistics.fmean(x['votantes'] for x in xs):>10.2f}{statistics.fmean(x['k'] for x in xs):>6.1f}"
                  f"{statistics.fmean(x['pureza'] for x in xs):>9.3f}")
            resumen.setdefault("afectadas", {})[nombre] = {
                "n": len(xs), "j": statistics.fmean(x["j"] for x in xs),
                "votantes": statistics.fmean(x["votantes"] for x in xs),
                "pureza": statistics.fmean(x["pureza"] for x in xs)}

    print("\n## 3 · Cuantas consultas caerian bajo cada umbral de pureza\n")
    print(f"{'umbral':>8}{'con A':>10}{'con D1':>10}{'con D3':>10}")
    d3_pureza = []
    for g, vs in escasas.items():
        for x in (vs.get("D3") or []):
            d3_pureza.append(x["pureza"])
    resumen["umbrales"] = {}
    for u in UMBRALES:
        na = sum(1 for _, p in pureza_A if p < u)
        nd = sum(1 for _, p in pureza_D if p < u)
        n3 = sum(1 for p in d3_pureza if p < u)
        print(f"{u:>8.2f}{na:>10}{nd:>10}{n3:>10}")
        resumen["umbrales"][f"{u:.2f}"] = {"A": na, "D1": nd, "D3_afectadas": n3}
    if args.out:
        args.out.write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
