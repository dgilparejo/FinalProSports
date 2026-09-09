"""Common persistence base of the four CaseRepositoryOutputPort implementations (Postgres + pgvector).

- Hydration without N+1 (E3.3): the k diets and ALL their items are loaded in two statements (`id = ANY(...)`), not 2 per case.
- Candidate rows: one statement joining diets with client_profiles gives every attribute the strategies need (goal of the
  diet, sex/age/activity/flags of the client) and, when asked, the cosine similarity to the query vector.
- Deliberately NO HNSW/IVFFlat index: ~1.000 rows scan in ~2 ms and attribute prefilters (professional_id, goal, excluded ids of
  the leave-one-out) would degrade the recall of an approximate index. ORDER BY embedding <=> :q, with :q a TYPED vector parameter
  (pgvector psycopg adapter registered in config/persistence.py): a text parameter cast per row cost ~46 ms.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from finalprosports.domain.composition.policy.gap_policy import CandidateCounts
from finalprosports.domain.composition.policy.retrieval_text_policy import age_bucket
from finalprosports.domain.model import CaseQuery, ClientProfile, Diet, Goal, RestrictionKind, RetrievedCase, SimilarityScore
from finalprosports.infrastructure.adapter.outbound.persistence.entity.diet_entity import DietEntity, DietItemEntity
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.diet_mapper import to_domain


def _num(v):
    return float(v) if v is not None else None


def _body(r) -> dict:
    """Los ocho campos de la lectura que el LATERAL eligió, o None en los ocho cuando no había ninguna anterior."""
    if r.bm_at is None:
        return {}
    return {"measured_at": r.bm_at.date().isoformat(), "weight_kg": _num(r.bm_weight), "fat_pct": _num(r.bm_fat),
            "muscle_mass_kg": _num(r.bm_muscle), "hydration_pct": _num(r.bm_water), "bone_mass_kg": _num(r.bm_bone),
            "physique_rating": r.bm_physique, "visceral_fat_rating": _num(r.bm_visceral),
            "metabolic_age": r.bm_metage, "basal_met_kcal": r.bm_basal}


@dataclass(frozen=True)
class Candidate:
    diet_id: str
    profile: ClientProfile            # the case's client attributes with the DIET's goal
    cosine: float | None


# El LATERAL de la báscula aplica la REGLA TEMPORAL dentro de la propia consulta: de todas las lecturas del cliente del
# caso, la más reciente ESTRICTAMENTE anterior a la fecha del documento de ESA dieta. No es una optimización — es el
# único sitio donde puede aplicarse sin equivocarse, porque la fecha de corte es distinta para cada candidato: dos
# dietas del mismo cliente separadas por dos años tienen que ver básculas distintas. Resolverlo fuera obligaría a
# traer la serie entera de cada cliente y a recordar, por candidato, con qué fecha filtrarla.
# Una dieta sin `doc_date` no recibe lectura (la comparación con NULL es NULL, y el LATERAL sale vacío): correcto por
# construcción, porque sin fecha no se puede afirmar que ninguna lectura la precediera.
CANDIDATE_SQL = """
    SELECT d.id, d.goal, d.has_intolerances, p.sex, p.age, p.height_cm, p.activity_level, p.has_allergies, p.has_medical_restrictions, p.is_athlete,
           p.sport, p.body_type, p.training_time, d.methods,
           bm.measured_at AS bm_at, bm.weight_kg AS bm_weight, bm.body_fat_pct AS bm_fat, bm.muscle_mass_kg AS bm_muscle,
           bm.water_pct AS bm_water, bm.bone_kg AS bm_bone, bm.physique_rating AS bm_physique,
           bm.visceral_fat_rating AS bm_visceral, bm.metabolic_age AS bm_metage, bm.basal_met_kcal AS bm_basal
           {cosine_col}
    FROM diets d
    JOIN client_profiles p ON p.professional_id = d.professional_id AND p.client_code = d.client_code
    LEFT JOIN LATERAL (
        SELECT b.* FROM body_measurements b
        WHERE b.professional_id = d.professional_id AND b.client_code = d.client_code
          AND b.measured_at::date < d.doc_date
        ORDER BY b.measured_at DESC LIMIT 1
    ) bm ON TRUE
    WHERE d.professional_id = :pid AND NOT (d.id = ANY(:excluded)) {vector_filter} {goal_filter} {sex_filter}
    {order} {limit}
