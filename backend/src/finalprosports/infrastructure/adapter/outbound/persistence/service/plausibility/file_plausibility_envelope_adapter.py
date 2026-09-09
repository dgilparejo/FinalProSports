"""PlausibilityEnvelopeOutputPort backed by the file produced by pipeline/plausibility_envelope.py ($FPS_DATASET_DIR/plausibility_envelope.json).
Aggregates over pseudonymous ids and canonical food names; when the file is absent the layer is simply off (None)."""
from __future__ import annotations

import json
from pathlib import Path

from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope
from finalprosports.infrastructure.config.paths import dataset_dir, repo_root


class FilePlausibilityEnvelopeAdapter:
    def __init__(self, path: Path | None = None):
        self._path = path
        self._cache: PlausibilityEnvelope | None = None
        self._loaded = False

    def load(self, professional_id: str) -> PlausibilityEnvelope | None:
        if not self._loaded:
            path = self._path or dataset_dir() / "plausibility_envelope.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                # The curated portion lists are human criterion and live with the rest of it, in the pipeline's data folder,
                # not in the mined envelope; they are merged here so the domain sees one object (§2 and §6 of the expert review).
                curated = repo_root() / "pipeline" / "src" / "pipeline" / "data"
                units = curated / "portion_units.json"
                if units.exists():
                    data["portion_units"] = json.loads(units.read_text(encoding="utf-8"))
                variants = curated / "food_variants.json"
                if variants.exists():
                    data["food_variants"] = json.loads(variants.read_text(encoding="utf-8")).get("variants", {})
                self._cache = PlausibilityEnvelope.from_dict(data)
            else:
                self._cache = None
            self._loaded = True
        return self._cache
