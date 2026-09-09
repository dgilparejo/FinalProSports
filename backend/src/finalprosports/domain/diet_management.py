"""Aggregate root: a professional's diet practice (profiles, cases, catalogue and constitution) — the consistency boundary
of the domain. Everything the composition policies need is reachable from here without touching infrastructure."""
from dataclasses import dataclass, field

from .model import ClientProfile, Diet, Food, Rule


@dataclass(frozen=True)
class DietManagement:
    professional_id: str
    catalog: tuple[Food, ...]
    rules: tuple[Rule, ...]
    profiles: tuple[ClientProfile, ...] = field(default_factory=tuple)

    def food(self, food_id: int) -> Food | None:
        return next((f for f in self.catalog if f.id == food_id), None)

    def enabled_rules(self) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules if r.enabled)

    def history_of(self, client_code: str, diets: tuple[Diet, ...]) -> tuple[Diet, ...]:
        return tuple(d for d in diets if d.client_code == client_code and d.professional_id == self.professional_id)
