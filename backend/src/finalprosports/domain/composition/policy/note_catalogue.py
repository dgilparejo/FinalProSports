"""The catalogue of canonical notes: what the professional instructs, recognised by theme instead of by literal string.

Why it exists. He writes the same instruction in many wordings — the hydration line lives in 638 of the 1.033 corpus diets
across 396 distinct wordings, the largest covering 33. Consensus over exact strings therefore could never see it: NOT ONE
note string in the corpus reaches the composition threshold `note_t = 0,35` (0 of 1.171), so the threshold branch never fired
and every note the composer emitted came from the `min_notes` top-up — one neighbour's own sentence, copied verbatim into a
stranger's diet. Measured effect on the constitution: the rule `agua_2.5L` scored 0,088 against his 0,790.

A theme groups the wordings of one instruction under a regular expression and gives it ONE canonical text, the most frequent
wording of that theme in the corpus. Consensus then runs over themes, so 396 ways of saying "drink water" count 396 times for
one theme instead of once each. What the catalogue does NOT cover keeps working exactly as before, by literal consensus.

`artefact` is a separate matter: 14,9 % of the `notes` field is not notes at all but section headers the document parser kept
(«Observaciones:», «Recomendaciones:», «Consejos:») and fragments of the contact footer («tel», «/ tel»). They were reaching
proposals — one of them reached a golden snapshot. They are excluded from the corpus side and never emitted.

Built by `pipeline/src/pipeline/build_canonical_notes.py` from the versioned criterion `pipeline/data/note_themes.json`.
Pure domain: regular expressions and text, no I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NoteTheme:
    id: str
    canonical: str                       # the wording emitted, his own most frequent one for this theme
    pattern: re.Pattern
    support_share: float                 # share of the corpus diets carrying the theme (explainability, not used to decide)
    rule_ids: tuple[str, ...] = ()       # rules of the constitution this theme makes evaluable


@dataclass(frozen=True)
class NoteCatalogue:
    themes: tuple[NoteTheme, ...] = ()
    artefact: re.Pattern | None = None
    _by_id: dict[str, NoteTheme] = field(default_factory=dict, compare=False)

    @classmethod
    def from_dict(cls, d: dict) -> "NoteCatalogue":
        themes = tuple(NoteTheme(t["id"], t["canonical"], re.compile(t["pattern"], re.I),
                                 float(t.get("support_share") or 0.0), tuple(t.get("rule_ids") or ()))
                       for t in d.get("themes", ()))
        art = d.get("artefact_pattern")
        return cls(themes, re.compile(art, re.I) if art else None, {t.id: t for t in themes})

    def is_artefact(self, text: str) -> bool:
        """A section header or a footer fragment: not an instruction, never emitted, never counted as support."""
        return bool(self.artefact and self.artefact.search(text or ""))

    def themes_in(self, text: str) -> frozenset[str]:
        """Which instructions this note carries. A note may legitimately carry two («no tomar postres, ni azúcar, ni
        bebidas alcohólicas» is sugar AND alcohol) and then both are supported by it."""
        t = text or ""
        return frozenset(th.id for th in self.themes if th.pattern.search(t))

    def canonical_of(self, theme_id: str) -> str | None:
        return self._by_id[theme_id].canonical if theme_id in self._by_id else None

    def __bool__(self) -> bool:
        return bool(self.themes)
