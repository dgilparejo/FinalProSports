"""Outbound port: unmet demand log (no similar cases, unsatisfiable restrictions)."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class GapLogOutputPort(Protocol):
    def log(self, professional_id: str, kind: str, payload: dict) -> None: ...
