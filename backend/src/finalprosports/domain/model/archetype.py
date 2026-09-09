from dataclasses import dataclass

from .goal import Goal


@dataclass(frozen=True)
class Archetype:
    sex: str | None
    age_bucket: str
    goal: Goal
    diet_count: int
    client_count: int
