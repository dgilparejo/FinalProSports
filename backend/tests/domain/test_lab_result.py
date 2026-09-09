# -*- coding: utf-8 -*-
"""Domain tests (S4): semantic status of a lab marker against its reference range and the latest value per marker."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.model.lab_result import LabResult, LabStatus, latest_per_marker  # noqa: E402


def test_status_against_the_reference_range():
    assert LabResult("Glucosa", 92, "mg/dL", 70, 100).status is LabStatus.IN_RANGE
    assert LabResult("Glucosa", 112, "mg/dL", 70, 100).status is LabStatus.HIGH and LabResult("Glucosa", 112, "mg/dL", 70, 100).out_of_range
    assert LabResult("Ferritina", 12, "ng/mL", 30, 300).status is LabStatus.LOW
    assert LabResult("HDL", 62, "mg/dL", ref_low=40).status is LabStatus.IN_RANGE          # open range above
    assert LabResult("LDL", 140, "mg/dL", ref_high=130).status is LabStatus.HIGH
    assert LabResult("Vitamina D", 28).status is LabStatus.UNKNOWN and not LabResult("Vitamina D", 28).out_of_range


def test_latest_per_marker_is_case_insensitive_and_keeps_the_most_recent():
    rows = (LabResult("glucosa", 92, measured_at=date(2026, 1, 10), id=1), LabResult("Glucosa", 98, measured_at=date(2026, 6, 1), id=2),
            LabResult("HDL", 55, measured_at=date(2026, 6, 1), id=3), LabResult("hdl", 50, measured_at=None, id=4))
    latest = latest_per_marker(rows)
    assert [(r.marker, r.value) for r in latest] == [("Glucosa", 98), ("HDL", 55)]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
