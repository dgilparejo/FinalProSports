from dataclasses import dataclass

from .client_profile import ClientProfile
from .diet import Diet


@dataclass(frozen=True)
class CaseQuery:
    """What a retrieval strategy receives: the query profile (goal is the professional's structured input) and, when the
    strategy needs it, the embedding of the query text (None for the attribute-only strategy)."""

    profile: ClientProfile
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class SimilarityScore:
    vector: float                         # cosine similarity of the retrieval texts (0.0 when the strategy uses no vector)
    attributes: float                     # attribute match in [0, 1] (0.0 when the strategy uses no attributes)
    total: float                          # what the strategy ranked by


@dataclass(frozen=True)
class RetrievedCase:
    diet: Diet
    score: SimilarityScore
    rank: int
    case_profile: ClientProfile | None = None     # the case's client attributes with the DIET's goal (for archetype checks, weighting)
