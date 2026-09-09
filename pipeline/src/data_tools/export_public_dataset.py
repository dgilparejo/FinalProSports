# -*- coding: utf-8 -*-
"""Exporta a un árbol PÚBLICO solo los agregados del corpus: el criterio del profesional, sin ninguna persona dentro.

Hermano de `export_seed_dataset.py`, y con la misma disciplina: **lista blanca**, cada entrada declara quién la lee, y
el exportador **aborta** si detecta datos por persona en el destino. La diferencia es el criterio de admisión, que aquí
es categórico: un fichero entra si NO tiene filas por persona, y punto.

Por qué existe: la aplicación se publica (repositorio público) y el corpus no puede salir — 301 personas, 96,4 % únicas
por sexo+edad+altura+fecha de primera consulta, 18.121 parámetros de laboratorio, art. 9 RGPD. Pero lo que hace que una
dieta sea CORRECTA no son los casos, es el criterio minado de ellos: 31 reglas, 228 alimentos canónicos, 223 bandas de
cantidad (p05/p50/p95 con n>=10), 14 temas de notas con soporte >=15 dietas, los pares de alternativas y la colocación
de los suplementos. Eso son agregados, no personas, y son la mitad publicable del trabajo.

Medido sobre dataset-v3 el 2026-09-09: lo que se queda fuera son 47,2 MB (98,7 % de los bytes) y lo que sale son 0,6 MB.
El corpus ES el volumen; el criterio cabe en un correo.

  ENTRA (11 ficheros + rotation recortado)          QUIÉN LO LEE
  foods.json                                        load_postgres -> tabla foods; el resolutor de gustos
  validated_rules.json                              load_postgres -> tabla rules (motor de reglas y validador)
  rules_evaluability.json                           load_postgres -> rules.evaluation_level
  plausibility_envelope.json                        FilePlausibilityEnvelopeAdapter (capa de plausibilidad, S2)
  canonical_notes.json                              el compositor, para consensuar notas por tema
  supplement_slots.json                             la colocación de suplementos en la propuesta
  daily_totals_envelope.json                        comprobaciones de totales diarios
  his_check_rates.json                              calibración de las comprobaciones
  rotation_analysis.json  SIN la clave `per_client`  RotationComposer (familias, pares, alimentos por franja)
  INDEX.md · VERSION.json                           procedencia y contenido, para que el árbol público se explique

  NO ENTRA NUNCA (filas por persona, medido)
  profiles.jsonl (301) · diets.jsonl (266) · meals.jsonl (266) · diet_items.jsonl (261) · archetypes.json (261)
  body_measurements.jsonl (171) · body_measurements_followup.jsonl (3) · lab_results.jsonl (155)
  rotation_analysis.json -> per_client (164)

Uso:
  python pipeline/src/data_tools/export_public_dataset.py --dataset $FPS_DATASET_DIR --out seed/dataset_public
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

# Lista blanca. Cada entrada: (fichero, quién lo lee). Si algo no está aquí, no sale.
WHITELIST: tuple[tuple[str, str], ...] = (
    ("foods.json", "load_postgres -> foods; resolutor de gustos del cuestionario"),
    ("validated_rules.json", "load_postgres -> rules; RuleEngine y DietValidator"),
    ("rules_evaluability.json", "load_postgres -> rules.evaluation_level"),
    ("plausibility_envelope.json", "FilePlausibilityEnvelopeAdapter (S2)"),
    ("canonical_notes.json", "consenso de notas por tema"),
    ("supplement_slots.json", "colocación de suplementos"),
    ("daily_totals_envelope.json", "comprobación de totales diarios"),
    ("his_check_rates.json", "calibración de las comprobaciones"),
    ("INDEX.md", "procedencia legible"),
    ("VERSION.json", "versión y contenido del dataset de origen"),
)
# Se copia recortando una clave. Va aparte porque es el único fichero que se TRANSFORMA al salir.
TRIMMED = ("rotation_analysis.json", ("per_client",), "RotationComposer (familias, pares, alimentos por franja)")

# Lo que la existencia de un solo fichero de estos en el destino convierte en un aborto.
FORBIDDEN = ("profiles.jsonl", "diets.jsonl", "meals.jsonl", "diet_items.jsonl", "archetypes.json",
             "body_measurements.jsonl", "body_measurements_followup.jsonl", "lab_results.jsonl")
PSEUDONYM = re.compile(r"CLIENTE_\d+")


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def abort(reason: str) -> None:
    print(f"ABORTADO: {reason}", file=sys.stderr)
    raise SystemExit(2)


def check_no_person(path: Path) -> int:
    """Ningún seudónimo del corpus en un fichero que se publica. Devuelve cuántos encontró (0 es el criterio)."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return len(set(PSEUDONYM.findall(text)))


