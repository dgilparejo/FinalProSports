"""Rotation statistics of the professional (measured in pipeline/rotation_analysis.py): how often a food that appears in a
version survives into the next version of the same client, against how often it would appear anyway (prevalence in the goal).

The object is immutable and can be re-derived WITHOUT one client's contribution (`without_client`), which is what the
leave-one-out harness needs to avoid learning the rotation of the very client it evaluates."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RotationStats:
    food_n: dict[int, int]                           # food -> pairs where the food was in v_n
    food_kept: dict[int, int]                        # food -> pairs where it also was in v_{n+1}
    food_prevalence: dict[int, float]                # food -> mean prevalence among diets of the same goal (chance persistence)
    family_persistence: dict[str, float]             # family -> P(family in v_{n+1} | family in v_n)
    renewal_same_goal: float                         # share of foods dropped between consecutive versions with the same goal
    renewal_goal_change: float                       # ... when the goal changes
    per_client: dict[str, dict[int, tuple[int, int]]] = field(default_factory=dict)   # client -> food -> (n, kept)
    interchangeable: frozenset[tuple[int, int]] = frozenset()   # ordered (min, max) food pairs he WROTE as alternatives of each other

    def are_interchangeable(self, a: int, b: int) -> bool:
        """Whether he himself has offered these two foods as alternatives of each other.

        The catalogue's families cannot carry this decision: `condimento` is a residual family holding garlic, turmeric,
        parsley, salt and sweetener, so a family-only rule let the rotation offer sweetener in place of garlic. His own
        practice is the better criterion and it is richer as well as stricter — of the 1.701 pairs he writes as
        alternatives only 24 % share a family (ave/pescado_blanco, arroz/pasta), while he uses just 38 % of the
        same-family pairs the catalogue would allow. When the set is empty the check is off and the family rule stands
        alone, so an installation without the rotation analysis still works."""
        return not self.interchangeable or (min(a, b), max(a, b)) in self.interchangeable

    def persistence(self, food_id: int) -> float | None:
        n = self.food_n.get(food_id, 0)
        return self.food_kept.get(food_id, 0) / n if n else None

    def n(self, food_id: int) -> int:
        return self.food_n.get(food_id, 0)

    def lift(self, food_id: int) -> float | None:
        p, ch = self.persistence(food_id), self.food_prevalence.get(food_id)
        return (p / ch) if (p is not None and ch) else None

    def without_client(self, client_code: str) -> "RotationStats":
        contrib = self.per_client.get(client_code)
        if not contrib:
            return self
        n = dict(self.food_n); k = dict(self.food_kept)
        for f, (cn, ck) in contrib.items():
            n[f] = n.get(f, 0) - cn; k[f] = k.get(f, 0) - ck
            if n[f] <= 0:
                n.pop(f, None); k.pop(f, None)
        return RotationStats(n, k, self.food_prevalence, self.family_persistence, self.renewal_same_goal, self.renewal_goal_change,
                             {c: v for c, v in self.per_client.items() if c != client_code})
