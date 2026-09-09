# -*- coding: utf-8 -*-
"""Copia al repositorio (`seed/dataset/`) EXACTAMENTE los ficheros que la aplicación necesita para funcionar.

Por qué existe. El requisito de entrega es que quien clone el repositorio levante la aplicación completa con
`docker compose up` y pueda generar dietas. El motor es BASADO EN CASOS: sin base de casos la propuesta devuelve 422.
Así que el corpus tiene que viajar con el código, y este script es el único camino por el que entra.

**Lista blanca, no lista negra.** Copia solo lo que está en `MANIFEST` y nada más. Un `cp -r` del dataset arrastraría
`_private/` —`id_map.json` y `client_files_map.json` mapean a los NOMBRES DE FICHERO ORIGINALES, y
`health_profiles.jsonl` es texto clínico— y también los artefactos de evaluación (`composer_per_query.jsonl` y
compañía, ~10 MB) que no pinta nada publicar. Con lista blanca, un fichero nuevo en el dataset no se cuela solo: hay
que añadirlo aquí a mano, que es el punto.

**`_private/` está prohibido explícitamente**, además de no estar en la lista, y el script aborta si detecta que
alguien lo ha añadido: es la diferencia entre un corpus seudonimizado y un corpus reidentificable.

Después de ejecutarlo hay que pasar la auditoría, que ahora recorre también estos ficheros porque están dentro del
árbol de código:

    python pipeline/src/data_tools/audit_tree.py     # criterio 0

Uso (desde la raíz del repositorio):
    python pipeline/src/data_tools/export_seed_dataset.py            # dice qué copiaría y cuánto ocupa
    python pipeline/src/data_tools/export_seed_dataset.py --apply    # lo copia

Imprime solo nombres de fichero y tamaños. Nunca contenido.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import dataset_dir, repo_root  # noqa: E402

DESTINO = "seed/dataset"
PROHIBIDO = ("_private",)

# Cada entrada dice QUIÉN la lee. Si nadie la lee, no viaja.
MANIFEST: dict[str, str] = {
    # --- la base de casos: sin esto el motor no puede recuperar nada y la propuesta devuelve 422
    "profiles.jsonl": "load_postgres -> client_profiles",
    "diets.jsonl": "load_postgres -> diets",
    "meals.jsonl": "load_postgres -> meals",
    "diet_items.jsonl": "load_postgres -> diet_items",
    "foods.json": "load_postgres -> foods (catalogo de alimentos canonicos)",
    "validated_rules.json": "load_postgres -> rules (31 reglas)",
    "rules_evaluability.json": "load_postgres -> rules (evaluabilidad)",
    "archetypes.json": "load_postgres -> archetypes",
    # --- opcionales del cargador: el motor entregado les da peso 0,0, pero la ficha del cliente los muestra
    "body_measurements.jsonl": "load_postgres -> body_measurements (peso 0,0 en similitud; ficha)",
    "body_measurements_followup.jsonl": "load_postgres -> body_measurements (seguimiento)",
    "lab_results.jsonl": "load_postgres -> lab_results (peso 0,0 en similitud; ficha)",
    # --- lo que la API lee EN EJECUCION; sin ellos estas capas se apagan en silencio
    "plausibility_envelope.json": "FilePlausibilityEnvelopeAdapter (capa de plausibilidad)",
    "canonical_notes.json": "FileNoteCatalogueAdapter (notas canonicas por tema)",
    "supplement_slots.json": "FileSupplementSlotsAdapter (colocacion de suplementos)",
    "rotation_analysis.json": "FileRotationStatsAdapter (rotacion del cliente recurrente)",
    # --- agregados que usan las comprobaciones de conformidad y el arnes
    "daily_totals_envelope.json": "eval.conformance (totales diarios por macrogrupo)",
    "his_check_rates.json": "eval.conformance (sus tasas, para la recalibracion)",
    # --- procedencia: qué version del dataset es esto
    "VERSION.json": "procedencia",
    "INDEX.md": "procedencia",
}

OBLIGATORIOS = ("profiles.jsonl", "diets.jsonl", "meals.jsonl", "diet_items.jsonl", "foods.json",
                "validated_rules.json", "rules_evaluability.json", "archetypes.json")


def sha1(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="copiar (sin esto solo informa)")
    args = ap.parse_args()

    origen, destino = dataset_dir(), repo_root() / DESTINO
    print(f"origen : {origen}")
    print(f"destino: {destino}")
    print()

    faltan = [n for n in OBLIGATORIOS if not (origen / n).exists()]
    if faltan:
        print(f"FALTAN ficheros sin los cuales la aplicacion no puede generar dietas: {faltan}", file=sys.stderr)
        return 1

    total = 0
    plan = []
    for nombre, quien in MANIFEST.items():
        p = origen / nombre
        if not p.exists():
            print(f"  {'(ausente)':>12s}  {nombre:36s} {quien}")
            continue
        total += p.stat().st_size
        plan.append((nombre, p))
        print(f"  {p.stat().st_size:12,d}  {nombre:36s} {quien}")
    print()
    print(f"  {total:12,d}  TOTAL  ({total / 1e6:.1f} MB en {len(plan)} ficheros)")

    if args.apply:
        destino.mkdir(parents=True, exist_ok=True)
        # Lo que ya hubiera y no este en el manifiesto se va: el destino es un ESPEJO del manifiesto, no un cajon
        # que acumula. Si no, un fichero retirado del manifiesto seguiria publicado para siempre.
        for viejo in destino.iterdir():
            if viejo.name not in MANIFEST and viejo.name != "README.md":
                print(f"  retirado (ya no esta en el manifiesto): {viejo.name}")
                shutil.rmtree(viejo) if viejo.is_dir() else viejo.unlink()
        for nombre, p in plan:
            shutil.copy2(p, destino / nombre)
        (destino / "MANIFEST.json").write_text(json.dumps(
            {"source_version": json.loads((origen / "VERSION.json").read_text(encoding="utf-8")) if (origen / "VERSION.json").exists() else None,
             "files": {n: {"bytes": (destino / n).stat().st_size, "sha1": sha1(destino / n), "read_by": MANIFEST[n]} for n, _ in plan}},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"\ncopiados {len(plan)} ficheros")

    # el guarda, se copie o no
    colados = [d for d in (destino.iterdir() if destino.exists() else []) if d.name in PROHIBIDO]
    if colados:
        print(f"\nABORTA: {[c.name for c in colados]} esta en el destino. Ahi vive el mapa de reidentificacion "
              f"(id_map.json, client_files_map.json) y el texto clinico. Eso NO se publica.", file=sys.stderr)
        return 1
    print("\nsiguiente paso obligatorio:  python pipeline/src/data_tools/audit_tree.py   (criterio 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
