"""RotationStatsOutputPort backed by the file produced by pipeline/rotation_analysis.py (_dataset/rotation_analysis.json).
The statistics are aggregates over pseudonymous ids (no health text); they are re-derived from the corpus, not stored in the database."""
from __future__ import annotations

import json
from pathlib import Path

from finalprosports.domain.model import RotationStats
from finalprosports.infrastructure.config.paths import dataset_dir


class FileRotationStatsAdapter:
    def __init__(self, path: Path | None = None):
        self._path = path or dataset_dir() / "rotation_analysis.json"     # FPS_DATASET_DIR
        self._cache: RotationStats | None = None

    def load(self, professional_id: str) -> RotationStats:
        if self._cache is None:
            self._cache = parse(json.loads(self._path.read_text(encoding="utf-8")))
        return self._cache


def parse(data: dict) -> RotationStats:
    foods = data["foods"]
    food_n = {int(f["food_id"]): int(f["n"]) for f in foods}
    food_kept = {int(f["food_id"]): round(f["persistence"] * f["n"]) for f in foods}
    prevalence = {int(k): float(v) for k, v in data.get("food_prevalence_same_goal", {}).items()}
    fam = {f["family"]: float(f["persistence"]) for f in data["families"]}
    s = data["summary"]
    per_client = {c: {int(f): (int(v[0]), int(v[1])) for f, v in d.items()} for c, d in data.get("per_client", {}).items()}
    inter = frozenset((int(a), int(b)) for a, b in
                      ((data.get("alternative_groups") or {}).get("interchangeable_foods") or {}).get("pairs", []))
    return RotationStats(food_n, food_kept, prevalence, fam, float(s["renewal_dropped_same_goal"]["mean"]),
                         float(s["renewal_dropped_goal_change"]["mean"] or s["renewal_dropped"]["mean"]), per_client, inter)
