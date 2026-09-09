# -*- coding: utf-8 -*-
"""Application tests (S4): the lab-report parser accepts CSV (Spanish/English headers, ';' or ',' delimiters, decimal comma, ranges «70-100»)
and JSON arrays, rejects rows without a numeric value, and the use case scopes everything to an existing portfolio client."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError  # noqa: E402
from finalprosports.application.usecase.record.add_lab_results_use_case import AddLabResultsUseCase, parse_file  # noqa: E402
from finalprosports.domain.model import ClientProfile, Goal  # noqa: E402
from finalprosports.domain.model.lab_result import LabResult, LabStatus  # noqa: E402

CSV_ES = "Marcador;Valor;Unidad;Min;Max;Fecha\nGlucosa;92,5;mg/dL;70;100;12/06/2026\nColesterol total;215;mg/dL;;200;12/06/2026\nHDL;;mg/dL;40;;12/06/2026\n"
CSV_EN = "marker,value,unit,range,date\nFerritin,25,ng/mL,30-300,2026-06-12\n"


class FakeClients:
    def __init__(self, *codes):
        self.codes = set(codes)

    def get(self, pid, code):
        return ClientProfile(code, pid, "M", 30, 178, 4, goal=Goal.VOLUME) if code in self.codes else None


class FakeLabs:
    def __init__(self):
        self.rows = []

    def list(self, pid, code):
        return tuple(self.rows)

    def add(self, pid, code, results):
        out = tuple(LabResult(r.marker, r.value, r.unit, r.ref_low, r.ref_high, r.measured_at, r.note, r.source, id=len(self.rows) + i + 1) for i, r in enumerate(results))
        self.rows.extend(out)
        return out

    def delete(self, pid, code, rid):
        n = len(self.rows); self.rows = [r for r in self.rows if r.id != rid]; return len(self.rows) < n


def test_parse_csv_spanish_headers_semicolon_and_decimal_comma():
    p = parse_file(CSV_ES)
    assert [r.marker for r in p.results] == ["Glucosa", "Colesterol total"] and p.rejected == ("fila 3: sin marcador o sin valor numérico",)
    g, c = p.results
    assert g.value == 92.5 and g.unit == "mg/dL" and (g.ref_low, g.ref_high) == (70, 100) and g.measured_at == date(2026, 6, 12) and g.status is LabStatus.IN_RANGE
    assert c.ref_low is None and c.ref_high == 200 and c.status is LabStatus.HIGH and c.source == "file"


def test_parse_csv_english_headers_with_range_column_and_json_array():
    p = parse_file(CSV_EN)
    assert p.results[0].ref_low == 30 and p.results[0].ref_high == 300 and p.results[0].status is LabStatus.LOW
    j = parse_file('[{"marker": "TSH", "value": "2.1", "unit": "mUI/L", "ref_low": 0.4, "ref_high": 4.0}, {"marker": "sin valor"}]', default_date=date(2026, 8, 1))
    assert len(j.results) == 1 and j.results[0].measured_at == date(2026, 8, 1) and j.rejected == ("fila 2: sin marcador o sin valor numérico",)
    assert parse_file("   ").results == ()


def test_use_case_scopes_to_existing_portfolio_clients():
    labs = FakeLabs()
    uc = AddLabResultsUseCase(FakeClients("DEMO_X"), labs)
    saved, rejected = uc.import_file("p", "DEMO_X", CSV_ES)
    assert len(saved) == 2 and len(rejected) == 1 and saved[0].id == 1
    assert uc.add_manual("p", "DEMO_X", (LabResult("HDL", 55, "mg/dL", 40, None),))[0].id == 3
    assert uc.delete("p", "DEMO_X", 3) is True and len(labs.rows) == 2
    for call in (lambda: uc.import_file("p", "CLIENTE_001", CSV_ES), lambda: uc.add_manual("p", "CLIENTE_001", ()), lambda: uc.delete("p", "CLIENTE_001", 1)):
        try:
            call(); raise AssertionError("expected ClientNotFoundError")
        except ClientNotFoundError:
            pass


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