def export(dataset: Path, out: Path, apply: bool) -> dict:
    if not (dataset / "foods.json").exists():
        abort(f"{dataset} no parece un dataset (falta foods.json)")
    # Guarda de destino: si ahí dentro hay datos por persona, no se escribe nada. Antes de copiar, no después.
    for name in FORBIDDEN:
        if (out / name).exists():
            abort(f"el destino {out} contiene {name}, que son filas por persona. No se escribe nada.")
    if (out / "_private").exists():
        abort(f"el destino {out} contiene _private/. No se escribe nada.")

    report: dict = {"dataset": str(dataset), "out": str(out), "applied": apply, "files": [], "skipped_person_files": list(FORBIDDEN)}
    if apply:
        out.mkdir(parents=True, exist_ok=True)

    for name, reader in WHITELIST:
        src = dataset / name
        if not src.exists():
            abort(f"falta {name} en {dataset}: la lista blanca no se cumple sola")
        hits = check_no_person(src)
        if hits:
            abort(f"{name} contiene {hits} seudónimos del corpus: no es un agregado, revísalo antes de publicar")
        if apply:
            shutil.copy2(src, out / name)
        report["files"].append({"file": name, "read_by": reader, "kb": round(src.stat().st_size / 1024, 1),
                                "sha1": sha1(src), "pseudonyms": hits})

    name, drop, reader = TRIMMED
    src = dataset / name
    if not src.exists():
        abort(f"falta {name} en {dataset}")
    data = json.loads(src.read_text(encoding="utf-8"))
    removed = {k: len(json.dumps(data[k], ensure_ascii=False)) for k in drop if k in data}
    for k in drop:
        data.pop(k, None)
    blob = json.dumps(data, ensure_ascii=False, indent=1)
    hits = len(set(PSEUDONYM.findall(blob)))
    if hits:
        abort(f"{name} sigue con {hits} seudónimos después de quitar {drop}: no se publica")
    if apply:
        (out / name).write_text(blob, encoding="utf-8", newline="\n")
    report["files"].append({"file": name, "read_by": reader, "kb": round(len(blob.encode("utf-8")) / 1024, 1),
                            "trimmed_keys": {k: round(v / 1024, 1) for k, v in removed.items()}, "pseudonyms": hits})

    if apply:                                                  # manifiesto propio: lo publicado y su huella
        manifest = {"source_dataset": str(dataset), "generated_by": "export_public_dataset.py",
                    "contents": [{"file": f["file"], "sha1": sha1(out / f["file"]), "kb": round((out / f["file"]).stat().st_size / 1024, 1)}
                                 for f in report["files"]],
                    "excluded_person_files": list(FORBIDDEN) + [f"{TRIMMED[0]}::per_client"],
                    "note": ("Solo agregados: ninguna fila por persona. El corpus real (301 personas, 1.203 dietas, "
                             "18.121 parámetros de laboratorio) NO se publica: es dato de salud del art. 9 RGPD.")}
        (out / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        report["manifest"] = str(out / "MANIFEST.json")
    report["total_kb"] = round(sum(f["kb"] for f in report["files"]), 1)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, required=True, help="dataset de origen (FPS_DATASET_DIR)")
    ap.add_argument("--out", type=Path, required=True, help="árbol público de destino")
    ap.add_argument("--apply", action="store_true", help="escribir de verdad (sin esto, solo informa)")
    args = ap.parse_args()
    print(json.dumps(export(args.dataset, args.out, args.apply), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
