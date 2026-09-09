# -*- coding: utf-8 -*-
"""Bloque 0.2 -- INVENTARIO de las analiticas: que hay, de quien, y cuanto sobrevive a la regla temporal.

Los 254 informes NO estaban sin parsear: `lab_results.jsonl` existe desde F3 con 18.177 valores. Lo que faltaba era
saber que contienen y si sirven, y eso es lo que produce este modulo. Se reporta por ESPACIO DE NOMBRES, sin mezclar:

* `bioanalyzer` (217 informes): la impresion de un dispositivo con indices propios y su rango de normalidad. Parsea
  limpio porque su maquetacion es una tabla de tres columnas fijas.
* `clinical` (34): NO es un unico formato. Dentro conviven analiticas de laboratorio acreditado, informes de
  fisiologia deportiva (ergoespirometria) y documentos sin tabla de resultados. El parser de laboratorio corriendo
  sobre un informe de ergoespirometria produce «analitos» que son celdas de una tabla antropometrica.
* `nutrigenetic` (3): sin filas analito/valor/rango; no hay nada que parsear.

La regla temporal es la misma que la de la bascula: para una dieta solo cuentan los informes ANTERIORES a ella. Se
reporta la cobertura resultante sobre las consultas del arnes, que es lo unico que decide si un parametro puede entrar
en la similitud.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.lab_signals
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from finalprosports.infrastructure.adapter.inbound.eval.body_signals import doc_dates
from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import setup
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()

# Clasificacion por CONTENIDO, no por la etiqueta del inventario. Los tres patrones son literales de maquetacion que
# solo aparecen en su formato; ninguno nombra a una persona ni a una patologia.
FORMATS = {
    "sports_physiology": re.compile(r"ergoespirom|tapiz rodante|prueba de esfuerzo", re.I),
    "laboratory": re.compile(r"hemograma|bioqu[ií]mica|hemat[ií]es|leucocitos|colesterol total|creatinina", re.I),
    "device_bioanalyzer": re.compile(r"bioanaliz|viscosidad de la sangre|elasticidad vascular|cristal de colesterol", re.I),
    "nutrigenetic": re.compile(r"NutriGen|Fagron", re.I),
}
MIN_CLIENTS_TO_BE_USABLE = 30       # por debajo de esto un parametro no puede sostener una senal de similitud


def load_reports() -> list[dict]:
    path = DATASET_DIR / "lab_results.jsonl"
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def parameter_name(value: dict) -> str:
    return value.get("indicator") or value.get("analyte") or "?"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "lab_signal_coverage.json")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    reports = load_reports()
    root, pid, diets, profiles, queries, rules = setup()
    dates = doc_dates(DATASET_DIR)

    print(f"informes: {len(reports)} · clientes con informe: {len({r['client_code'] for r in reports if r['client_code']})}")
    by_ns = collections.Counter(r["source_type"] for r in reports)
    print(f"por espacio de nombres: {dict(by_ns)}")

    # ------------------------------------------------------------------------------------- escaneados / sin texto
    sin_texto = [r for r in reports if r["extractable_chars"] == 0]
    poco_texto = [r for r in reports if 0 < r["extractable_chars"] < 1200]
    print(f"\n--- los que no dan texto ---")
    print(f"  0 caracteres extraibles (imagen pura)   : {len(sin_texto)}")
    print(f"  por debajo del umbral de 1.200 caracteres: {len(poco_texto)}")
    print(f"  NO se ha inventado ningun valor para ellos: quedan en nivel 1/2 con su motivo.")

    # ------------------------------------------------------------------------------------------ niveles y motivos
    niveles = collections.Counter(r["level"] for r in reports)
    print(f"\n--- nivel alcanzado ---")
    for lvl in sorted(niveles):
        print(f"  nivel {lvl}: {niveles[lvl]}")
    motivos = collections.Counter(r["level_reason"].split(":")[0] for r in reports if r["level_reason"])
    for m, n in motivos.most_common():
        print(f"    {n:>4}  {m[:100]}")

    # ---------------------------------------------------------------------- parametros: frecuencia y clientes
    print(f"\n--- parametros distintos, por espacio de nombres ---")
    inventory = {}
    for ns in sorted(by_ns):
        freq = collections.Counter()
        clients = collections.defaultdict(set)
        for r in reports:
            if r["source_type"] != ns:
                continue
            for v in r["values"]:
                name = parameter_name(v)
                freq[name] += 1
                if r["client_code"]:
                    clients[name].add(r["client_code"])
        inventory[ns] = {name: {"occurrences": n, "clients": len(clients[name])} for name, n in freq.items()}
        usables = [n for n, d in inventory[ns].items() if d["clients"] >= MIN_CLIENTS_TO_BE_USABLE]
        print(f"\n  {ns}: {len(freq)} parametros distintos · {sum(freq.values())} valores · "
              f"{len(usables)} con >= {MIN_CLIENTS_TO_BE_USABLE} clientes")
        print(f"    {'parametro':52}{'veces':>8}{'clientes':>10}")
        for name, n in freq.most_common(args.top):
            print(f"    {name[:50]:52}{n:>8}{len(clients[name]):>10}")

    # ---------------------------------------------------------------------------------- la regla temporal
    by_client = collections.defaultdict(list)
    for r in reports:
        if r["client_code"] and r["report_date"]:
            by_client[r["client_code"]].append(r)
    q_clients = {q.client_code for q in queries}
    print(f"\n--- regla temporal sobre las {len(queries)} consultas del arnes ---")
    print(f"  clientes del arnes con algun informe fechado: {len(q_clients & by_client.keys())} de {len(q_clients)}")
    con_previo = collections.Counter()
    for q in queries:
        cut = dates.get(q.id)
        if not cut:
            continue
        prev = [r for r in by_client.get(q.client_code, []) if r["report_date"] < cut]
        if prev:
            con_previo["cualquiera"] += 1
            for ns in {r["source_type"] for r in prev}:
                con_previo[ns] += 1
            if any(r["values"] for r in prev):
                con_previo["con_valores"] += 1
    print(f"  consultas con ALGUN informe anterior          : {con_previo['cualquiera']}  ({con_previo['cualquiera']/len(queries):.1%})")
    print(f"  ... y con al menos un valor parseado          : {con_previo['con_valores']}  ({con_previo['con_valores']/len(queries):.1%})")
    for ns in sorted(by_ns):
        print(f"  ... de tipo {ns:20}: {con_previo[ns]:>4}  ({con_previo[ns]/len(queries):.1%})")

    # ------------------------------------------------------- cobertura por parametro CON la regla temporal aplicada
    print(f"\n--- parametros por cobertura EFECTIVA (consulta con ese parametro medido ANTES de su dieta) ---")
    per_param = collections.Counter()
    for q in queries:
        cut = dates.get(q.id)
        if not cut:
            continue
        vistos = set()
        for r in by_client.get(q.client_code, []):
            if r["report_date"] < cut:
                vistos.update(parameter_name(v) for v in r["values"])
        for name in vistos:
            per_param[name] += 1
    total_pairs = len(queries) * (len(queries) - 1)
    print(f"  {'parametro':52}{'consultas':>11}{'%':>8}{'% pares':>10}")
    effective = {}
    for name, n in per_param.most_common(args.top):
        pairs = n * (n - 1) / total_pairs
        effective[name] = {"queries": n, "pct": n / len(queries), "pairs_pct": pairs}
        print(f"  {name[:50]:52}{n:>11}{n/len(queries):>8.1%}{pairs:>10.1%}")
    if not per_param:
        print("  (ninguno)")

    payload = {"reports": len(reports), "by_namespace": dict(by_ns), "levels": dict(niveles),
               "no_extractable_text": len(sin_texto), "below_threshold": len(poco_texto),
               "queries": len(queries),
               "queries_with_a_prior_report": con_previo["cualquiera"],
               "queries_with_a_prior_parsed_value": con_previo["con_valores"],
               "queries_with_a_prior_report_by_namespace": {ns: con_previo[ns] for ns in by_ns},
               "min_clients_to_be_usable": MIN_CLIENTS_TO_BE_USABLE,
               "inventory": inventory, "effective_coverage_top": effective}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
