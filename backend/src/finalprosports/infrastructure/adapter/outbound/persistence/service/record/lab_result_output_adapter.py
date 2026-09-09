"""LabResultOutputPort on Postgres (S4): lab_results, scoped to the portfolio through the client_profiles join."""
from __future__ import annotations

from sqlalchemy import text

from finalprosports.domain.model.lab_result import LabResult

_PORTFOLIO = "JOIN client_profiles p ON p.professional_id = r.professional_id AND p.client_code = r.client_code AND NOT p.is_corpus_case"


def _from_row(row) -> LabResult:
    g = row._mapping.get
    return LabResult(g("marker"), float(g("value")), g("unit"), float(g("ref_low")) if g("ref_low") is not None else None,
                     float(g("ref_high")) if g("ref_high") is not None else None, g("measured_at"), g("note"), g("source"), int(g("id")))


class LabResultOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    def list(self, professional_id: str, client_code: str) -> tuple[LabResult, ...]:
        with self._sf() as s:
            rows = s.execute(text(f"SELECT r.* FROM lab_results r {_PORTFOLIO} WHERE r.professional_id = :p AND r.client_code = :c ORDER BY r.measured_at NULLS LAST, r.id"),
                             {"p": professional_id, "c": client_code}).all()
            return tuple(_from_row(r) for r in rows)

    def add(self, professional_id: str, client_code: str, results: tuple[LabResult, ...]) -> tuple[LabResult, ...]:
        out = []
        with self._sf() as s:
            for r in results:
                row = s.execute(text("INSERT INTO lab_results (professional_id, client_code, measured_at, marker, value, unit, ref_low, ref_high, note, source) "
                                     "VALUES (:p, :c, :d, :m, :v, :u, :lo, :hi, :n, :s) RETURNING *"),
                                {"p": professional_id, "c": client_code, "d": r.measured_at, "m": r.marker, "v": r.value, "u": r.unit, "lo": r.ref_low, "hi": r.ref_high,
                                 "n": r.note, "s": r.source}).first()
                out.append(_from_row(row))
            s.commit()
        return tuple(out)

    def delete(self, professional_id: str, client_code: str, result_id: int) -> bool:
        with self._sf() as s:
            n = s.execute(text("DELETE FROM lab_results WHERE professional_id = :p AND client_code = :c AND id = :i"), {"p": professional_id, "c": client_code, "i": result_id}).rowcount
            s.commit()
            return bool(n)
