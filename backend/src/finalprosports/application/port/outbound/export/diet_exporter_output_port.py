"""Outbound port: diet export."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.diet_proposal import DietProposal


class DietExporterOutputPort(Protocol):
    def export(self, proposal: DietProposal, diet_id: str = "", strategy_label: str | None = None, lab_results=(), client_name: str | None = None) -> bytes: ...
