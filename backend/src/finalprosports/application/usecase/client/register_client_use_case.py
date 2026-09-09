"""RegisterClientUseCase (S1): a client of the portfolio is registered BY NAME, as the professional's
intake sheet asks; the KEY is a UUID the application generates and nobody types. The identity (name, birth date, phone, e-mail) is
written to the record; the profile — what the engine sees — receives only the key, the algorithm inputs and the age derived from
the birth date. Codes of the case base (``CLIENTE_NNN``) can never be a portfolio key: the repository refuses them, and the key format
(UUID) makes a collision impossible by construction."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date

from finalprosports.application.port.outbound.persistence.client.client_repository_output_port import ClientRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.record.client_record_output_port import ClientRecordOutputPort
from finalprosports.domain.model import ClientProfile
from finalprosports.domain.model.client_profile import is_portfolio_key
from finalprosports.domain.model.client_record import ClientRecord, Identification


def age_on(birth_date: date | None, today: date) -> int | None:
    if birth_date is None:
        return None
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


class RegisterClientUseCase:
    def __init__(self, clients: ClientRepositoryOutputPort, records: ClientRecordOutputPort):
        self._clients, self._records = clients, records

    def register(self, draft: ClientProfile, identification: Identification, client_id: str | None = None, today: date | None = None) -> ClientProfile:
        """``draft.client_code`` is ignored: the key is ``client_id`` (must be a UUID; demos pass a deterministic one) or a fresh uuid4."""
        name = (identification.full_name or "").strip()
        if len(name) < 2:
            raise ValueError("a client of the portfolio is registered by name")
        key = client_id or str(uuid.uuid4())
        if not is_portfolio_key(key):
            raise ValueError("the key of a portfolio client is a UUID assigned by the application")
        today = today or date.today()
        age = age_on(identification.birth_date, today)
        profile = replace(draft, client_code=key, is_corpus_case=False, age=age if age is not None else draft.age)
        saved = self._clients.save(profile)
        self._records.save(ClientRecord(key, profile.professional_id, identification=replace(identification, full_name=name)))
        return saved
