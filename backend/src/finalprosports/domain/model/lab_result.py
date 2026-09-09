"""Lab results (S4): one marker of a blood/urine analysis attached to a portfolio client's record.

Simple and extensible model: marker, value, unit, reference range, date. The STATUS is derived (below / above / inside the reference
range, or unknown when no range is given) and drives the semantic colour in the UI. The analysis is CONTEXT for the professional: it
never enters retrieval or composition — the corpus carries no analyses to match against (declared in the UI and the report)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class LabStatus(StrEnum):
    LOW = "bajo"
    HIGH = "alto"
    IN_RANGE = "en_rango"
    UNKNOWN = "sin_rango"


@dataclass(frozen=True)
class LabResult:
    marker: str                          # as written in the report («Glucosa», «HDL», «Ferritina» ...)
    value: float
    unit: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    measured_at: date | None = None
    note: str | None = None
    source: str = "manual"               # 'manual' | 'file'
    id: int | None = None

    @property
    def status(self) -> LabStatus:
        if self.ref_low is None and self.ref_high is None:
            return LabStatus.UNKNOWN
        if self.ref_low is not None and self.value < self.ref_low:
            return LabStatus.LOW
        if self.ref_high is not None and self.value > self.ref_high:
            return LabStatus.HIGH
        return LabStatus.IN_RANGE

    @property
    def out_of_range(self) -> bool:
        return self.status in (LabStatus.LOW, LabStatus.HIGH)


def latest_per_marker(results: tuple[LabResult, ...]) -> tuple[LabResult, ...]:
    """The most recent value of each marker (case-insensitive marker key), in marker order."""
    best: dict[str, LabResult] = {}
    for r in results:
        k = r.marker.strip().lower()
        cur = best.get(k)
        if cur is None or ((r.measured_at or date.min), r.id or 0) >= ((cur.measured_at or date.min), cur.id or 0):
            best[k] = r
    return tuple(sorted(best.values(), key=lambda r: r.marker.lower()))
