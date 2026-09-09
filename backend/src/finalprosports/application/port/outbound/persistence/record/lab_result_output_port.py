"""Outbound port: lab results attached to a portfolio client (S4)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.lab_result import LabResult


class LabResultOutputPort(Protocol):
    def list(self, professional_id: str, client_code: str) -> tuple[LabResult, ...]: ...

    def add(self, professional_id: str, client_code: str, results: tuple[LabResult, ...]) -> tuple[LabResult, ...]: ...

    def delete(self, professional_id: str, client_code: str, result_id: int) -> bool: ...
