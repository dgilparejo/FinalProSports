"""The pharmacological exclusion, applied to EVERY derived output and not only to the food catalogue.

The criterion (data owner) is that the assistant must be *structurally unable to propose* a
prescription drug or anabolic/hormonal product. Keeping them out of ``foods.json`` achieves that for composed
items, and only for those. An excluded substance can still reach the client through any other channel the
dataset feeds, and it did:

* ``diets.notes`` -> the database -> ``diet_factory`` -> the composer's note consensus -> ``build_proposal`` ->
  the **printed PDF**. Notes reading "2 PROVIRON/DÍA" and "1 proviron por la noche ... 3 oxandrolona" were on
  that path, in v2 as well as v3.
* ``diets.text`` and ``meals.text``, which are loaded into the database verbatim.

It is the same shape as the ContextVar problem: the protection sat in one place and the data left by another.

Two different treatments, because one rule does not fit both cases:

**Notes are dropped unless the mention is recognisable clinical prose.** "…PARA REGULAR LOS PICOS DE INSULINA…"
is a physiological explanation, and `insulina` is a key of an excluded entry; redacting the token would mangle a
legitimate note. But the first version of this rule kept a note unless a DOSE sat next to the substance, and that
is a blocklist over an open set of phrasings: "tomar proviron por la noche" carries no number and walks straight
through it. The rule is therefore inverted -- a note that names a substance is DROPPED unless every mention sits
in an allowlisted construction (``resistencia a la…``, ``picos de…``, ``producción de…``). Losing a legitimate
note costs a line of advice; keeping one prescription costs a printed PDF that hands a client an anabolic.

**Rendered texts are redacted, except the prose half.** ``diets.text`` and ``meals.text`` are renderings, so
replacing an ITEM's substance with a marker is honest and loses nothing recorded elsewhere. The ``OBJETIVO`` line
is not an item: it is prose about the client's physiology, and blanket redaction turned 37 of his stated goals
into "resistencia a la [SUSTANCIA EXCLUIDA]". Prose fields take the same allowlist as the notes.

**``raw_text`` is kept untouched.** It is the provenance the rebuild was asked to preserve, the item carries
``canonical_name = None`` and ``unmapped_reason = "excluded_substance"`` so it can never be proposed, and it is now
also flagged with ``contains_excluded_substance`` so any consumer can filter it without re-deriving the list.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

MARKER = "[SUSTANCIA EXCLUIDA]"


@lru_cache(maxsize=1)
def _entries() -> tuple[dict, ...]:
    here = Path(__file__).resolve().parents[1] / "pipeline" / "data" / "excluded_substances.json"
    data = json.loads(here.read_text(encoding="utf-8"))
    return tuple(data["substances"])


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern:
    keys: set[str] = set()
    for entry in _entries():
        keys.add(entry["name"].lower())
        keys.update(k.lower() for k in entry["keys"])
    # Longest first so "testo best" wins over "testo". Two-character keys are kept: "gh", "t3" and "t4" are real
    # entries of the curated list and dropping them for being short let 13 of them through into the meal text.
    # Word boundaries make them safe -- they only match as standalone tokens.
    ordered = sorted((k for k in keys if len(k) >= 2), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in ordered) + r")\b", re.I)


# A dose next to the substance: "2 PROVIRON", "1 proviron por la noche", "3 oxandrolona (1-1-1)", "PROVIRON/DÍA".
_DOSE_BEFORE = re.compile(r"(?:^|[^\w])(\d+[.,]?\d*)\s*(?:gr?s?|mg|ml|caps?|c[aá]psulas?|comp\.?|pastillas?|"
                          r"unidades?|ud\.?)?\s*$", re.I)
_DOSE_AFTER = re.compile(r"^\s*(?:/\s*d[ií]a|x\s*\d|\d|\(\s*\d)", re.I)

# The DESCRIPTIVE constructions: the substance named as a physiological fact, not handed to the client.
# "resistencia a la insulina", "picos de insulina", "producción y absorción de testosterona".
#
# This is an ALLOWLIST, and it is the whole point. A "does it look like a prescription?" test is a blocklist over
# an open set of phrasings, and it misses whatever it was not written for -- "tomar proviron por la noche" carries
# no number and slips straight through a dose rule. Defaulting to DROP and naming the few prose shapes that may
# stay is the same move that fixed the file-name masking: enumerate what is safe, not what is dangerous.
# Two families, and the split is the safety argument. NOUNS name a measurement or a physiological state
# ("picos de insulina"). VERBS describe modulating the body's OWN production ("potenciar la testosterona",
# "estimulación de la hormona crecimiento") -- deliberately NOT the administration verbs (tomar, añadir,
# inyectar, pinchar, meter), which are exactly what must keep triggering the discard.
_DESCRIPTIVE = re.compile(
    r"(?:resistencia|sensibilidad|picos?|niveles?|producci[oó]n|absorci[oó]n|s[ií]ntesis|regulaci[oó]n|"
    r"metabolismo|s[ií]ndrome|exceso|d[eé]ficit|control|anal[ií]tica|an[aá]lisis|"
    r"estimulaci[oó]n|segregaci[oó]n|secreci[oó]n|"
    r"regular|controlar|estimular|potenciar|mejorar|favorecer|optimizar|interferir|interfieran)"
    r"(?:\s+\w+){0,3}\s+(?:de\s+la\s+|de\s+|a\s+la\s+|al\s+|en\s+|con\s+la\s+|la\s+|el\s+|y\s+)?$",
    re.I,
)


# Handing the substance to the client. Vetoes the allowlist outright: no phrasing that administers a substance is
# clinical prose, however much physiological language surrounds it.
_ADMINISTERS = re.compile(
    r"\b(?:tomar|tomes?|toma|tomando|beber|bebe|ingerir|inyectar|inyecta|pinchar|pincha|meter|mete|"
    r"a[nñ]adir|a[nñ]ade|usar|usa|aplicar|aplica|suplementar|empezar\s+con|seguir\s+con|ponerse|p[oó]nte)\b",
    re.I,
)


def find(text: str) -> list[str]:
    """Every excluded-substance mention in the text, lower-cased. Empty when there is none."""
    return [m.group(0).lower() for m in _pattern().finditer(text or "")] if text else []


def contains(text: str) -> bool:
    return bool(find(text))


def prescribes(text: str) -> bool:
    """True when the text does not merely mention a substance but gives it with a dose.

    Reported separately from :func:`must_drop` because it is the *measurable* half: a dose is objective evidence
    of a prescription, so this is the count that goes in the report. It is not the discard rule -- on its own it
    is a blocklist, and "tomar proviron por la noche" defeats it.
    """
    if not text:
        return False
    for match in _pattern().finditer(text):
        before = text[max(0, match.start() - 24):match.start()]
        after = text[match.end():match.end() + 12]
        if _DOSE_BEFORE.search(before) or _DOSE_AFTER.match(after):
            return True
    return False


def is_descriptive(text: str) -> bool:
    """True when EVERY mention in the text sits in an allowlisted clinical construction.

    A single mention that does not is enough to fail: the text is then treated as a prescription, whatever the
    other mentions look like.

    The administration veto is checked FIRST and independently. Without it the descriptive verbs reopen the hole
    they were added to close: "controlar y tomar proviron" satisfies the allowlist through ``controlar`` because
    the pattern tolerates a few words between the term and the substance, and ``tomar`` is one of them.
    """
    matches = list(_pattern().finditer(text or ""))
    if not matches:
        return True
    for m in matches:
        window = text[max(0, m.start() - 48):m.start()]
        if _ADMINISTERS.search(window) or not _DESCRIPTIVE.search(window):
            return False
    return True


def must_drop(text: str) -> bool:
    """The discard rule for notes: mentions a substance and is not recognisably clinical prose.

    Deliberately stricter than :func:`prescribes`. Losing a legitimate note costs a line of advice; keeping a
    prescription costs a printed PDF that hands a client an anabolic.
    """
    return contains(text) and not is_descriptive(text)


def redact(text: str) -> str:
    """Replace every mention with the marker. For rendered text, never for ``raw_text``."""
    return _pattern().sub(MARKER, text) if text else text
