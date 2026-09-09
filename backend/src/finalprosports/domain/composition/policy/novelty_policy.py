"""How different the next diet should be from the client's previous one (§8 of the expert review).

The professional asked for it directly, and gave the reason: «se tiene que poder elegir si el entrenador quiere que sea muy
distinta la dieta de la anterior del cliente, por el bien psicológico del cliente». The machinery already existed — the
rotation works to a renewal budget — but the budget was internal and always took his measured average. This exposes it as
three levels, and every one of them is a number measured on his own practice, not a slider invented for the screen:

    conservadora   0,15   below his same-goal rate: the diet is recognisably the previous one
    equilibrada    0,272  his measured renewal between consecutive versions of the SAME goal (rotation_analysis)
    muy distinta   0,424  his measured renewal when the GOAL CHANGES, which is the most he ever renews at once

The upper level is deliberately not higher than 0,424: renewing more than he ever renews would not be «his diet, refreshed»,
it would be a different diet, and the whole system is built on reproducing what he does.

**Supplements are outside this control, at every level.** He renews them at 17,3 % against 29,3 % for food, with a median of
zero, and the reason is economic rather than nutritional: «si el cliente se compró un batido de proteínas, pues no se quede
con medio bote sin usar porque se lo hemos cambiado en la dieta». If the novelty level reached them, asking for more variety
would throw away the client's money — the opposite of what he wants. Their budget lives in `RotationParams` and stays there.
"""
from enum import StrEnum


class NoveltyLevel(StrEnum):
    CONSERVATIVE = "conservadora"
    BALANCED = "equilibrada"
    HIGH = "muy_distinta"


#: level -> renewal target for FOOD (supplements never take it)
RENEWAL_TARGET: dict[NoveltyLevel, float] = {
    NoveltyLevel.CONSERVATIVE: 0.15,
    NoveltyLevel.BALANCED: 0.272,
    NoveltyLevel.HIGH: 0.424,
}

DEFAULT = NoveltyLevel.BALANCED


def renewal_target(level: "NoveltyLevel | str | None") -> float | None:
    """The food renewal target for a level; None when no level is given, which leaves the measured default in place."""
    if level is None:
        return None
    try:
        return RENEWAL_TARGET[NoveltyLevel(level)]
    except ValueError:
        return None
