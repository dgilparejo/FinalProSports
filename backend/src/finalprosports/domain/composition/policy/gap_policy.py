"""Gap (unmet demand) assessment of a retrieval (E3.4).

The attribute score measures MATCH, not AVAILABILITY: a profile can match perfectly on goal, sex and age and still have no
truly comparable case because its restrictions rule every candidate out. So a gap is defined by four conditions, in order
of importance, evaluated on the candidate counts the repository reports for the query (after the mandatory exclusions):

  1. candidate_scarcity        after the hard filters (goal + declared restrictions) fewer than k candidates remain
  2. poor_archetype            the profile's archetype (sex x age bucket x goal) has fewer than MIN_ARCHETYPE_DIETS diets available
  3. restriction_incompatible  no candidate is free of the foods vetoed by the client's structured restrictions
  4. low_score                 the best candidate scores below the similarity threshold (secondary signal)

Pure function; the service logs the gap with the FIRST triggered condition as `kind` and the whole assessment as payload.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MIN_ARCHETYPE_DIETS = 2


@dataclass(frozen=True)
class CandidateCounts:
    """What is available for a query after the mandatory exclusions."""

    total: int                         # every candidate diet
    same_goal: int                     # hard filter: goal
    same_goal_restriction_free: int    # hard filters: goal + no vetoed food (== same_goal when no structured restriction is declared)
    archetype: int                     # sex x age bucket x goal
    restriction_free: int              # any goal, no vetoed food (== total when no structured restriction is declared)
    restrictions_declared: int         # number of structured restrictions the query carried


@dataclass(frozen=True)
class GapAssessment:
    candidate_scarcity: bool
    poor_archetype: bool
    restriction_incompatible: bool
    low_score: bool
    counts: CandidateCounts
    k: int
    best_score: float | None
    threshold: float
    triggered: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_gap(self) -> bool:
        return bool(self.triggered)

    @property
    def kind(self) -> str | None:
        return self.triggered[0] if self.triggered else None


def assess_gap(counts: CandidateCounts, k: int, best_score: float | None, threshold: float) -> GapAssessment:
    scarcity = counts.same_goal_restriction_free < k
    poor = counts.archetype < MIN_ARCHETYPE_DIETS
    incompatible = counts.restrictions_declared > 0 and counts.restriction_free == 0
    low = best_score is None or best_score < threshold
    triggered = tuple(name for flag, name in ((scarcity, "candidate_scarcity"), (poor, "poor_archetype"),
                                               (incompatible, "restriction_incompatible"), (low, "low_score")) if flag)
    return GapAssessment(scarcity, poor, incompatible, low, counts, k, best_score, threshold, triggered)
