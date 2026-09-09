"""ProposalRepositoryOutputPort on Postgres: saved_diets (payload jsonb = the whole proposal, evidence and validation included).
Reads are scoped to the PORTFOLIO (S1): a diet saved under a code of the case base is never served."""
from __future__ import annotations

import json

from sqlalchemy import text

from finalprosports.domain.model import DietProposal
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.proposal_mapper import proposal_from_dict, proposal_to_dict


class ProposalRepositoryOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    def _next_id(self, s, professional_id: str, client_code: str) -> str:
        n = s.execute(text("SELECT count(*) FROM saved_diets WHERE professional_id = :p AND client_code = :c"), {"p": professional_id, "c": client_code}).scalar() or 0
        return f"{client_code}::e{n + 1:02d}"

    def save(self, professional_id: str, proposal: DietProposal, edited: bool, original: DietProposal | None = None, diff=None) -> str:
        with self._sf() as s:
            diet_id = self._next_id(s, professional_id, proposal.profile.client_code)
            s.execute(text("INSERT INTO saved_diets (id, professional_id, client_code, goal, strategy, edited, payload, original_payload, diff) "
                           "VALUES (:id, :p, :c, :g, :st, :e, CAST(:payload AS jsonb), CAST(:original AS jsonb), CAST(:diff AS jsonb))"),
                      {"id": diet_id, "p": professional_id, "c": proposal.profile.client_code, "g": proposal.profile.goal.value if proposal.profile.goal else "sin_clasificar",
                       "st": proposal.strategy, "e": edited, "payload": json.dumps(proposal_to_dict(proposal), ensure_ascii=False, default=str),
                       "original": json.dumps(proposal_to_dict(original), ensure_ascii=False, default=str) if original is not None else None,
                       "diff": json.dumps(diff.as_dict(), ensure_ascii=False, default=str) if diff is not None else None})
            s.commit()
            return diet_id

    def get(self, professional_id: str, diet_id: str) -> DietProposal | None:
        with self._sf() as s:
            row = s.execute(text("SELECT d.payload FROM saved_diets d JOIN client_profiles p ON p.professional_id = d.professional_id AND p.client_code = d.client_code "
                                  "WHERE d.professional_id = :p AND d.id = :id AND NOT p.is_corpus_case"), {"p": professional_id, "id": diet_id}).first()
            return proposal_from_dict(row[0] if isinstance(row[0], dict) else json.loads(row[0])) if row else None

    def get_detail(self, professional_id: str, diet_id: str) -> dict | None:
        """Metadata + diff of a saved diet (S5): id, created_at, edited, strategy, goal, diff (None when saved without the original)."""
        with self._sf() as s:
            row = s.execute(text("SELECT d.id, d.created_at, d.goal, d.strategy, d.edited, d.diff, d.original_payload IS NOT NULL AS has_original FROM saved_diets d "
                                  "JOIN client_profiles p ON p.professional_id = d.professional_id AND p.client_code = d.client_code "
                                  "WHERE d.professional_id = :p AND d.id = :id AND NOT p.is_corpus_case"), {"p": professional_id, "id": diet_id}).first()
            if row is None:
                return None
            diff = row.diff if isinstance(row.diff, dict) or row.diff is None else json.loads(row.diff)
            return {"id": row.id, "created_at": row.created_at.isoformat(), "goal": row.goal, "strategy": row.strategy, "edited": row.edited, "diff": diff, "has_original": bool(row.has_original)}

    def list_for_client(self, professional_id: str, client_code: str) -> tuple[dict, ...]:
        with self._sf() as s:
            rows = s.execute(text("SELECT d.id, d.created_at, d.goal, d.strategy, d.edited, (d.diff->>'edit_ratio')::float AS edit_ratio FROM saved_diets d JOIN client_profiles p ON p.professional_id = d.professional_id "
                                  "AND p.client_code = d.client_code WHERE d.professional_id = :p AND d.client_code = :c AND NOT p.is_corpus_case ORDER BY d.created_at"),
                             {"p": professional_id, "c": client_code}).all()
            return tuple({"id": r.id, "created_at": r.created_at.isoformat(), "goal": r.goal, "strategy": r.strategy, "edited": r.edited, "edit_ratio": r.edit_ratio} for r in rows)

    def delete_for_corpus_clients(self, professional_id: str) -> int:
        """S1 clean-up: a diet saved under a code of the case base (possible before S1) is unreachable and is removed."""
        with self._sf() as s:
            n = s.execute(text("DELETE FROM saved_diets d USING client_profiles p WHERE p.professional_id = d.professional_id AND p.client_code = d.client_code "
                               "AND d.professional_id = :p AND p.is_corpus_case"), {"p": professional_id}).rowcount
            s.commit()
            return int(n or 0)
