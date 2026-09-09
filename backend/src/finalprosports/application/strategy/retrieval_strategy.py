"""Retrieval strategies (E3.2). All four are implemented behind CaseRepositoryOutputPort and selected by configuration
(Settings.retrieval_strategy); the default is the one that won the leave-one-out benchmark on food overlap (Jaccard)."""
from enum import StrEnum


class RetrievalStrategy(StrEnum):
    VECTOR = "vector"                                # cosine over e5 embeddings of the retrieval text, no prefilter
    GOAL_FILTERED_VECTOR = "goal_filtered_vector"    # prefilter by the professional's goal, cosine order inside
    ATTRIBUTES = "attributes"                        # weighted attribute match only (goal, sex, age, activity, restrictions), no vectors
    HYBRID = "hybrid"                                # prefilter by goal (+ sex), alpha * normalised cosine + (1 - alpha) * attributes
