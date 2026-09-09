from dataclasses import dataclass, field

from .client_profile import ClientProfile
from .diet_item import DietItem
from .meal_slot import MealSlot


@dataclass(frozen=True)
class RuleSupport:
    """A rule of the constitution that backs a proposed food (explainability panel)."""

    rule_id: str
    prevalence: float | None            # prevalence of the pattern in the rule's group
    lift: float | None


@dataclass(frozen=True)
class ItemEvidence:
    """Why an item is proposed: the retrieved cases that contain it in this slot, their share, and the rules that back it."""

    case_ids: tuple[str, ...]
    support: float                      # fraction of the k retrieved cases containing the food in this slot
    rules: tuple[RuleSupport, ...] = ()


@dataclass(frozen=True)
class ProposedItem:
    item: DietItem
    evidence: ItemEvidence


@dataclass(frozen=True)
class AlternativeGroup:
    """One position of a meal as the professional writes it: «150 gr Pollo / 160 gr Pavo / 180 gr Lomo»."""

    position: int
    options: tuple[ProposedItem, ...]

    @property
    def leader(self) -> ProposedItem:
        return self.options[0]


@dataclass(frozen=True)
class ProposedMeal:
    slot: MealSlot
    groups: tuple[AlternativeGroup, ...]

    @property
    def items(self) -> tuple[ProposedItem, ...]:
        return tuple(o for g in self.groups for o in g.options)


@dataclass(frozen=True)
class RuleCheck:
    rule_id: str
    applicable: bool
    satisfied: bool | None
    enforced: bool = False              # the validator had to change the proposal to satisfy it


@dataclass(frozen=True)
class ForcedChange:
    """What the validator changed and why (restrictions have maximum priority, then enforced rules)."""

    slot: MealSlot
    food_id: int | None
    canonical_name: str | None
    action: str                         # 'removed'
    reason: str                         # 'restriction:contains_lactose' | 'rule:sin_hidratos_cena'


@dataclass(frozen=True)
class ValidationReport:
    rule_checks: tuple[RuleCheck, ...]
    forced_changes: tuple[ForcedChange, ...]
    warnings: tuple[str, ...] = ()      # non-strict restrictions reproduced from the professional's behaviour

    @property
    def compliance(self) -> float | None:
        applicable = [c for c in self.rule_checks if c.applicable and c.satisfied is not None]
        return (sum(1 for c in applicable if c.satisfied) / len(applicable)) if applicable else None


@dataclass(frozen=True)
class DietProposal:
    profile: ClientProfile
    meals: tuple[ProposedMeal, ...]
    notes: tuple[str, ...]
    retrieved_case_ids: tuple[str, ...]
    strategy: str                       # 'case_based_composer' | 'llm_fallback' (v2)
    parameters: dict = field(default_factory=dict)          # k, inclusion threshold ... (reproducibility)
    validation: ValidationReport | None = None

    @property
    def rule_checks(self) -> tuple[RuleCheck, ...]:
        return self.validation.rule_checks if self.validation else ()

    @property
    def compliance(self) -> float | None:
        return self.validation.compliance if self.validation else None

    @property
    def food_ids(self) -> frozenset[int]:
        return frozenset(o.item.food_id for m in self.meals for o in m.items if o.item.food_id is not None)
