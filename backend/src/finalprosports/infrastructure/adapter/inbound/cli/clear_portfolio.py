# -*- coding: utf-8 -*-
"""`make clear-portfolio` — dejar la base de datos EN ESTADO DE ENTREGA: la cartera vacía, la base de casos intacta.

La aplicación se entrega sin un solo cliente. La base de datos de entrega, en cambio, sí lleva el corpus: el pgvector
lo necesita para recuperar. Este adaptador de entrada separa las dos poblaciones que comparten tabla:

  cartera        los clientes del profesional (`is_corpus_case = false`), con su expediente, su báscula, sus
                 analíticas y sus dietas guardadas. **Se borran.**
  base de casos  el corpus seudonimizado (`is_corpus_case = true`), sus dietas, sus embeddings y — desde las
                 migraciones 0015 y 0016 — sus lecturas y sus parámetros. **No se tocan.**

Existe porque durante el desarrollo la cartera se llena a propósito: `make demo` siembra tres clientes ficticios y el
recorrido de extremo a extremo carga uno real para revisar su dieta en la aplicación. Ninguno de los dos
puede viajar en la entrega, y «acuérdate de borrarlo» no es un procedimiento.

Borra a través del repositorio de clientes (`ClientRepositoryOutputAdapter.delete`), que ya arrastra en cascada las
dietas guardadas, las analíticas, la báscula y el expediente, y cuyo `DELETE` de perfil lleva escrito
`AND NOT is_corpus_case`: si un día alguien le pasara un código del corpus, no borraría nada.

Uso (desde backend/, con la base de datos levantada):
    python -m finalprosports.infrastructure.adapter.inbound.cli.clear_portfolio            # dice qué borraría
    python -m finalprosports.infrastructure.adapter.inbound.cli.clear_portfolio --apply    # lo borra

Imprime CUÁNTOS clientes y de qué longitud es su nombre, nunca el nombre (regla 1 de las reglas de manejo de datos personales de la memoria). Después conviene
`make verify-delivery`, que es quien comprueba que la aplicación ya no muestra nada.
"""
from __future__ import annotations

import argparse
import json
import sys

from finalprosports.infrastructure.composition_root import CompositionRoot
from finalprosports.infrastructure.config.settings import Settings


def clear(root: CompositionRoot, pid: str, apply: bool) -> dict:
    cartera = root.client_repository.list(pid)
    out = {"professional_id": pid, "apply": apply, "portfolio_before": len(cartera), "clients": [], "case_base": 0}
    for p in cartera:
        record = root.client_records.get(pid, p.client_code)
        nombre = (record.identification.full_name or "") if record is not None else ""
        out["clients"].append({"key": p.client_code, "name_length": len(nombre.strip()),
                               "saved_diets": len(root.history.history(pid, p.client_code)),
                               "lab_results": len(root.lab_results.list(pid, p.client_code))})
        if apply:
            root.client_repository.delete(pid, p.client_code)
    out["portfolio_after"] = len(root.client_repository.list(pid))
    out["case_base"] = len(root.client_repository.list_case_profiles(pid))       # intacta, y se imprime para probarlo
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="borrar de verdad (sin esto solo informa)")
    args = ap.parse_args()
    root = CompositionRoot.from_env()
    res = clear(root, Settings().professional_id, args.apply)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if not args.apply and res["portfolio_before"]:
        print(f"\n{res['portfolio_before']} clientes de cartera seguirían visibles en la entrega. Repetir con --apply.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
