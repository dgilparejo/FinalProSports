# -*- coding: utf-8 -*-
"""DONDE pone EL cada suplemento, minado del corpus. Salida: `$FPS_DATASET_DIR/supplement_slots.json`.

Por que hace falta. El sistema componia un bloque «SUPLEMENTOS» aparte con todo lo que los casos tenian ahi, y el
cliente leia una lista al final del documento sin saber cuando tomarse cada cosa. El profesional, cuando los
distribuye, los escribe DENTRO de la comida: la creatina en el desayuno, el potasio en la comida, el ZMA y la vitamina
D en la cena.

Lo que dice el corpus, y conviene decirlo entero porque matiza la decision:

* **el bloque no es un invento del sistema**: el lo usa en **589 de sus 1.203 dietas (49,0 %)**, y el 34,1 % de los
  items de suplemento viven ahi. Distribuir siempre no es «hacer lo que el hace»: es hacer lo que hace la otra mitad
  de las veces;
* fuera del bloque, las franjas de entreno se llevan la quinta parte (DESPUES 10,5 %, ANTES 9,8 %) y RECIEN LEVANTADO
  otro 8,1 %.

Este artefacto es el RESPALDO, no el criterio principal. La colocacion la decide primero lo que hacen los CASOS
RECUPERADOS de ese cliente (`supplement_placement_policy`), que es el principio del sistema y resuelve el 74,8 % de
los casos; esta tabla solo contesta el 25,2 % restante, cuando los veinte vecinos no lo dicen en ninguna franja real.

Se guarda la distribucion ENTERA por suplemento, no solo la moda: `concentration` dice cuanto se puede confiar en
ella, y son solo 10 de 37 los suplementos cuya franja modal pasa del 50 %. Quien consuma esto tiene que poder ver esa
cifra y no solo la respuesta.

Run:  python pipeline/src/pipeline/supplement_slots.py
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR  # noqa: E402

# Las dos franjas que NO son un momento de ingesta: el bloque generico y el cajon del extractor. Son justo las que se
# quieren evitar, asi que no pueden contar como respuesta.
GENERIC = {"SUPLEMENTOS", "OTHER"}
MIN_OBSERVATIONS = 10          # por debajo de esto la moda no se sostiene y el suplemento se deja sin colocar


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=Path(DATASET_DIR))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out_path = args.out or (args.dataset / "supplement_slots.json")

    foods = {f["id"]: f for f in json.loads((args.dataset / "foods.json").read_text(encoding="utf-8"))["foods"]}
    supplements = {i for i, f in foods.items() if f["group"] == "SUPPLEMENT"}

    per_food: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    in_generic: collections.Counter = collections.Counter()
    diets_with_block, diets = set(), set()
    for line in (args.dataset / "diet_items.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        diets.add(row["diet_id"])
        if row["meal_slot"] == "SUPLEMENTOS":
            diets_with_block.add(row["diet_id"])
        fid = row.get("food_id")
        if fid not in supplements:
            continue
        if row["meal_slot"] in GENERIC:
            in_generic[fid] += 1
        else:
            per_food[fid][row["meal_slot"]] += 1

    placements = {}
    for fid, counter in per_food.items():
        n = sum(counter.values())
        if n < MIN_OBSERVATIONS:
            continue
        slot, k = counter.most_common(1)[0]
        placements[foods[fid]["canonical_name"]] = {
            "food_id": fid, "slot": slot, "observations": n, "concentration": round(k / n, 4),
            "in_generic_block": in_generic.get(fid, 0),
            "distribution": {s: c for s, c in counter.most_common()},
        }

    payload = {
        "diets": len(diets),
        "diets_with_a_supplements_block": len(diets_with_block),
        "diets_with_a_supplements_block_pct": round(len(diets_with_block) / len(diets), 4),
        "min_observations": MIN_OBSERVATIONS,
        "supplements_placeable": len(placements),
        "supplements_with_modal_slot_over_half": sum(1 for p in placements.values() if p["concentration"] >= 0.5),
        "note": ("Respaldo, no criterio principal: la colocacion la deciden primero los CASOS RECUPERADOS "
                 "(supplement_placement_policy), que resuelven el 74,8 %. Esta tabla contesta el resto."),
        "placements": dict(sorted(placements.items(), key=lambda kv: -kv[1]["observations"])),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"dietas: {payload['diets']} · con bloque SUPLEMENTOS propio: {payload['diets_with_a_supplements_block']} "
          f"({payload['diets_with_a_supplements_block_pct']:.1%})")
    print(f"suplementos colocables (>= {MIN_OBSERVATIONS} observaciones fuera del bloque): {len(placements)}")
    print(f"  de ellos con franja modal >= 50 %: {payload['supplements_with_modal_slot_over_half']}")
    print(f"\n  {'suplemento':30}{'franja modal':24}{'n':>7}{'concentracion':>15}")
    for name, p in list(payload["placements"].items())[:15]:
        print(f"  {name[:28]:30}{p['slot']:24}{p['observations']:>7}{p['concentration']:>14.1%}")
    print(f"\n-> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
