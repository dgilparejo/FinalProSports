"""F4.0 -- the goal taxonomy: what the professional actually declares, and how coarse the labels are.

The declared goal is the primary retrieval key and the stratum of nearly every figure in the evaluation, so before
anything is asked *about* goals they have to be enumerated. 449 distinct ``OBJETIVO`` strings become a small set of
labels, kept identical to v2 so the schema does not move.

Two things the enumeration shows and the v2 single ``goal`` field cannot express:

* the strings are frequently **compound** -- "Ganar masa muscular y tonificar" is two goals, and a diet that declares
  it is not mislabelled, it is coarsely labelled. ``goals`` keeps every label found; ``goal`` keeps the primary one.
  Separating this from real error matters, because otherwise a compound declaration looks like a mistake in F4.1.
* a diet with no ``OBJETIVO`` line at all gets ``goal_inferred = True`` and its label from the diet's own content,
  which is a weaker claim and is flagged as such.
"""
from __future__ import annotations

import re

# label -> ordered patterns over the NORMALISED (accent-folded, upper-case) goal string.
# Order matters only for choosing the primary label; every match is recorded in ``goals``.
# Built against the enumeration of every declared goal string, not from imagination. The first version was written
# from the verb forms alone and left 204 of 1.140 declared goals unmatched -- 18 % of the corpus reported as "no
# goal", which is what a review caught. The professional writes the NOUN at least as often as the verb ("pérdida de
# grasa", "quema de grasa", "tonificación", "ganancia muscular"), and he puts words between the verb and its object
# ("perder % grasa", "eliminar porcentaje de grasa"). Every pattern below maps to a label that already exists in
# the v2 taxonomy and in the domain's Goal enum; no category is invented here.
_GRASA = r"(?:MASA\s+)?GRASA|PESO|PORCENTAJE(?:\s+DE)?\s+GRASA|%\s*(?:DE\s+)?GRASA"
GOAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ayuno_intermitente", re.compile(r"\bAYUNO\b|\bAYUNOS\b|\bINTERMITENTE\b|\bAUTOFAGIA\b")),
    ("cetosis_keto", re.compile(r"\bCETO(SIS|GENIC)?\b|\bKETO\b|\bCETONIC")),
    ("descarga_carga", re.compile(r"\bDESCARGA\b|\bRECARGA\b|\bCARGA\s+DE\s+(HIDRATOS|CARBOHIDRATOS)\b|"
                                  r"\bCARGA(?:R)?\s+(?:DE\s+)?GLUCOGENO\b|\bGLUCOGENO\s+MUSCULAR\b")),
    ("volumen_masa", re.compile(
        r"\bVOLUMEN\b|\bHIPERTROFIA\b|\bCRECER\b|\bMASA\s+MUSCULAR\b|\bMASA\s+MAGRA\b|"
        r"\b(?:GANAR|AUMENTAR|SUBIR|MEJORAR|GANANDO)\s+(?:\w+\s+){0,2}"
        r"(?:MASA|MUSCULO|MUSCULATURA|MUSCULAR|PESO|MAGRA|CALIDAD\s+MUSCULAR|FIBRAS?)\b|"
        r"\b(?:GANANCIA|AUMENTO|SUBIDA)\s+(?:\w+\s+){0,2}(?:MUSCULAR|MUSCULO|MASA|FIBRAS?)\b|"
        r"\bFORTALECER\s+(?:\w+\s+){0,2}(?:MUSCULAR|MUSCULO|FIBRAS?)\b")),
    ("definicion_grasa", re.compile(
        r"\bDEFINIR\b|\bDEFINICION\b|\bADELGAZAR\b|\bABDOMINALES\b|\bMARCAR\b|"
        r"\bTONIFICAR\b|\bTONIFICACION\b|\bTONO\s+MUSCULAR\b|"
        r"\bPEGAR\s+(?:LA\s+)?PIEL\b|\bRECOGIMIENTO\s+DE\s+(?:LA\s+)?PIEL\b|\bAFINAR\s+(?:LA\s+)?PIEL\b|"
        r"\b(?:PERDER|BAJAR|ELIMINAR|QUEMAR|REDUCIR)\s+(?:\w+\s+){0,3}(?:" + _GRASA + r")\b|"
        r"\b(?:PERDIDA|QUEMA|REDUCCION|ELIMINACION|BAJADA)\s+(?:\w+\s+){0,3}(?:" + _GRASA + r")\b|"
        r"\bNO\s+ALMACENAR\s+GRASA\b|\bGRASA\s+VISCERAL\b")),
    ("hipocalorica", re.compile(r"\bHIPOCALORICA\b|\bBAJA\s+EN\s+CALORIAS\b|\bDEFICIT\s+CALORICO\b")),
    ("alta_en_fibra", re.compile(r"\bFIBRA\b|\bTRANSITO\b|\bESTRENIMIENTO\b")),
    ("mantenimiento", re.compile(r"\bMANTENIMIENTO\b|\bMANTENER\s+(EL\s+)?PESO\b|\bMANTENER\s+LA\s+LINEA\b|"
                                 r"\bNO\s+PERDER\s+LO\s+GANADO\b")),
]

