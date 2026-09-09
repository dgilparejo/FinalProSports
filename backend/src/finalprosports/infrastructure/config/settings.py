"""Runtime settings (environment). pydantic-settings is a config concern, allowed here only."""
from pydantic_settings import BaseSettings

from finalprosports.infrastructure.config.paths import repo_root


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://finalprosports:finalprosports@localhost:5432/finalprosports"
    professional_id: str = "prof_001"
    professional_brand: str = "Final Pro Sports"        # S6: brand block of the PDF (logo in adapter/outbound/export/assets)
    professional_contact: str = ""                      # S6: footer lines of the PDF separated by '|' (e-mail | phone); empty by default, set in .env
    professional_secondary_logo: str = ""               # S6: optional second logo (top-right of his document), path outside the repository; empty = none
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_model_revision: str = "d128750597153bb5987e10b1c3493a34e5a4502a"      # Hugging Face commit; pinned so the vectors are reproducible
    embedding_dimension: int = 768
    retrieval_k: int = 5
    retrieval_strategy: str = "attributes"              # vector | goal_filtered_vector | attributes | hybrid - attributes won the E3.2 LOO benchmark (la memoria (evaluación de la recuperación))
    hybrid_alpha: float = 0.5                           # weight of the normalised cosine in the hybrid strategy
    composer_k: int = 20                                # cases used by the composer: k_effective = min(k, cases retrieved) (E4.2 grid, la memoria (evaluación del compositor))
    composer_inclusion_threshold: float = 0.35          # share of cases containing a food for it to be proposed: size ratio 0.98 vs the real diet (E4.2 grid)
    enable_low_confidence_rules: bool = False           # the 12 low-confidence rules: implemented, disabled by default (measured separately)
    enforce_rules: bool = True                          # validator removes foods violating enforceable prohibitions (sugar, carbs at dinner for keto/fasting, fruit at dinner, soy)
    restriction_mode: str = "restriccion_estricta"      # restriccion_estricta | reproducir_criterio_profesional (lactose, rule section 8)
    recurrent_strategy: str = "rotation"                # rotation | case_based — strategy for clients with previous versions (2.3/2.4)
    rotation_use_repertoire: bool = True                # True = full rotation at the professional's renewal rate (family-level fidelity identical to copying, human-level novelty); False = conservative (consensus replacements only, ~5 % renewal)
    route_goal_change_to_archetype: bool = True         # recurrent client whose goal changed -> compose from the archetype (the previous diet stops being a reference); same goal -> rotate the previous version
    plausibility_completion: bool = True                # S2: after the strategy, complete the required slot structure / top up thin slots from the cases and clamp quantities into the corpus envelope (proposal_completion_policy); the LOO harness measures the raw strategies
    # v2 — Keycloak. There is NO switch to turn authentication off: the application does not start
    # a mode without it (la memoria (capítulo de seguridad)). `keycloak_internal_issuer` only changes WHERE the JWKS is
    # fetched from (container-to-container); the `iss` that must appear in the token is `keycloak_issuer`.
    keycloak_issuer: str = "http://localhost:8080/realms/fps"
    keycloak_internal_issuer: str = ""
    keycloak_audience: str = "fps-backend"
    keycloak_required_role: str = "entrenador"
    keycloak_jwks_cache_seconds: float = 300.0
    keycloak_leeway_seconds: float = 10.0
    similarity_threshold: float = 0.80                  # secondary gap signal (LOO top-1 attribute score: p05 0.93, min 0.79); primary conditions in domain gap_policy

    model_config = {"env_prefix": "", "env_file": (str(repo_root() / ".env"), ".env"), "extra": "ignore"}   # .env at the repository root (TFM/code), then cwd
