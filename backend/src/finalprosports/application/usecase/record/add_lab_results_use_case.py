"""AddLabResultsUseCase (S4): attach an analysis to a portfolio client — rows typed by hand or a file pasted / uploaded as text.

File import without new dependencies: the client sends the file CONTENT (CSV with header, or a JSON array of rows). Accepted header
names (case-insensitive, Spanish or English): marcador|marker|parametro|prueba, valor|value|resultado, unidad|unit|unidades,
min|ref_low|inferior|desde, max|ref_high|superior|hasta, fecha|date|measured_at, nota|note. Decimal comma is accepted. Rows without a
numeric value are reported as rejected, never guessed."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.application.port.outbound.persistence.client.client_repository_output_port import ClientRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.record.lab_result_output_port import LabResultOutputPort
from finalprosports.domain.model.lab_result import LabResult

_ALIASES = {"marker": ("marcador", "marker", "parametro", "parámetro", "prueba", "analito", "name", "nombre"),
            "value": ("valor", "value", "resultado", "result"),
            "unit": ("unidad", "unit", "unidades", "units"),
            "ref_low": ("min", "ref_low", "inferior", "desde", "low", "minimo", "mínimo"),
            "ref_high": ("max", "ref_high", "superior", "hasta", "high", "maximo", "máximo"),
            "measured_at": ("fecha", "date", "measured_at", "fecha_analitica"),
            "note": ("nota", "note", "observaciones", "comentario")}
_RANGE = re.compile(r"^\s*([\d.,]+)\s*[-–]\s*([\d.,]+)\s*$")


@dataclass(frozen=True)
class ParsedRows:
    results: tuple[LabResult, ...]
    rejected: tuple[str, ...]


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def _date(v) -> date | None:
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _norm_key(k: str) -> str:
    k = k.strip().lower()
    for canon, aliases in _ALIASES.items():
        if k in aliases:
            return canon
    return k


def row_to_result(row: dict, source: str, default_date: date | None = None) -> LabResult | None:
    r = {_norm_key(k): v for k, v in row.items() if k is not None}
    marker = str(r.get("marker") or "").strip()
    value = _num(r.get("value"))
    if not marker or value is None:
        return None
    low, high = _num(r.get("ref_low")), _num(r.get("ref_high"))
    rng = r.get("rango") or r.get("range") or r.get("referencia")
    if low is None and high is None and rng and _RANGE.match(str(rng)):
        m = _RANGE.match(str(rng)); low, high = _num(m.group(1)), _num(m.group(2))
    return LabResult(marker[:80], value, (str(r.get("unit")).strip()[:30] or None) if r.get("unit") else None, low, high,
                     _date(r.get("measured_at")) or default_date, (str(r.get("note")).strip()[:300] or None) if r.get("note") else None, source)


def parse_file(content: str, default_date: date | None = None) -> ParsedRows:
    text = content.strip()
    if not text:
        return ParsedRows((), ())
    rows: list[dict] = []
    if text.startswith("["):
        rows = [r for r in json.loads(text) if isinstance(r, dict)]
    else:
        sample = text.splitlines()[0]
        delim = ";" if sample.count(";") >= sample.count(",") and sample.count(";") >= sample.count("\t") else ("\t" if sample.count("\t") > sample.count(",") else ",")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    results, rejected = [], []
    for i, row in enumerate(rows, 1):
        res = row_to_result(row, "file", default_date)
        (results.append(res) if res else rejected.append(f"fila {i}: sin marcador o sin valor numérico"))
    return ParsedRows(tuple(results), tuple(rejected))


class AddLabResultsUseCase:
    def __init__(self, clients: ClientRepositoryOutputPort, labs: LabResultOutputPort):
        self._clients, self._labs = clients, labs

    def add_manual(self, professional_id: str, client_code: str, results: tuple[LabResult, ...]) -> tuple[LabResult, ...]:
        if self._clients.get(professional_id, client_code) is None:
            raise ClientNotFoundError(client_code)
        return self._labs.add(professional_id, client_code, results)

    def import_file(self, professional_id: str, client_code: str, content: str, default_date: date | None = None) -> tuple[tuple[LabResult, ...], tuple[str, ...]]:
        if self._clients.get(professional_id, client_code) is None:
            raise ClientNotFoundError(client_code)
        parsed = parse_file(content, default_date)
        saved = self._labs.add(professional_id, client_code, parsed.results) if parsed.results else ()
        return saved, parsed.rejected

    def delete(self, professional_id: str, client_code: str, result_id: int) -> bool:
        if self._clients.get(professional_id, client_code) is None:
            raise ClientNotFoundError(client_code)
        return self._labs.delete(professional_id, client_code, result_id)