# Purposes the professional writes that the v2 taxonomy has no label for: a depurative / detox diet and a
# performance diet are neither fat loss nor volume. They are NOT mapped onto the nearest existing label -- that
# would be inventing a goal for him -- and they are NOT new enum values either, because that is engine code.
# They are counted here so the gap is visible instead of hiding inside "sin_clasificar".
UNCOVERED_PURPOSES: list[tuple[str, re.Pattern]] = [
    ("depurativa_detox", re.compile(r"\bDEPURATIV|\bDEPURAR\b|\bDETOX\b|\bTOXINAS\b|\bDIURETICA\b|"
                                    r"\bRETENCION\s+(?:DE\s+)?(?:LIQUIDOS|AGUA)\b|\bALCALINIZ")),
    ("rendimiento", re.compile(r"\bCOMPETICION\b|\bRESISTENCIA\b|\bMARCAS?\s+DE\s+CARRERA\b|\bVO2\b|"
                               r"\bPRUEBAS\s+FISICAS\b|\bRENDIMIENTO\b|\bPOTENCIA\b")),
    ("salud_metabolica", re.compile(r"\bCOLESTEROL\b|\bTIROIDES\b|\bINSULINA\b|\bMICROBIOTA\b|\bINFLAMACION\b|"
                                    r"\bMETABOLISMO\b|\bHORMONAL\b|\bCOLAGENO\b|\bOSEA\b")),
]


def uncovered_purposes(goal_text: str, fold) -> list[str]:
    """Purposes present in the declared text that the taxonomy cannot express. Reported, never mapped."""
    if not goal_text:
        return []
    normalised = fold(goal_text)
    return [name for name, pattern in UNCOVERED_PURPOSES if pattern.search(normalised)]

# Two labels that routinely appear in the same sentence and mean one plan, not a contradiction.
COMPATIBLE_PAIRS = {
    frozenset({"ayuno_intermitente", "cetosis_keto"}),
    frozenset({"ayuno_intermitente", "definicion_grasa"}),
    frozenset({"cetosis_keto", "definicion_grasa"}),
    frozenset({"hipocalorica", "definicion_grasa"}),
    frozenset({"volumen_masa", "descarga_carga"}),
}

# Labels whose expected direction of change is unambiguous, for the scale-trajectory signal in F4.1.
# "mantenimiento" and a bare "tonificar" have no direction and are excluded there by name.
DIRECTIONAL = {
    "volumen_masa": {"weight": +1, "muscle": +1},
    "definicion_grasa": {"weight": -1, "fat": -1},
    "hipocalorica": {"weight": -1, "fat": -1},
    "cetosis_keto": {"weight": -1, "fat": -1},
    "ayuno_intermitente": {"weight": -1, "fat": -1},
}
NON_DIRECTIONAL = ("mantenimiento", "alta_en_fibra", "descarga_carga")

