# -*- coding: utf-8 -*-
"""Bloques 1.4 a 1.7 -- el analisis de `arms_per_query.jsonl`. No mide nada: lee lo medido.

Se separa de la MEDICION a proposito. Medir tarda minutos y el analisis se reescribe varias veces; tenerlos
juntos obligaria a volver a medir cada vez que cambia una tabla, y entonces las cuatro respuestas podrian no venir del
mismo dato.

  1.4  estratificacion por objetivo: D3 - A pareado con IC en cada objetivo, con los escasos nombrados.
  1.5  D3 - B pareado con IC y Wilcoxon en las tres granularidades (se comparo por medias).
  1.6  D3 contra el TECHO, sobre el MISMO conjunto. El techo laxo sin vecino (0,2746) y el D3 (0,2850) se habian
       calculado sobre 741 y 815 consultas; una diferencia entre medias de conjuntos distintos no es una diferencia.
  1.7  umbrales de pureza: las dos fracciones, sus tablas de corte y las tres bandas de servicio.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.arms_report
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

from finalprosports.infrastructure.adapter.inbound.eval.near_duplicate_leak import paired_ci
from finalprosports.infrastructure.adapter.inbound.eval.retrieval_ablation import wilcoxon
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()
METRICS = ("normalized_key", "food_id", "familia")
CUTS = (0.90, 0.80, 0.70, 0.60, 0.50)
METRIC = "normalized_key"


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def paired(rows, a: str, b: str, metric: str):
    """b - a sobre las consultas donde LOS DOS brazos existen. Nunca entre medias de conjuntos distintos."""
    d = [r["arms"][b][metric] - r["arms"][a][metric] for r in rows if a in r["arms"] and b in r["arms"]]
    if not d:
        return None
    media, lo, hi = paired_ci(d)
    return {"n": len(d), "diff": media, "ci95": [lo, hi], "wilcoxon_p": wilcoxon(d)}


def fmt(res) -> str:
    if res is None:
        return "        —"
    star = "*" if res["ci95"][0] > 0 or res["ci95"][1] < 0 else " "
    return f"{res['diff']:+.4f} [{res['ci95'][0]:+.4f}, {res['ci95'][1]:+.4f}]{star} n={res['n']:>3} p={res['wilcoxon_p']:.2g}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arms", type=Path, default=DATASET_DIR / "arms_per_query.jsonl")
    ap.add_argument("--composer", type=Path, default=DATASET_DIR / "composer_per_query.jsonl")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "arms_report.json")
    ap.add_argument("--no-clean-ceiling", dest="clean_ceiling", action="store_false", default=True,
                    help="omite el techo LIMPIO (el unico calculo de este modulo que necesita la base de datos)")
    ap.add_argument("--near-duplicate", type=float, default=0.90,
                    help="J de firma (franja, alimento) a partir del cual una version del mismo cliente es casi-copia")
    args = ap.parse_args()

    rows = load(args.arms)
    print(f"consultas medidas: {len(rows)}")
    con_fecha = sum(1 for r in rows if r.get("has_doc_date"))
    con_causal = sum(1 for r in rows if "RS" in r.get("arms", {}))
    con_gustos = sum(1 for r in rows if r.get("has_likes"))
    print(f"  con fecha de documento: {con_fecha} · con brazo causal (>= 20 candidatos anteriores): {con_causal}")
    print(f"  consultas cuyo cliente tiene gustos positivos anotados: {con_gustos}")
    for arm in ("A0", "A", "B", "D1", "D3", "RS", "RR", "RB", "D3_sin_gustos", "G_SIM"):
        got = [r for r in rows if arm in r["arms"]]
        if got:
            print(f"  {arm:3}  n={len(got):>4}  " + "  ".join(
                f"{m} {statistics.fmean(r['arms'][arm][m] for r in got):.4f}" for m in METRICS))

    out = {"n": len(rows), "arm_means": {}}
    for arm in ("A0", "A", "B", "D1", "D3", "RS", "RR", "RB", "D3_sin_gustos", "G_SIM"):
        got = [r for r in rows if arm in r["arms"]]
        if got:
            out["arm_means"][arm] = {"n": len(got),
                                     **{m: statistics.fmean(r["arms"][arm][m] for r in got) for m in METRICS}}

    # ------------------------------------------------------------------------------------------------- 1.5 · D3 - B
    print("\n## 1.5 · D3 contra B (pareado, tres granularidades)\n")
    print(f"{'comparacion':16}{'metrica':16}  diferencia")
    out["pairwise"] = {}
    for a, b in (("A0", "D3"), ("A0", "A"), ("B", "D3"), ("A", "D3"), ("A", "D1"), ("D1", "D3"), ("A", "B"),
                 # LA RECENCIA CAUSAL contra la configuracion ENTREGADA. Todas se comparan contra D3 y entre si sobre
                 # las consultas donde los dos brazos existen: una consulta sin suficientes candidatos ANTERIORES no
                 # tiene brazo causal y no entra, en vez de rellenarse con posteriores.
                 ("D3", "RS"), ("D3", "RR"), ("D3", "RB"), ("RS", "RR"), ("RS", "RB"),
                 # LOS GUSTOS, cada via por separado. `D3_sin_gustos` es la ENTREGADA con el desempate apagado, asi
                 # que «D3 - D3_sin_gustos» es exactamente lo que aporta la via (b). `G_SIM` solo existe en las
                 # consultas cuyo cliente tiene lista, y ahi se compara contra D3 sobre esas mismas consultas.
                 ("D3_sin_gustos", "D3"), ("D3", "G_SIM")):
        for m in METRICS:
            res = paired(rows, a, b, m)
            out["pairwise"][f"{b}-{a}:{m}"] = res
            print(f"  {b} - {a:<11}{m:16}{fmt(res)}")
        print()

    # ------------------------------------------------------------------------------------- 1.4 · estratificacion
    print("## 1.4 · D3 - A por OBJETIVO (pareado, con IC)\n")
    by_goal = collections.defaultdict(list)
    for r in rows:
        by_goal[r["goal"]].append(r)
    print(f"{'objetivo':24}{'n':>6}{'A0':>9}{'D3':>9}   D3 - A0")
    out["by_goal"] = {}
    for goal in sorted(by_goal, key=lambda g: -len(by_goal[g])):
        g = [r for r in by_goal[goal] if "A0" in r["arms"] and "D3" in r["arms"]]
        if not g:
            continue
        res = paired(g, "A0", "D3", METRIC)
        a_mean = statistics.fmean(r["arms"]["A0"][METRIC] for r in g)
        d_mean = statistics.fmean(r["arms"]["D3"][METRIC] for r in g)
        out["by_goal"][goal] = {"n": len(g), "A": a_mean, "D3": d_mean, **(res or {})}
        print(f"  {goal:22}{len(g):>6}{a_mean:>9.4f}{d_mean:>9.4f}   {fmt(res)}")
    regres = [g for g, d in out["by_goal"].items() if d.get("ci95") and d["ci95"][1] < 0]
    print(f"\n  objetivos con REGRESION significativa (IC entero por debajo de 0): {regres or '(ninguno)'}")

    # ------------------------------------------------------------------------------------------ 1.6 · el techo
    print("\n## 1.6 · D3 contra el TECHO, sobre el MISMO conjunto\n")
    ceil = {}
    if args.composer.exists():
        for line in args.composer.open(encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            ceil[r["diet_id"]] = r
    # El techo LIMPIO: la media sobre las versiones del mismo cliente que NO son casi-copias de la oculta. Se
    # recalcula aqui, sobre las MISMAS consultas, porque compararlo con el valor publicado seria otra vez comparar
    # medias de conjuntos distintos, que es justo el defecto que este apartado viene a corregir.
    limpio, limpio_sin_nn = {}, {}
    if args.clean_ceiling:
        from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import key_set, setup
        from finalprosports.infrastructure.adapter.inbound.eval.near_duplicate_leak import signature
        from finalprosports.infrastructure.adapter.inbound.eval.retrieval_benchmark import jaccard as _j
        _root, _pid, _diets, _profiles, _queries, _ = setup()
        por_cliente = collections.defaultdict(list)
        for _d in _diets.values():
            if _d.template_group_id is None:
                por_cliente[_d.client_code].append(_d)
        firmas = {_d.id: signature(_d) for _d in _diets.values()}
        for _q in _queries:
            otras = [o for o in por_cliente[_q.client_code] if o.id != _q.id]
            limpias = [o for o in otras if _j(firmas[_q.id], firmas[o.id]) < args.near_duplicate]
            if limpias:
                oculta = key_set(_q)
                limpio[_q.id] = statistics.fmean(_j(key_set(o), oculta) for o in limpias)
                # ...y el que el titular cita como 0,2721: sin casi-copias Y ADEMAS sin el vecino mas cercano de lo
                # que queda. Son dos techos distintos y hay que decir cual es cual: quitar la casi-copia es raro
                # (casi nunca hay una), quitar el vecino mas cercano quita SIEMPRE el maximo. Por eso el «limpio»
                # sale ALTO -- se parece al techo CON vecino -- y el «limpio sin vecino» sale bajo.
                if len(limpias) > 1:
                    orden = sorted(limpias, key=lambda o: _j(key_set(o), oculta), reverse=True)
                    limpio_sin_nn[_q.id] = statistics.fmean(_j(key_set(o), oculta) for o in orden[1:])

    con_techo = [r for r in rows if "D3" in r["arms"] and ceil.get(r["diet_id"], {}).get("ceiling_excl_nn")]
    print(f"  consultas con techo sin vecino definido: {len(con_techo)} de {len(rows)}")
    if con_techo:
        d3 = [r["arms"]["D3"][METRIC] for r in con_techo]
        a = [r["arms"]["A0"][METRIC] for r in con_techo if "A0" in r["arms"]]
        techo = [ceil[r["diet_id"]]["ceiling_excl_nn"]["j_key"] for r in con_techo]
        techo_nn = [ceil[r["diet_id"]]["ceiling_incl_nn"]["j_key"] for r in con_techo]
        print(f"  sobre esas {len(con_techo)}:  D3 {statistics.fmean(d3):.4f} · motor anterior {statistics.fmean(a):.4f} · "
              f"techo sin vecino {statistics.fmean(techo):.4f} · techo con vecino {statistics.fmean(techo_nn):.4f}")
        for etiqueta, tabla in (("LIMPIO (sin casi-copias)", limpio),
                                ("LIMPIO SIN VECINO (sin casi-copias y sin el mas cercano)", limpio_sin_nn)):
            if not tabla:
                continue
            con_limpio = [r for r in con_techo if r["diet_id"] in tabla]
            d3_l = [r["arms"]["D3"][METRIC] for r in con_limpio]
            t_l = [tabla[r["diet_id"]] for r in con_limpio]
            dif = [x - y for x, y in zip(d3_l, t_l)]
            media, lo, hi = paired_ci(dif)
            pv = wilcoxon(dif)
            supera = "SUPERA" if lo > 0 else ("IGUALA" if hi > 0 else "NO alcanza")
            print(f"    n={len(con_limpio):>4}  techo {etiqueta}: D3 {statistics.fmean(d3_l):.4f} · "
                  f"techo {statistics.fmean(t_l):.4f}  -> {media:+.4f} IC [{lo:+.4f}, {hi:+.4f}] p={pv:.2g}  {supera}")
            out["vs_" + etiqueta.split()[0].lower() + ("_sin_nn" if "SIN VECINO" in etiqueta else "")] = {
                "n": len(d3_l), "diff": media, "ci95": [lo, hi], "p": pv,
                "d3": statistics.fmean(d3_l), "ceiling": statistics.fmean(t_l)}
        for nombre, serie in (("techo SIN vecino", techo), ("techo CON vecino", techo_nn)):
            media, lo, hi = paired_ci([x - y for x, y in zip(d3, serie)])
            p = wilcoxon([x - y for x, y in zip(d3, serie)])
            supera = "SUPERA" if lo > 0 else ("IGUALA" if hi > 0 else "NO alcanza")
            print(f"    D3 - {nombre:18}: {media:+.4f}  IC [{lo:+.4f}, {hi:+.4f}]  p={p:.2g}   -> {supera}")
            out[f"vs_{nombre.replace(' ', '_')}"] = {"n": len(d3), "diff": media, "ci95": [lo, hi], "p": p,
                                                     "d3": statistics.fmean(d3), "ceiling": statistics.fmean(serie)}

    # ------------------------------------------------------------------------- los gustos: la metrica que si los ve
    con_lider = [r for r in rows if r.get("leaders")]
    if con_lider:
        print("")
        print("## Los GUSTOS positivos, medidos donde el desempate puede verse")
        print("")
        print("El Jaccard es sobre CONJUNTOS y el desempate reordena DENTRO del conjunto ya seleccionado, asi que no")
        print("puede moverlo: `D3 - D3_sin_gustos` da 0,0000 exacto en las 815 y eso es una propiedad, no un hallazgo.")
        print("Lo que el desempate cambia es QUE ALIMENTO ENCABEZA cada grupo, que es la linea que el cliente lee.")
        print("")
        con = [r["leaders"]["D3"] for r in con_lider]
        sin = [r["leaders"]["D3_sin_gustos"] for r in con_lider]
        d = [a - b for a, b in zip(con, sin)]
        media, lo, hi = paired_ci(d)
        print(f"  consultas con gustos anotados            : {len(con_lider)}")
        print(f"  acierto del LIDER, con desempate         : {statistics.fmean(con):.4f}")
        print(f"  acierto del LIDER, sin desempate         : {statistics.fmean(sin):.4f}")
        print(f"  diferencia PAREADA                       : {media:+.4f}  IC 95 % [{lo:+.4f}, {hi:+.4f}]  "
              f"p={wilcoxon(d):.2g}")
        cambia = sum(1 for x in d if x != 0)
        print(f"  consultas en que el desempate cambia algo: {cambia} de {len(d)}")
        out["likes_tiebreak"] = {"queries": len(con_lider), "with": statistics.fmean(con), "without": statistics.fmean(sin),
                                 "diff": media, "ci95": [lo, hi], "changed": cambia}

    # -------------------------------------------------------------------------------------- 1.7 · pureza
    print("\n## 1.7 · Umbrales de PUREZA\n")
    print("Dos fracciones porque son dos preguntas: cuanto de lo que vota es del regimen pedido (pureza), y de")
    print("cuantas personas distintas viene ese voto (independencia). D3 rellena con OTRAS VERSIONES de los mismos")
    print("clientes antes de salir del objetivo, asi que puede ser puro y a la vez poco independiente.\n")
    out["purity"] = {}
    for campo, etiqueta in (("goal_diets_frac", "dietas del objetivo / k  (PUREZA)"),
                            ("goal_clients_frac", "clientes del objetivo / k  (INDEPENDENCIA)")):
        print(f"  {etiqueta}")
        print(f"    {'brazo':6}{'media':>9}" + "".join(f"{'<'+f'{c:.2f}':>10}" for c in CUTS))
        for arm in ("A0", "A", "D1", "D3"):
            vals = [r["purity"][arm][campo] for r in rows if arm in r.get("purity", {})]
            if not vals:
                continue
            fila = {"mean": statistics.fmean(vals), "n": len(vals),
                    "below": {f"{c:.2f}": sum(1 for v in vals if v < c) for c in CUTS}}
            out["purity"][f"{arm}:{campo}"] = fila
            print(f"    {arm:6}{fila['mean']:>9.3f}" + "".join(f"{fila['below'][f'{c:.2f}']:>10}" for c in CUTS))
        print()

    # las tres bandas, sobre D3, que es el brazo entregable
    print("  BANDAS DE SERVICIO propuestas (sobre D3)\n")
    bandas = collections.Counter()
    detalle = collections.defaultdict(collections.Counter)
    for r in rows:
        p = r.get("purity", {}).get("D3")
        if not p:
            continue
        # La banda NO se decide por la fraccion sino por el NUMERO ABSOLUTO de clientes distintos del objetivo que
        # existen. Con k = 20 la fraccion satura: D3 rellena con otras versiones de los mismos clientes y sale 0,975
        # lo mismo con cuarenta clientes que con cuatro. Lo que decide si un consenso significa algo es de cuantas
        # PERSONAS distintas viene, y el corte natural es k: por debajo de k clientes del objetivo, los veinte votos
        # no pueden ser veinte opiniones ni aunque la seleccion sea perfecta.
        clientes_disp = r["clients_same_goal_available"]
        if clientes_disp < 2 or p["goal_diets_frac"] < 0.50:
            b = "NO SERVIR"
        elif clientes_disp < 20:
            b = "SERVIR DECLARANDO"
        else:
            b = "SERVIR"
        bandas[b] += 1
        detalle[b][r["goal"]] += 1
    total = sum(bandas.values())
    for b in ("SERVIR", "SERVIR DECLARANDO", "NO SERVIR"):
        n = bandas[b]
        print(f"    {b:20}{n:>6}  ({n/total:.1%})   objetivos: {dict(detalle[b].most_common(6))}")
    out["bands"] = {b: {"n": bandas[b], "goals": dict(detalle[b])} for b in bandas}
    print("")
    print("    criterio -- NO SERVIR: menos de 2 clientes del objetivo (todo voto es la misma persona) o")
    print("    pureza < 0,50 · SERVIR DECLARANDO: menos de k = 20 clientes distintos del objetivo, asi que")
    print("    el consenso se apoya en menos personas que huecos tiene · SERVIR: el resto. La advertencia")
    print("    del panel dice con cuantos casos del objetivo y de cuantos clientes se construyo.")

    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float) + "\n",
                        encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
