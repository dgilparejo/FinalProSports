"""SubstitutionPolicy: when may a food replace another in the rotation, and when does that count as renewal.

Rotating is not «swap a food for another of the same family». The functional test found four families of bad substitution in one
proposal, and each needs its own criterion:

  plátano -> fruta, atún -> pescado azul     a concrete food replaced by the GENERIC placeholder of its own family. The diet gets
                                             poorer, not renewed. A placeholder is recognisable from the catalogue itself: its
                                             canonical name IS its family name (arroz, pescado blanco, pescado azul, fruta,
                                             aminoácidos, huevo, marisco, embutido). A generic may be replaced by a concrete food,
                                             never the other way round.
  patata -> puré de patata                   same food, other preparation. For a client tired of eating potato this renews
                                             nothing. Detected by the nominal head: one canonical name's content words are a
                                             subset of the other's.
  ensalada -> cebolla                        same group and same family (both VEGETABLE / verdura), but not the same ROLE: he
                                             writes 150 g of salad and 20 g of onion. The corpus says it: the median quantity of
                                             the substitute in the same unit must be within a factor of the original's.
  pan integral -> sándwich                   «sándwich» is a PREPARATION (its keys are «sandwich pavo», «sandwich atún»: bread plus
                                             a filling), not an ingredient. It is kept in the catalogue because 149 components say
                                             it, but it must not be offered as a substitute.

The macrogroup (FoodGroup) is checked too, although in the current catalogue every family lies inside one group, so it is a guard
against future catalogue changes rather than a filter that fires today — the five bad substitutions above all shared group AND
family, which is why family alone was not enough.
"""
from __future__ import annotations

import re
import unicodedata

from finalprosports.domain.model import Food

# Preparations kept in the catalogue because the corpus writes them, never offered as a rotation substitute.
PREPARATIONS: frozenset[str] = frozenset({"sándwich", "sandwich"})
SCALE_TOLERANCE = 3.0
"""How far apart two foods' typical quantities may be and still count as the same role in the meal.

Measured, not chosen. The professional's own alternative groups are pairs he himself declares interchangeable, so the ratio
of their corpus medians inside a shared unit IS the tolerance he works with: over 4.971 usable groups the ratio is 1,10x at
the median, 2,00x at p90 and 3,00x at p95, and 4,45 % of his groups exceed 3x. The value was originally a guess; the
measurement puts it at percentile 95,55 of his own practice, which is the same p95 criterion the plausibility envelope uses
everywhere else, so it stands as measured rather than as assumed. Full distribution in
`FPS_DATASET_DIR/rotation_scale_tolerance.json` (pipeline: 5 of the diagnostic batch).
Counter-example it excludes: ensalada 150 g vs cebolla 20 g = 7,5x."""
STOPWORDS = frozenset({"de", "del", "la", "el", "los", "las", "al", "con", "sin", "en", "y", "o", "a", "para"})


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def content_words(name: str) -> frozenset[str]:
    return frozenset(t for t in re.split(r"[\s/(),.-]+", _norm(name)) if t and t not in STOPWORDS)


def _singular(s: str) -> str:
    """Enough Spanish plural to compare a canonical name with a family name: «grasas» is the family «grasa»."""
    return s[:-2] if s.endswith("es") and len(s) > 4 else (s[:-1] if s.endswith("s") and len(s) > 3 else s)


def is_generic(food: Food) -> bool:
    """A placeholder for its own family: its canonical name is the family name (the catalogue says so, nobody declared it).

    Compared in the singular, because the catalogue names families in the singular and foods sometimes in the plural: «grasas»
    against the family «grasa» slipped through an exact comparison and the rotation printed «0,5 Grasas» where the client had
    «1 cucharada de Aceite de coco» — the generic replacing the specific, which is the opposite of renewing."""
    if not food.family:
        return False
    a = _singular(_norm(food.canonical_name).replace(" ", "_"))
    b = _singular(_norm(food.family))
    return a == b


def is_preparation(food: Food) -> bool:
    return _norm(food.canonical_name) in {_norm(p) for p in PREPARATIONS}


def shares_nominal_head(a: Food, b: Food) -> bool:
    """Same noun: «patata» / «puré de patata», «arroz» / «arroz integral». Not «aceite de oliva» / «aceite de coco»."""
    wa, wb = content_words(a.canonical_name), content_words(b.canonical_name)
    return bool(wa) and bool(wb) and (wa <= wb or wb <= wa)


def comparable_scale(original: Food, candidate: Food, medians: dict[tuple[int, str], float] | None) -> bool:
    """Same role in the meal, measured: the medians of both foods in a shared unit differ by at most SCALE_TOLERANCE.
    With no shared unit in the envelope the check cannot fire and the substitution is allowed (declared)."""
    if not medians:
        return True
    units_a = {u: v for (fid, u), v in medians.items() if fid == original.id and v}
    units_b = {u: v for (fid, u), v in medians.items() if fid == candidate.id and v}
    shared = set(units_a) & set(units_b)
    if not shared:
        return True
    for u in shared:
        ratio = max(units_a[u], units_b[u]) / min(units_a[u], units_b[u])
        if ratio <= SCALE_TOLERANCE:
            return True
    return False


def may_substitute(original: Food, candidate: Food, medians: dict[tuple[int, str], float] | None = None,
                   interchangeable=None) -> tuple[bool, str | None]:
    """(allowed, reason when refused). The reason is recorded so a refusal can be explained.

    `interchangeable` is a predicate `(food_id, food_id) -> bool` over the pairs the professional himself writes as
    alternatives. It is the criterion that the catalogue's families cannot supply: `condimento` holds garlic, turmeric,
    parsley, salt and sweetener in one family, and the family rule alone let the rotation offer «Edulcorante» where he had
    written «Ajo». When it is not supplied the family rule stands alone."""
    if candidate.id == original.id:
        return False, "mismo alimento"
    if is_preparation(candidate):
        return False, f"«{candidate.canonical_name}» es una preparación, no un ingrediente"
    if candidate.group is not original.group:
        return False, f"distinto papel en la comida ({candidate.group.value} frente a {original.group.value})"
    if candidate.family != original.family:
        return False, f"distinta familia ({candidate.family} frente a {original.family})"
    if is_generic(candidate) and not is_generic(original):
        return False, f"«{candidate.canonical_name}» es el genérico de la familia: empobrece en lugar de renovar"
    if shares_nominal_head(original, candidate):
        return False, f"misma cabeza nominal que «{original.canonical_name}»: otra preparación del mismo alimento, no una renovación"
    if not comparable_scale(original, candidate, medians):
        return False, "escala de uso distinta: no cumple el mismo papel en la franja"
    if interchangeable is not None and not interchangeable(original.id, candidate.id):
        return False, f"él nunca ha escrito «{candidate.canonical_name}» como alternativa de «{original.canonical_name}»"
    return True, None


def counts_as_renewal(original: Food, candidate: Food) -> bool:
    """A replacement that does not renew must not consume the renewal budget (nor be reported as renewal)."""
    return not shares_nominal_head(original, candidate) and not (is_generic(candidate) and not is_generic(original))