PRIMARY_ORDER = ["volumen_masa", "definicion_grasa", "cetosis_keto", "ayuno_intermitente",
                 "descarga_carga", "hipocalorica", "alta_en_fibra", "mantenimiento"]

# ------------------------------------------------------------------------------------ purpose vs method
# "Ayuno intermitente para perder grasa" declares TWO different things and both matter, so neither may evict the
# other. The PURPOSE is what the client wants (fat loss) and it is what makes two cases comparable: two clients
# fasting, one to lose fat and one to gain mass, are not each other's neighbour. The METHOD is how the diet is
# structured -- time-restricted eating, ketogenic macros, carbohydrate cycling -- and it is the most predictive
# signal there is about the SHAPE of the diet: which slots exist at all, whether carbohydrates appear at dinner.
#
# v2 read the method into ``goal`` and lost the purpose; v3 read the purpose and lost the method. Both threw away
# half of a compound declaration. ``method`` is therefore a FIELD OF ITS OWN, mined from the same ``goal_text``.
# No label is rewritten: ``goal`` and ``goals`` keep exactly the values they had.
#
# Only regimes that change the STRUCTURE of the plan are methods. ``hipocalorica`` is an energy target, not a
# structure, and stays a goal only; the rules that condition on it condition on the goal.
METHOD_ORDER = ["ayuno_intermitente", "cetosis_keto", "descarga_carga"]
NO_METHOD = None


def methods_for(goal_text: str, fold, extra_text: str = "") -> list[str]:
    """Every structural method the declared string supports, in taxonomy order.

    Reuses ``GOAL_PATTERNS`` deliberately: the same words name the method whether or not a purpose is also
    declared, and a second vocabulary for the same regimes would drift away from the first.
    """
    labels = set(labels_for(goal_text, fold))
    if extra_text:
        labels |= set(labels_for(extra_text, fold))
    return [m for m in METHOD_ORDER if m in labels]


def primary_method(methods: list[str]):
    """The method recorded in ``meta.method``; ``None`` when the diet declares no structural regime."""
    for m in METHOD_ORDER:
        if m in methods:
            return m
    return NO_METHOD

# A diet whose document declares no goal the taxonomy recognises. It is a NAMED absence, not a null and not a
# guess: v2's schema has a goal on every diet and downstream code sorts and groups on it, so a None crashes the
# plausibility envelope and would silently form a null stratum everywhere else.
#
# The value is the domain's own ``Goal.UNCLASSIFIED``. An invented label ("sin_objetivo") does not validate against
# that StrEnum, and widening the enum would mean editing the engine, which this rebuild does not do. The domain
# already had a name for "no goal", which is the right one to use.
NO_GOAL = "sin_clasificar"

_TONIFICAR = re.compile(r"\bTONIFICAR\b|\bTONIFICACION\b")


def labels_for(goal_text: str, fold) -> list[str]:
    """Every goal label the declared string supports, in taxonomy order. Empty when it supports none."""
    if not goal_text:
        return []
    normalised = fold(goal_text)
    found = [label for label, pattern in GOAL_PATTERNS if pattern.search(normalised)]
    return [label for label in PRIMARY_ORDER if label in found]


def primary(labels: list[str]) -> str:
    for label in PRIMARY_ORDER:
        if label in labels:
            return label
    return NO_GOAL


def is_compound(goal_text: str, labels: list[str], fold) -> bool:
    """True when the declared string names more than one goal that are not a recognised compatible pair.

    "Ganar masa muscular y tonificar" is the case this exists for: coarse taxonomy, not a mislabelled diet.
    """
    if len(labels) < 2:
        return False
    if len(labels) == 2 and frozenset(labels) in COMPATIBLE_PAIRS:
        return False
    normalised = fold(goal_text)
    if _TONIFICAR.search(normalised) and "volumen_masa" in labels:
        return True
    return True
