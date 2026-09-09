"""Outbound port: body-composition measurements of a portfolio client (scale import or manual entry)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.client_record import BodyMeasurement


class BodyMeasurementOutputPort(Protocol):
    def list(self, professional_id: str, client_code: str) -> tuple[BodyMeasurement, ...]: ...

    def add(self, professional_id: str, client_code: str, measurements: tuple[BodyMeasurement, ...]) -> int: ...
