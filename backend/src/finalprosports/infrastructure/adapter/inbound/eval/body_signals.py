# -*- coding: utf-8 -*-
"""Bloque 0.1 -- COBERTURA de la bascula sobre el arnes, con la regla temporal.

La bascula (`body_measurements.jsonl`, 1.338 lecturas de 171 clientes) esta extraida desde F3 y NO llega a
`ClientProfile`, asi que ni la recuperacion ni la composicion la ven. Antes de anadirla hay que saber sobre cuantas
consultas es utilizable, y «utilizable» tiene una definicion estricta:

    LA LECTURA VALIDA DE UNA DIETA ES LA MAS RECIENTE ANTERIOR A SU FECHA.

Una bascula de 2023 no puede explicar una dieta de 2019: el profesional no la tenia delante cuando la escribio. Usarla
seria fuga temporal, y en un corpus donde el mismo cliente aparece varias veces a lo largo de diez anos la fuga no es
teorica. La regla se aplica con `<` ESTRICTO sobre `doc_date`: una lectura del MISMO dia se descarta, porque el orden
dentro del dia no consta y no se puede afirmar que precediera a la consulta.

Se reportan tres denominadores distintos, porque miden cosas distintas:
  * por CLIENTE   -- cuantos de los clientes con dietas tienen alguna lectura;
  * por DIETA     -- cuantas dietas tienen una lectura anterior (el numerador real de la senal);
  * por PAR       -- en cuantos pares (consulta, caso) los DOS lados tienen el campo, que es lo unico que un
                     comparador de similitud puede usar. Es el denominador que decide si el campo entra.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.body_signals
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import setup
from finalprosports.infrastructure.config.paths import dataset_dir

DATASET_DIR = dataset_dir()

# Los campos numericos de la bascula, con el nombre que llevan en `body_measurements.jsonl`.
SCALE_FIELDS = ("weight_kg", "fat_pct", "muscle_mass_kg", "hydration_pct", "bone_mass_kg",
                "physique_rating", "visceral_fat_rating", "metabolic_age", "basal_met_kcal", "height_cm")


def load_readings(path: Path) -> dict[str, list[dict]]:
    """Lecturas por cliente, ordenadas por fecha ascendente. `basal_met_kcal` viene como CADENA en el fichero."""
    by = collections.defaultdict(list)
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if row.get("basal_met_kcal") is not None:                      # defecto del extractor: "2725" en vez de 2725
            try:
                row["basal_met_kcal"] = float(row["basal_met_kcal"])
            except (TypeError, ValueError):
                row["basal_met_kcal"] = None
        by[row["client_code"]].append(row)
    for rows in by.values():
        rows.sort(key=lambda r: r["date"])
    return dict(by)


def as_of(readings: list[dict], on_date: str | None) -> dict | None:
    """La mas reciente ESTRICTAMENTE anterior a `on_date`. Sin fecha de dieta no hay lectura utilizable."""
    if not on_date:
        return None
    prior = [r for r in readings if r["date"] < on_date]
    return prior[-1] if prior else None


def doc_dates(dataset_path: Path) -> dict[str, str | None]:
    out = {}
    for line in (dataset_path / "diets.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        out[row["id"]] = row["meta"].get("doc_date")
    return out


def _days(iso: str) -> int:
    return int(iso[:4]) * 372 + int(iso[5:7]) * 31 + int(iso[8:10])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "body_signal_coverage.json")
    args = ap.parse_args()

    root, pid, diets, profiles, queries, rules = setup()
    doc_date = doc_dates(DATASET_DIR)
    readings = load_readings(DATASET_DIR / "body_measurements.jsonl")

    clients_with_diets = {d.client_code for d in diets.values()}
    q_clients = {q.client_code for q in queries}
    print(f"corpus : {len(diets)} dietas de {len(clients_with_diets)} clientes")
    print(f"arnes  : {len(queries)} consultas de {len(q_clients)} clientes")
    print(f"bascula: {sum(len(v) for v in readings.values())} lecturas de {len(readings)} clientes\n")

    print("--- por CLIENTE ---")
    print(f"  clientes con dietas y alguna lectura   : {len(clients_with_diets & readings.keys())} de {len(clients_with_diets)}")
    print(f"  clientes del ARNES con alguna lectura  : {len(q_clients & readings.keys())} de {len(q_clients)}")

    def dieta_stats(pool, etiqueta):
        sin_fecha = sum(1 for d in pool if not doc_date.get(d.id))
        sin_bascula = sum(1 for d in pool if doc_date.get(d.id) and d.client_code not in readings)
        con_prev = [d for d in pool if as_of(readings.get(d.client_code, []), doc_date.get(d.id))]
        toda_post = len(pool) - sin_fecha - sin_bascula - len(con_prev)
        print(f"\n--- por {etiqueta} ({len(pool)}) ---")
        print(f"  con lectura ANTERIOR (utilizable)      : {len(con_prev)}  ({len(con_prev)/len(pool):.1%})")
        print(f"  cliente sin ninguna lectura            : {sin_bascula}")
        print(f"  lecturas existen pero TODAS posteriores: {toda_post}")
        print(f"  dieta sin fecha en el documento        : {sin_fecha}")
        if con_prev:
            gaps = sorted(_days(doc_date[d.id]) - _days(as_of(readings[d.client_code], doc_date[d.id])["date"])
                          for d in con_prev)
            print(f"  antiguedad de la lectura usada (dias)  : mediana {statistics.median(gaps):.0f} · p90 {gaps[int(len(gaps)*.9)]:.0f}")
        return con_prev

    dieta_stats(list(diets.values()), "DIETA del corpus")
    q_prev = dieta_stats(list(queries), "CONSULTA del arnes")

    print(f"\n--- cobertura POR CAMPO sobre las {len(queries)} consultas del arnes ---")
    print(f"  {'campo':22}{'consultas':>11}{'%':>9}{'pares evaluables':>19}{'% pares':>10}")
    usable = {}
    for q in queries:
        usable[q.id] = as_of(readings.get(q.client_code, []), doc_date.get(q.id)) or {}
    field_rows = {}
    total_pairs = len(queries) * (len(queries) - 1)
    for f in SCALE_FIELDS:
        n = sum(1 for q in queries if usable[q.id].get(f) is not None)
        ok_pairs = n * (n - 1)
        field_rows[f] = {"queries_with_value": n, "queries_pct": n / len(queries),
                         "pairs_evaluable": ok_pairs, "pairs_pct": ok_pairs / total_pairs}
        print(f"  {f:22}{n:>11}{n/len(queries):>9.1%}{ok_pairs:>19,}{ok_pairs/total_pairs:>10.1%}")

    payload = {"queries": len(queries), "query_clients": len(q_clients),
               "corpus_diets": len(diets), "corpus_clients": len(clients_with_diets),
               "scale_readings": sum(len(v) for v in readings.values()), "scale_clients": len(readings),
               "clients_with_diets_and_a_reading": len(clients_with_diets & readings.keys()),
               "query_clients_with_a_reading": len(q_clients & readings.keys()),
               "queries_with_a_prior_reading": len(q_prev),
               "rule": "the valid reading of a diet is the most recent one STRICTLY before its doc_date",
               "fields": field_rows}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
