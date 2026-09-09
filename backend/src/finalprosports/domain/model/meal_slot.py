from enum import StrEnum


class MealSlot(StrEnum):
    """Meal slots as written in the corpus (values are the corpus literals).

    DECLARATION ORDER IS THE ORDER OF THE DAY: ``composition_policy.SLOT_ORDER`` is ``tuple(MealSlot)`` and the
    printed document follows it. A new member goes in its temporal position, never appended.

    dataset-v3 added five. They are not new inventions: the professional writes them, and the twelve-prefix
    splitter folded each one into whichever slot happened to be open, which is why v2's MERIENDA count (896) is
    v3's MERIENDA (400) plus MEDIA TARDE (577), and its RECENA (225) is RECENA (18) plus ANTES DE DORMIR (191).
    The workaround was visible in the PDF template, which printed MERIENDA under the label "MEDIA TARDE" and
    OTHER under "Recién levantado": the slots existed in his documents all along and only the model lacked names
    for them. Same precedent as INTRA_WORKOUT, added when dataset-v2 found it.
    """

    ON_WAKING = "RECIEN LEVANTADO"               # dataset-v3: 439 diets; v2 printed it by relabelling OTHER
    BREAKFAST = "DESAYUNO"
    MID_MORNING = "MEDIA MAÑANA"
    BRUNCH = "ALMUERZO"
    LUNCH = "COMIDA"
    SNACK = "MERIENDA"
    MID_AFTERNOON = "MEDIA TARDE"                # dataset-v3: 577 diets; v2 had no such slot and printed MERIENDA under this label
    DINNER = "CENA"
    LATE_SNACK = "RECENA"
    BEFORE_BED = "ANTES DE DORMIR"               # dataset-v3: 191 diets, folded into RECENA by the old splitter
    PRE_WORKOUT = "ANTES DE ENTRENAR"
    INTRA_WORKOUT = "MITAD DE ENTRENAMIENTO"     # dataset-v2: a real intake occasion (438 blocks, 88 % supplements) the legacy splitter folded into ANTES DE ENTRENAR
    POST_WORKOUT = "DESPUES DE ENTRENAR"
    SHAKE = "BATIDO"
    SUPPLEMENTS = "SUPLEMENTOS"                  # dataset-v3: 289 diets
    WATER = "AGUA"                               # dataset-v3: 307 diets; mostly an intake instruction, not food
    OTHER = "OTHER"                              # the generic bucket: 528 distinct header shapes the vocabulary
    #                                              could not map with confidence keep their literal in
    #                                              ``raw_slot_label`` instead of becoming 528 enum members.
