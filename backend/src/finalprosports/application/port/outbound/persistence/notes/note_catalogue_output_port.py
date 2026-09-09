"""Outbound port: the catalogue of canonical notes mined from the corpus (E9, realism batch).
One implementation today (file produced by pipeline/build_canonical_notes.py). When it is absent the composer falls back to
the literal-string consensus it always used."""
from typing import Protocol

from finalprosports.domain.composition.policy.note_catalogue import NoteCatalogue


class NoteCatalogueOutputPort(Protocol):
    def load(self, professional_id: str) -> NoteCatalogue | None: ...