"""


class CaseRepositoryBase:
    requires_embedding: bool = True

    def __init__(self, session_factory):
        self._sf = session_factory

    # ------------------------------------------------------------------------------------------------------ hydration (E3.3)
    @staticmethod
    def load_diets(s: Session, professional_id: str, ids: list[str]) -> dict[str, Diet]:
        if not ids:
            return {}
        diets = s.execute(select(DietEntity).where(DietEntity.professional_id == professional_id, DietEntity.id.in_(ids))).scalars().all()
        items = s.execute(select(DietItemEntity).where(DietItemEntity.professional_id == professional_id, DietItemEntity.diet_id.in_(ids))).scalars().all()
        by_diet: dict[str, list[DietItemEntity]] = {d.id: [] for d in diets}
        for it in items:
            by_diet[it.diet_id].append(it)
        return {d.id: to_domain(d, by_diet[d.id]) for d in diets}

    def get(self, professional_id: str, diet_id: str) -> Diet:
        with self._sf() as s:
            return self.load_diets(s, professional_id, [diet_id])[diet_id]

    def all_diets(self, professional_id: str) -> dict[str, Diet]:
        """Every diet of the professional, hydrated in two statements (evaluation adapters)."""
        with self._sf() as s:
            return self.load_diets(s, professional_id, list(self.all_ids(professional_id)))

    def all_ids(self, professional_id: str) -> tuple[str, ...]:
        with self._sf() as s:
            return tuple(s.execute(select(DietEntity.id).where(DietEntity.professional_id == professional_id)).scalars().all())

    def diet_ids_of_client(self, professional_id: str, client_code: str) -> frozenset[str]:
        with self._sf() as s:
            return frozenset(s.execute(select(DietEntity.id).where(DietEntity.professional_id == professional_id, DietEntity.client_code == client_code)).scalars())

    def diet_ids_sharing_template_with(self, professional_id: str, client_code: str) -> frozenset[str]:
        with self._sf() as s:
            rows = s.execute(text("SELECT d2.id FROM diets d1 JOIN diets d2 ON d2.professional_id = d1.professional_id AND d2.template_group_id = d1.template_group_id "
                                  "WHERE d1.professional_id = :pid AND d1.client_code = :c AND d1.template_group_id IS NOT NULL"), {"pid": professional_id, "c": client_code})
            return frozenset(r[0] for r in rows)

    # ------------------------------------------------------------------------------------------------------------- candidates
    def candidates(self, s: Session, professional_id: str, query: CaseQuery, excluded: frozenset[str], *, with_cosine: bool,
                   goal: Goal | None = None, sex: str | None = None, order_by_cosine: bool = False, limit: int | None = None) -> list[Candidate]:
        sql = CANDIDATE_SQL.format(
            cosine_col=", 1 - (d.embedding <=> :q) AS cosine" if with_cosine else ", NULL AS cosine",      # :q is a typed vector parameter (see config/persistence.py)
            vector_filter="AND d.embedding IS NOT NULL" if with_cosine else "",
            # A regime declared as the diet's METHOD makes it just as much a neighbour as one that declared it
            # as its goal: "ayuno intermitente para perder grasa" has goal=definicion_grasa and
            # method=ayuno_intermitente, and it is a fasting diet either way. Filtering on `goal` alone left a
            # fasting client with the 74 diets that named fasting as their purpose instead of the 253 that
            # follow the regime, and the composer then could not reach consensus on the 16-hour note that the
            # professional writes in 90 % of them. Symmetric in the other direction by construction: a diet
            # whose goal IS the regime still matches.
            goal_filter="AND (d.goal = :goal OR :goal = ANY(d.methods))" if goal is not None else "",
            sex_filter="AND (p.sex = :sex OR p.sex IS NULL)" if sex is not None else "",
            order="ORDER BY d.embedding <=> :q, d.id" if order_by_cosine else "ORDER BY d.id",
            limit="LIMIT :k" if limit is not None else "")
        params = {"pid": professional_id, "excluded": list(excluded)}
        if with_cosine:
            params["q"] = np.asarray(query.embedding, dtype=np.float32)      # binary vector parameter: no per-row text parse
        if goal is not None:
            params["goal"] = goal.value
        if sex is not None:
            params["sex"] = sex
        if limit is not None:
            params["k"] = limit
        rows = s.execute(text(sql), params).all()
        return [Candidate(r.id, ClientProfile("", professional_id, r.sex, r.age, r.height_cm, r.activity_level, goal=Goal(r.goal),
                                        sport=r.sport, body_type=r.body_type, training_time=r.training_time,
                                        methods=tuple(r.methods or ()),
                                              has_allergies=bool(r.has_allergies), has_intolerances=bool(r.has_intolerances),
                                              has_medical_restrictions=bool(r.has_medical_restrictions), is_athlete=r.is_athlete,
                                              **_body(r)),
                          float(r.cosine) if r.cosine is not None else None) for r in rows]

    RESTRICTION_FLAGS = frozenset(k.value for k in RestrictionKind)       # whitelist of foods.* boolean columns

    def candidate_counts(self, professional_id: str, profile: ClientProfile, exclude_diet_ids: frozenset[str]) -> CandidateCounts:
        """Availability counts for the gap policy, in ONE statement: total, same goal, same goal and free of vetoed foods,
        same archetype (sex x age bucket x goal), free of vetoed foods. A diet is 'free' when none of its mapped items is a
        food carrying any flag vetoed by the profile's structured restrictions (unmapped items cannot be checked)."""
        flags = sorted({r.kind.value for r in profile.restrictions if r.kind.value in self.RESTRICTION_FLAGS})
        vetoed = " OR ".join(f"f.{c}" for c in flags) or "FALSE"
        free = (f"NOT EXISTS (SELECT 1 FROM diet_items i JOIN foods f ON f.professional_id = i.professional_id AND f.id = i.food_id "
                f"WHERE i.professional_id = d.professional_id AND i.diet_id = d.id AND ({vetoed}))")
        bucket_sql = "CASE WHEN p.age IS NULL THEN 'edad_NA' WHEN p.age < 25 THEN '<25' WHEN p.age < 40 THEN '25-39' WHEN p.age < 55 THEN '40-54' ELSE '55+' END"
        sql = f"""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE d.goal = :goal) AS same_goal,
                   count(*) FILTER (WHERE d.goal = :goal AND {free}) AS same_goal_free,
                   count(*) FILTER (WHERE d.goal = :goal AND p.sex IS NOT DISTINCT FROM :sex AND {bucket_sql} = :bucket) AS archetype,
                   count(*) FILTER (WHERE {free}) AS restriction_free
            FROM diets d JOIN client_profiles p ON p.professional_id = d.professional_id AND p.client_code = d.client_code
            WHERE d.professional_id = :pid AND NOT (d.id = ANY(:excluded))"""
        with self._sf() as s:
            r = s.execute(text(sql), {"pid": professional_id, "excluded": list(exclude_diet_ids), "goal": profile.goal.value if profile.goal else None,
                                      "sex": profile.sex, "bucket": age_bucket(profile.age)}).one()
        return CandidateCounts(int(r.total), int(r.same_goal), int(r.same_goal_free), int(r.archetype), int(r.restriction_free), len(flags))

    def hydrate(self, s: Session, professional_id: str, ranked: list[tuple[Candidate, SimilarityScore]]) -> tuple[RetrievedCase, ...]:
        diets = self.load_diets(s, professional_id, [c.diet_id for c, _ in ranked])
        return tuple(RetrievedCase(diet=diets[c.diet_id], score=score, rank=i + 1, case_profile=c.profile) for i, (c, score) in enumerate(ranked))

    def doc_dates(self, professional_id: str) -> dict[str, str | None]:
        """La fecha del documento de cada dieta, en ISO. La necesitan los arneses para aplicar la regla temporal por su
        cuenta (el LATERAL solo la resuelve para el lado del CASO; el de la CONSULTA lo construye quien mide)."""
        with self._sf() as s:
            rows = s.execute(text("SELECT id, doc_date FROM diets WHERE professional_id = :p"), {"p": professional_id}).all()
        return {r.id: r.doc_date.isoformat() if r.doc_date is not None else None for r in rows}

    def diagnostics(self, professional_id: str) -> dict:
        """Server/extension versions and corpus counts (for the evaluation adapters' reports; no domain meaning)."""
        with self._sf() as s:
            pg = s.execute(text("SHOW server_version")).scalar()
            pgv = s.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
            n, n_vec = s.execute(text("SELECT count(*), count(embedding) FROM diets WHERE professional_id = :p"), {"p": professional_id}).one()
        return {"postgres": pg, "pgvector_extension": pgv, "diets": int(n), "with_embedding": int(n_vec)}
