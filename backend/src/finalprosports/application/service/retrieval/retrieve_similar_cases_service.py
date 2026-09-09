"""Retrieval service (E3.4) — implements RetrieveSimilarCasesInputPort.

1. Mandatory exclusions: the client's own diets and every diet of the template groups the client belongs to (retrieving
   the same document delivered to several clients would be a leak, not a prediction), plus the caller's exclusions (LOO).
2. Query text built by the domain policy with the same header as the documents; vectorised only if the wired strategy
   needs it (attribute-only retrieval makes no model call).
3. Delegates ranking to the CaseRepositoryOutputPort implementation selected by configuration (vector, goal-filtered
   vector, attributes, hybrid).
4. Gap assessment (domain gap_policy): candidate scarcity after hard filters, poor archetype, restriction incompatibility, low
   score - logged to the gaps table with the first triggered condition as kind and the whole assessment as payload.
"""
from finalprosports.application.port.outbound.embeddings.embedder_output_port import EmbedderOutputPort
from finalprosports.application.port.outbound.persistence.case.case_repository_output_port import CaseRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.gap.gap_log_output_port import GapLogOutputPort
from finalprosports.application.service.annotation import timed
from finalprosports.domain.composition.policy.gap_policy import GapAssessment, assess_gap
from finalprosports.domain.composition.policy.neighbourhood_policy import OVERFETCH, Neighbourhood, select
from finalprosports.domain.composition.policy.retrieval_text_policy import query_text
from finalprosports.domain.model import CaseQuery, ClientProfile, RetrievedCase

profile_query_text = query_text          # kept for callers that imported the old name


class RetrieveSimilarCasesService:
    def __init__(self, embedder: EmbedderOutputPort, cases: CaseRepositoryOutputPort, gaps: GapLogOutputPort | None = None,
                 similarity_threshold: float = 0.80):
        self._embedder, self._cases, self._gaps, self._threshold = embedder, cases, gaps, similarity_threshold
        self.last_assessment: GapAssessment | None = None
        self.last_neighbourhood: Neighbourhood | None = None

    def mandatory_exclusions(self, professional_id: str, profile: ClientProfile, include_own_history: bool = False) -> frozenset[str]:
        """Template groups are always excluded; the client's own diets are excluded unless the caller explicitly allows the history
        (recurrent client: in production the professional has the client's previous versions in front of him)."""
        # Los códigos bajo los que este cliente puede aparecer en la base de casos: el suyo de cartera y, si el
        # profesional lo ha declarado, el seudónimo con el que ya era caso antes de existir la aplicación. Sin el
        # segundo, la exclusión mira un código que en el corpus no existe y le devuelve sus propias dietas como si
        # fueran de otra persona (`ClientProfile.corpus_alias`).
        codes = [profile.client_code] + ([profile.corpus_alias] if profile.corpus_alias else [])
        templates = frozenset().union(*(self._cases.diet_ids_sharing_template_with(professional_id, c) for c in codes))
        if include_own_history:
            # Aun permitiendo su historial de CARTERA, las dietas de su seudónimo siguen siendo suyas y no son casos.
            alias_own = (self._cases.diet_ids_of_client(professional_id, profile.corpus_alias)
                         if profile.corpus_alias else frozenset())
            return templates | alias_own
        return frozenset().union(*(self._cases.diet_ids_of_client(professional_id, c) for c in codes)) | templates

    def query_for(self, profile: ClientProfile) -> CaseQuery:
        if not self._cases.requires_embedding:
            return CaseQuery(profile, None)
        return CaseQuery(profile, tuple(self._embedder.embed_query(query_text(profile))))

    @timed
    def retrieve(self, professional_id: str, profile: ClientProfile, k: int = 5, exclude_diet_ids: frozenset[str] = frozenset(),
                 include_own_history: bool = False) -> tuple[RetrievedCase, ...]:
        excluded = frozenset(exclude_diet_ids) | self.mandatory_exclusions(professional_id, profile, include_own_history)
        # Se piden MÁS candidatos de los que se van a usar y la selección la hace la política de dominio (D3: un caso
        # por cliente, pureza primero). Pedir exactamente k y quedarse con ellos era lo que concentraba el vecindario
        # en siete clientes, porque varias versiones del mismo cliente comparten perfil y entran juntas.
        pool = self._cases.find_similar(professional_id, self.query_for(profile), k * OVERFETCH, excluded)
        self.last_neighbourhood = select(pool, profile.goal, k)
        result = self.last_neighbourhood.cases
        if self._gaps is not None:
            self.last_assessment = self.assess(professional_id, profile, k, excluded, result)
            if self.last_assessment.is_gap:
                a = self.last_assessment
                self._gaps.log(professional_id, a.kind, {"client_code": profile.client_code, "goal": profile.goal.value if profile.goal else None, "k": k,
                                                       "triggered": list(a.triggered), "counts": vars(a.counts), "best_score": a.best_score,
                                                       "threshold": a.threshold, "excluded": len(excluded)})
        return result

    def assess(self, professional_id: str, profile: ClientProfile, k: int, excluded: frozenset[str], result: tuple[RetrievedCase, ...]) -> GapAssessment:
        counts = self._cases.candidate_counts(professional_id, profile, excluded)
        return assess_gap(counts, k, result[0].score.total if result else None, self._threshold)
