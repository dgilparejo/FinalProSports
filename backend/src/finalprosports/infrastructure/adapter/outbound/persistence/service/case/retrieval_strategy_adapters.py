"""The four retrieval strategies (E3.2), each a CaseRepositoryOutputPort on Postgres + pgvector.

  vector                 cosine over the retrieval-text embeddings, no prefilter                       (baseline)
  goal_filtered_vector   prefilter by the professional's goal, cosine order inside
  attributes             weighted attribute match only (domain policy), no vectors, deterministic
  hybrid                 prefilter by goal (+ sex when known); alpha * min-max-normalised cosine + (1 - alpha) * attributes

Ranking logic that has domain meaning (attribute weights, mixing) lives in the domain policy; here only SQL and glue.
The factory `case_repository_for` is what the composition root calls with Settings.retrieval_strategy.
"""
from __future__ import annotations

from finalprosports.application.strategy.retrieval_strategy import RetrievalStrategy
from finalprosports.domain.composition.policy.attribute_similarity_policy import DEFAULT_WEIGHTS, AttributeWeights, attribute_score, hybrid_score
from finalprosports.domain.model import CaseQuery, RetrievedCase, SimilarityScore

from .case_repository_output_adapter import Candidate, CaseRepositoryBase


class VectorCaseRepositoryAdapter(CaseRepositoryBase):
    requires_embedding = True

    def find_similar(self, professional_id: str, query: CaseQuery, k: int, exclude_diet_ids: frozenset[str]) -> tuple[RetrievedCase, ...]:
        with self._sf() as s:
            cands = self.candidates(s, professional_id, query, exclude_diet_ids, with_cosine=True, order_by_cosine=True, limit=k)
            return self.hydrate(s, professional_id, [(c, SimilarityScore(c.cosine, 0.0, c.cosine)) for c in cands])


class GoalFilteredVectorCaseRepositoryAdapter(CaseRepositoryBase):
    requires_embedding = True

    def find_similar(self, professional_id: str, query: CaseQuery, k: int, exclude_diet_ids: frozenset[str]) -> tuple[RetrievedCase, ...]:
        with self._sf() as s:
            cands = self.candidates(s, professional_id, query, exclude_diet_ids, with_cosine=True, goal=query.profile.goal, order_by_cosine=True, limit=k)
            if len(cands) < k:                                                 # goal with fewer diets than k: complete without the filter
                seen = {c.diet_id for c in cands}
                cands += [c for c in self.candidates(s, professional_id, query, exclude_diet_ids | seen, with_cosine=True, order_by_cosine=True, limit=k - len(cands))]
            return self.hydrate(s, professional_id, [(c, SimilarityScore(c.cosine, 0.0, c.cosine)) for c in cands])


class AttributeCaseRepositoryAdapter(CaseRepositoryBase):
    requires_embedding = False

    def __init__(self, session_factory, weights: AttributeWeights = DEFAULT_WEIGHTS):
        super().__init__(session_factory)
        self._w = weights

    def find_similar(self, professional_id: str, query: CaseQuery, k: int, exclude_diet_ids: frozenset[str],
                     enrich=None) -> tuple[RetrievedCase, ...]:
        """`enrich(candidate) -> candidate` puebla el lado del CASO con datos que `CANDIDATE_SQL` no trae.

        Existe para los rasgos cuyo dato no es una columna del perfil sino una SERIE FECHADA -- hoy, las mediciones
        analiticas: 189 parametros por cliente, resueltos a la fecha de CADA dieta candidata. Traerlos en la consulta
        exigiria un LATERAL por parametro. Lo usa el barrido de pesos; la ruta de produccion no lo pasa, y por eso el
        peso de esos rasgos es 0,00 mientras no se decida lo contrario.
        """
        with self._sf() as s:
            cands = self.candidates(s, professional_id, query, exclude_diet_ids, with_cosine=False)
            if enrich is not None:
                cands = [enrich(c) for c in cands]
            scored = sorted(((c, attribute_score(query.profile, c.profile, self._w)) for c in cands), key=lambda t: (-t[1], t[0].diet_id))[:k]
            return self.hydrate(s, professional_id, [(c, SimilarityScore(0.0, a, a)) for c, a in scored])


class HybridCaseRepositoryAdapter(CaseRepositoryBase):
    requires_embedding = True

    def __init__(self, session_factory, weights: AttributeWeights = DEFAULT_WEIGHTS, alpha: float = 0.5, prefilter_sex: bool = True):
        super().__init__(session_factory)
        self._w, self._alpha, self._prefilter_sex = weights, alpha, prefilter_sex

    def find_similar(self, professional_id: str, query: CaseQuery, k: int, exclude_diet_ids: frozenset[str]) -> tuple[RetrievedCase, ...]:
        p = query.profile
        with self._sf() as s:
            cands = self.candidates(s, professional_id, query, exclude_diet_ids, with_cosine=True, goal=p.goal, sex=p.sex if self._prefilter_sex else None)
            if len(cands) < k:                                                 # relax the prefilter when the goal (+ sex) has too few diets
                cands = self.candidates(s, professional_id, query, exclude_diet_ids, with_cosine=True, goal=p.goal)
            if len(cands) < k:
                cands = self.candidates(s, professional_id, query, exclude_diet_ids, with_cosine=True)
            ranked = self.rank(p, cands, k)
            return self.hydrate(s, professional_id, ranked)

    def rank(self, profile, cands: list[Candidate], k: int) -> list[tuple[Candidate, SimilarityScore]]:
        if not cands:
            return []
        lo, hi = min(c.cosine for c in cands), max(c.cosine for c in cands)
        span = (hi - lo) or 1.0
        scored = []
        for c in cands:
            attr = attribute_score(profile, c.profile, self._w)
            scored.append((c, SimilarityScore(c.cosine, attr, hybrid_score((c.cosine - lo) / span, attr, self._alpha))))
        scored.sort(key=lambda t: (-t[1].total, t[0].diet_id))
        return scored[:k]


def case_repository_for(strategy: RetrievalStrategy | str, session_factory, weights: AttributeWeights = DEFAULT_WEIGHTS, alpha: float = 0.5) -> CaseRepositoryBase:
    strategy = RetrievalStrategy(strategy)
    if strategy is RetrievalStrategy.VECTOR:
        return VectorCaseRepositoryAdapter(session_factory)
    if strategy is RetrievalStrategy.GOAL_FILTERED_VECTOR:
        return GoalFilteredVectorCaseRepositoryAdapter(session_factory)
    if strategy is RetrievalStrategy.ATTRIBUTES:
        return AttributeCaseRepositoryAdapter(session_factory, weights)
    return HybridCaseRepositoryAdapter(session_factory, weights, alpha)
