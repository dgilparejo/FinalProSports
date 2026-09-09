"""Lab-results endpoints (S4): list, add rows by hand, import a file's content (CSV or JSON), delete.

El aviso que este adaptador emitia («la analitica no interviene en la generacion: el corpus no tiene analiticas con
las que emparejar»): su segunda mitad dejo de ser cierta con la migracion 0016, que
cargo **18.038 mediciones de 254 informes de 155 clientes** en la base de casos. El corpus SI tiene analiticas.

Lo que sigue siendo cierto es que no intervienen en la propuesta -- su peso en la similitud es 0,00 porque el barrido
midio que no aportan (0,3015 frente a 0,3060) -- y que no pueden salir en el documento del cliente
(`tests/architecture/test_labs_never_reach_the_client.py`). Pero eso es una decision medida, no una carencia del
corpus, y decirlo con el motivo equivocado es peor que no decirlo: describia el sistema por algo que ya no pasa."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, status

from finalprosports.domain.model.lab_result import LabResult, latest_per_marker
from finalprosports.infrastructure.adapter.inbound.rest.dto.lab_dto import LabFileDto, LabResultsDto

def lab_to_dict(r: LabResult) -> dict:
    return {"id": r.id, "marker": r.marker, "value": r.value, "unit": r.unit, "ref_low": r.ref_low, "ref_high": r.ref_high,
            "measured_at": r.measured_at.isoformat() if r.measured_at else None, "note": r.note, "source": r.source, "status": r.status.value, "out_of_range": r.out_of_range}


def lab_context(results: tuple[LabResult, ...]) -> dict:
    latest = latest_per_marker(results)
    return {"results": [lab_to_dict(r) for r in latest], "out_of_range": sum(1 for r in latest if r.out_of_range), "total_rows": len(results)}


class LabResultsRestAdapter:
    def __init__(self, root):
        self.router = APIRouter(tags=["intake"])
        current, uc, labs, clients = root.current_professional, root.add_lab_results_use_case, root.lab_results, root.get_clients_service

        @self.router.get("/clients/{client_id}/lab-results", summary="Lab results of the client (all rows + latest per marker with semantic status)")
        def get_labs(client_id: str):
            pid = current.current_professional_id()
            clients.get_client(pid, client_id)
            rows = labs.list(pid, client_id)
            return {"rows": [lab_to_dict(r) for r in rows], **lab_context(rows)}

        @self.router.post("/clients/{client_id}/lab-results", status_code=status.HTTP_201_CREATED, summary="Add lab results typed by hand")
        def add_labs(client_id: str, dto: LabResultsDto):
            pid = current.current_professional_id()
            saved = uc.add_manual(pid, client_id, tuple(LabResult(r.marker, r.value, r.unit, r.ref_low, r.ref_high, r.measured_at, r.note, "manual") for r in dto.results))
            return {"added": [lab_to_dict(r) for r in saved], **lab_context(labs.list(pid, client_id))}

        @self.router.post("/clients/{client_id}/lab-results/import", status_code=status.HTTP_201_CREATED, summary="Import a lab report file (CSV with header or JSON array) sent as text")
        def import_labs(client_id: str, dto: LabFileDto):
            pid = current.current_professional_id()
            saved, rejected = uc.import_file(pid, client_id, dto.content, dto.measured_at)
            return {"added": [lab_to_dict(r) for r in saved], "rejected": list(rejected), **lab_context(labs.list(pid, client_id))}

        @self.router.delete("/clients/{client_id}/lab-results/{result_id}", summary="Delete one lab result row")
        def delete_lab(client_id: str, result_id: int):
            pid = current.current_professional_id()
            return {"deleted": uc.delete(pid, client_id, result_id), **lab_context(labs.list(pid, client_id))}
