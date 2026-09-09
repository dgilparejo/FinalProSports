"""FoodMatcher (S3): resolves the free text of the intake sheet («gustos negativos: pescado azul, coliflor; suplementos: creatina, whey»)
to catalogue foods, using the same normalised keys and synonyms the ETL used to map the corpus. Deterministic, no I/O; unmatched
fragments are returned so the professional sees what the engine could not use."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from finalprosports.domain.model import Food

_SPLIT = re.compile(r"[,;/\n]|\by\b|\bni\b|\be\b", re.I)
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return _WS.sub(" ", t).strip()


@dataclass(frozen=True)
class MatchResult:
    food_ids: tuple[int, ...]
    matched: tuple[tuple[str, int, str], ...]      # (fragment, food_id, canonical_name)
    unmatched: tuple[str, ...]


class FoodMatcher:
    def __init__(self, catalog: dict[int, Food]):
        self._index: dict[str, int] = {}
        for f in sorted(catalog.values(), key=lambda x: -x.frequency):           # frequent foods win ties on a shared synonym
            for name in (f.canonical_name, *f.synonyms):
                self._index.setdefault(normalise(name), f.id)
        self._catalog = catalog

    def add(self, food: Food) -> None:
        """S5: a food registered by the professional becomes matchable at once."""
        self._catalog[food.id] = food
        for name in (food.canonical_name, *food.synonyms):
            self._index.setdefault(normalise(name), food.id)

    def match(self, text: str | None) -> MatchResult:
        if not text or not text.strip():
            return MatchResult((), (), ())
        ids: list[int] = []
        matched, unmatched = [], []
        for raw in (p.strip() for p in _SPLIT.split(text) if p and p.strip()):
            key = normalise(raw)
            if not key:
                continue
            fid = self._index.get(key) or self._index.get(key.rstrip("s")) or next((v for k, v in self._index.items() if len(k) > 3 and (k in key or key in k)), None)
            if fid is None:
                unmatched.append(raw)
            elif fid not in ids:
                ids.append(fid); matched.append((raw, fid, self._catalog[fid].canonical_name))
        return MatchResult(tuple(ids), tuple(matched), tuple(unmatched))
