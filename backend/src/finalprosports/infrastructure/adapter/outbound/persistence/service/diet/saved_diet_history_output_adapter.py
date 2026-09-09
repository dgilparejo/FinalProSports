"""DietRepositoryOutputPort.history for the PORTFOLIO (S1): the versions of a client of the application are the diets the
professional saved for him (``saved_diets``), converted to ``Diet`` so that the routing (same goal -> rotate the previous version)
and the RotationComposer see them exactly as they see a prescribed version of the corpus. The corpus is never a client's history
here: the case base only enters through retrieval."""
from __future__ import annotations

import json
import re

from sqlalchemy import text

from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.domain.model import Diet
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.proposal_mapper import proposal_from_dict

_VERSION = re.compile(r"::e(\d+)$")


def version_of(diet_id: str) -> int | None:
    m = _VERSION.search(diet_id)
    return int(m.group(1)) if m else None


class SavedDietHistoryOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    def history(self, professional_id: str, client_code: str) -> tuple[Diet, ...]:
        with self._sf() as s:
            rows = s.execute(text("SELECT d.id, d.payload FROM saved_diets d JOIN client_profiles p ON p.professional_id = d.professional_id AND p.client_code = d.client_code "
                                  "WHERE d.professional_id = :p AND d.client_code = :c AND NOT p.is_corpus_case ORDER BY d.created_at, d.id"),
                             {"p": professional_id, "c": client_code}).all()
        out = []
        for diet_id, payload in rows:
            proposal = proposal_from_dict(payload if isinstance(payload, dict) else json.loads(payload))
            diet = to_diet(proposal, diet_id)
            out.append(Diet(**{**diet.__dict__, "diet_version": version_of(diet_id)}))
        return tuple(out)

    def count(self, professional_id: str, client_code: str) -> int:
        return len(self.history(professional_id, client_code))

    def save(self, diet: Diet) -> Diet:
        raise NotImplementedError("saved diets are written by ProposalRepositoryOutputPort (SaveEditedDietUseCase)")
