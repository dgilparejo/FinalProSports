"""ClientRepositoryOutputPort on Postgres (S1): the PORTFOLIO and the CASE BASE share the table but never the queries.

``get`` / ``list`` / ``save`` / ``count_saved_diets`` are scoped to ``is_corpus_case = false`` — the clients the professional
registered in the application. The 467 pseudonymous corpus profiles are reachable only through ``list_case_profiles`` (retrieval
strategies, evaluation adapters). Saving under a corpus code is refused: the case base is frozen (dataset-v1) and must never be
overwritten by the registration form."""
from sqlalchemy import select, text

from finalprosports.application.exception.client.client_code_reserved_error import ClientCodeReservedError
from finalprosports.domain.model import ClientProfile
from finalprosports.infrastructure.adapter.outbound.persistence.entity.client_profile_entity import ClientProfileEntity
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.client_profile_mapper import to_domain


class ClientRepositoryOutputAdapter:
    def __init__(self, session_factory):
        self._sf = session_factory

    # ------------------------------------------------------------------------------------------------------- portfolio
    def get(self, professional_id: str, client_code: str) -> ClientProfile | None:
        with self._sf() as s:
            e = s.execute(select(ClientProfileEntity).where(ClientProfileEntity.professional_id == professional_id,
                                                            ClientProfileEntity.client_code == client_code,
                                                            ClientProfileEntity.is_corpus_case.is_(False))).scalar_one_or_none()
            return to_domain(e) if e else None

    def list(self, professional_id: str) -> tuple[ClientProfile, ...]:
        with self._sf() as s:
            rows = s.execute(select(ClientProfileEntity).where(ClientProfileEntity.professional_id == professional_id,
                                                               ClientProfileEntity.is_corpus_case.is_(False)).order_by(ClientProfileEntity.client_code)).scalars()
            return tuple(to_domain(e) for e in rows)

    def count_saved_diets(self, professional_id: str) -> dict[str, int]:
        """client_code -> number of diets saved in the application (one statement, portfolio only)."""
        with self._sf() as s:
            rows = s.execute(text("SELECT d.client_code, count(*) FROM saved_diets d JOIN client_profiles p ON p.professional_id = d.professional_id "
                                  "AND p.client_code = d.client_code WHERE d.professional_id = :p AND NOT p.is_corpus_case GROUP BY d.client_code"),
                             {"p": professional_id}).all()
            return {r[0]: int(r[1]) for r in rows}

    def save(self, profile: ClientProfile) -> ClientProfile:
        """Insert or update a PORTFOLIO profile (pseudonymous code; health only as booleans + structured restrictions).
        A code that belongs to the case base is reserved: the corpus is never edited through the application."""
        with self._sf() as s:
            reserved = s.execute(text("SELECT 1 FROM client_profiles WHERE professional_id = :p AND client_code = :c AND is_corpus_case"),
                                 {"p": profile.professional_id, "c": profile.client_code}).first()
            if reserved or profile.is_corpus_case:
                raise ClientCodeReservedError(profile.client_code)
            s.execute(text("""
                INSERT INTO client_profiles (client_code, professional_id, sex, age, age_bucket, height_cm, activity_level, activity_level_reported, is_athlete,
                                             goals, has_allergies, has_intolerances, has_medical_restrictions, diet_count, diet_count_raw, diet_count_stored,
                                             empty_profile, unmapped, suspicious_demographics, field_carryover_suspected, restrictions, is_corpus_case,
                                             sport, disliked_food_ids, liked_food_ids, owned_supplement_ids, body_type, training_time, corpus_alias)
                VALUES (:c, :p, :sex, :age, :bucket, :h, :act, :act_rep, :ath, :goals, :al, :intol, :med, 0, 0, 0, false, false, false, false, :restr, false,
                        :sport, :disliked, :liked, :owned, :body_type, :training_time, :corpus_alias)
                ON CONFLICT (professional_id, client_code) DO UPDATE SET sex = EXCLUDED.sex, age = EXCLUDED.age, age_bucket = EXCLUDED.age_bucket,
                    height_cm = EXCLUDED.height_cm, activity_level = EXCLUDED.activity_level, activity_level_reported = EXCLUDED.activity_level_reported,
                    is_athlete = EXCLUDED.is_athlete, goals = EXCLUDED.goals, has_allergies = EXCLUDED.has_allergies, has_intolerances = EXCLUDED.has_intolerances,
                    has_medical_restrictions = EXCLUDED.has_medical_restrictions, restrictions = EXCLUDED.restrictions,
                    sport = EXCLUDED.sport, disliked_food_ids = EXCLUDED.disliked_food_ids, liked_food_ids = EXCLUDED.liked_food_ids, owned_supplement_ids = EXCLUDED.owned_supplement_ids,
                    body_type = EXCLUDED.body_type, training_time = EXCLUDED.training_time,
                    corpus_alias = EXCLUDED.corpus_alias
                WHERE NOT client_profiles.is_corpus_case"""),
                      {"c": profile.client_code, "p": profile.professional_id, "sex": profile.sex, "age": profile.age,
                       "bucket": profile.age_bucket if profile.age is not None else None, "h": profile.height_cm, "act": profile.activity_level,
                       "act_rep": profile.activity_level is not None, "ath": profile.is_athlete, "goals": profile.goal.value if profile.goal else None,
                       "al": profile.has_allergies, "intol": profile.has_intolerances, "med": profile.has_medical_restrictions,
                       "restr": [r.kind.value for r in profile.restrictions], "sport": profile.sport,
                       "disliked": list(profile.disliked_food_ids), "liked": list(profile.liked_food_ids), "owned": list(profile.owned_supplement_ids),
                       # 0013: los dos rasgos que la similitud consulta. Sin escribirlos aqui, el caso de uso los
                       # sincroniza, el objeto los lleva y la fila se guarda con NULL: el peso 0,10 de `body_type`
                       # no hace nada para ningun cliente de la cartera. Fijado por test de arquitectura.
                       "body_type": profile.body_type, "training_time": profile.training_time,
                       # 0014: el puente cartera <-> base de casos. Se guarda aqui porque la exclusion obligatoria
                       # de la recuperacion lo lee del PERFIL, no de una tabla aparte.
                       "corpus_alias": profile.corpus_alias})
            s.commit()
        return profile

    def delete(self, professional_id: str, client_code: str) -> None:
        """Portfolio only (demo reset); the case base is untouchable from here. Removes the client's saved diets and records first."""
        with self._sf() as s:
            for table in ("saved_diets", "lab_results", "body_measurements", "client_records"):
                exists = s.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"), {"t": table}).first()
                if exists:
                    s.execute(text(f"DELETE FROM {table} WHERE professional_id = :p AND client_code = :c"), {"p": professional_id, "c": client_code})
            s.execute(text("DELETE FROM client_profiles WHERE professional_id = :p AND client_code = :c AND NOT is_corpus_case"), {"p": professional_id, "c": client_code})
            s.commit()

    # ------------------------------------------------------------------------------------------------------- case base
    def liked_food_ids_by_client(self, professional_id: str) -> dict[str, tuple[int, ...]]:
        """Los gustos positivos resueltos, por codigo de cliente, en una sentencia.

        Lo usan los arneses para poblar el lado del CASO: `CANDIDATE_SQL` no los trae, y sin ellos el rasgo `likes` no
        seria evaluable en ningun par y el barrido diria «no aporta» por un motivo que no es el que se mide.
        """
        with self._sf() as s:
            rows = s.execute(text("SELECT client_code, liked_food_ids FROM client_profiles WHERE professional_id = :p"),
                             {"p": professional_id}).all()
        return {r.client_code: tuple(r.liked_food_ids or ()) for r in rows}

    def list_case_profiles(self, professional_id: str) -> tuple[ClientProfile, ...]:
        """The pseudonymous profiles of the corpus (retrieval strategies, leave-one-out harness). Never served by a client endpoint."""
        with self._sf() as s:
            rows = s.execute(select(ClientProfileEntity).where(ClientProfileEntity.professional_id == professional_id,
                                                               ClientProfileEntity.is_corpus_case.is_(True))).scalars()
            return tuple(to_domain(e) for e in rows)
