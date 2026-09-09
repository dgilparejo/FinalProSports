"""NoteCatalogueOutputPort backed by the file produced by pipeline/build_canonical_notes.py
($FPS_DATASET_DIR/canonical_notes.json). Themes and canonical wordings only: no client text, no identifiers."""
from __future__ import annotations

import json
from pathlib import Path

from finalprosports.domain.composition.policy.note_catalogue import NoteCatalogue
from finalprosports.infrastructure.config.paths import dataset_dir


class FileNoteCatalogueAdapter:
    def __init__(self, path: Path | None = None):
        self._path = path
        self._cache: NoteCatalogue | None = None
        self._loaded = False

    def load(self, professional_id: str) -> NoteCatalogue | None:
        if not self._loaded:
            path = self._path or dataset_dir() / "canonical_notes.json"
            self._cache = NoteCatalogue.from_dict(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None
            self._loaded = True
        return self._cache
