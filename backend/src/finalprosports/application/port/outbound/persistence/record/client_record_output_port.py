"""Outbound port: the client's record (intake questionnaire) — portfolio only."""
from typing import Protocol

from finalprosports.domain.model import *  # noqa: F401,F403  (structural typing only)
from finalprosports.domain.model.client_record import ClientRecord, Identification


class ClientRecordOutputPort(Protocol):
    def get(self, professional_id: str, client_code: str) -> ClientRecord | None: ...

    def save(self, record: ClientRecord) -> ClientRecord: ...

    def list_identifications(self, professional_id: str) -> dict[str, Identification]:
        """client key -> identification block of every portfolio client (S9: the list and the headers show the NAME, never the key)."""
        ...
