from dataclasses import dataclass
from enum import StrEnum


class RuleConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RuleScope(StrEnum):
    GLOBAL = "global"
    GOAL = "goal"
    SEX = "sex"
    PHASE = "phase"
    PLACEMENT = "placement"
    AVOID_PLACEMENT = "avoid_placement"
    BEHAVIOUR = "behaviour"
    POLICY = "policy"


class RuleStatus(StrEnum):
    KEPT = "kept"
    RETIRED = "retired"
    DESCRIPTIVE = "descriptive"
    POLICY = "policy"


class RuleNature(StrEnum):
    """Prescriptive: may be demanded of every proposal of its group (kept or policy AND followed in the majority of the group).
    Descriptive: reported and explained as evidence, never required — a kept rule present in 27 % of its group discriminates the goal
    but cannot be imposed on 100 % of the proposals (finding of Fase 9, B). Decided by the constitution builder, stored with the rule."""

    PRESCRIPTIVE = "prescriptive"
    DESCRIPTIVE = "descriptive"


MAJORITY_PREVALENCE = 0.5     # the majority cut shared with pipeline/src/data_tools/build_validated_rules.py (fallback when nature is not stored)


@dataclass(frozen=True)
class Rule:
    """A validated rule of the professional's constitution with its empirical support."""

    id: str
    statement: str
    scope: RuleScope
    status: RuleStatus
    evaluation_level: str                 # 'item' | 'note'
    condition: tuple[str, ...] = ()       # goals / sexes / phases the rule applies to (empty = always)
    confidence: RuleConfidence | None = None
    n_support: int | None = None
    prevalence: float | None = None       # prevalence of the pattern inside the rule's group (explainability)
    lift: float | None = None
    adjusted: float | None = None
    enabled: bool = True
    nature: RuleNature | None = None      # None = constitution loaded before 0009: fall back to the prevalence cut

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence is RuleConfidence.LOW

    @property
    def is_prescriptive(self) -> bool:
        if self.nature is not None:
            return self.nature is RuleNature.PRESCRIPTIVE
        # Strictly greater: a majority is more than half. Mirrors data_tools.build_validated_rules.nature_of,
        # where the boundary case (exactly 0.50) was demanding perfect compliance with a coin flip.
        return self.status in (RuleStatus.KEPT, RuleStatus.POLICY) and (self.prevalence or 0.0) > MAJORITY_PREVALENCE
