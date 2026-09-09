"""Pydantic DTOs of the lab-results endpoints (S4)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LabResultDto(BaseModel):
    marker: str = Field(min_length=1, max_length=80)
    value: float
    unit: str | None = Field(default=None, max_length=30)
    ref_low: float | None = None
    ref_high: float | None = None
    measured_at: date | None = None
    note: str | None = Field(default=None, max_length=300)


class LabResultsDto(BaseModel):
    results: list[LabResultDto] = Field(default_factory=list)


class LabFileDto(BaseModel):
    """The CONTENT of the file (CSV with header or JSON array), read by the client; no multipart dependency."""

    content: str = Field(min_length=1, max_length=200_000)
    measured_at: date | None = Field(default=None, description="Default date for rows without one")
