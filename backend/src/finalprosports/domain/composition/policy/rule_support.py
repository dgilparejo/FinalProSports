"""Which applicable rules back a proposed food in a slot (evidence for the explainability panel, E4.3).

The mapping is the reading of each rule's statement: a rule backs a food when the food is exactly the pattern the rule
describes (cereal at breakfast, supplement around training, carbohydrate at dinner for volume goals...). Prevalence and
lift come from the rule's empirical support in the corpus.
"""
from __future__ import annotations

from typing import Callable

from finalprosports.domain.model import ClientProfile, Food, FoodGroup, MealSlot, ProposedItem, ProposedMeal, Rule, RuleSupport

FIRST_HALF = {MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.BRUNCH, MealSlot.LUNCH, MealSlot.SNACK}
WORKOUT = {MealSlot.PRE_WORKOUT, MealSlot.INTRA_WORKOUT, MealSlot.POST_WORKOUT}   # dataset-v2: intra-workout is part of the training window (see rule_engine.WORKOUT)


def _groups(f: Food) -> set[FoodGroup]:
    return {f.group} | ({f.secondary_group} if f.secondary_group else set())


BACKS: dict[str, Callable[[Food, MealSlot], bool]] = {
    "desayuno_avena_cereales": lambda f, s: s is MealSlot.BREAKFAST and f.family == "cereal",
    "hidratos_en_cena": lambda f, s: s is MealSlot.DINNER and FoodGroup.CARB in _groups(f),
    "hidratos_primera_mitad_dia": lambda f, s: s in FIRST_HALF and FoodGroup.CARB in _groups(f),
    "cena_proteina_grasa_verdura": lambda f, s: s is MealSlot.DINNER and bool(_groups(f) & {FoodGroup.PROTEIN, FoodGroup.VEGETABLE, FoodGroup.FAT}),
    "suplementacion_pre_post": lambda f, s: s in WORKOUT and f.group is FoodGroup.SUPPLEMENT,
    "hombres_suplementacion": lambda f, s: s in WORKOUT and f.group is FoodGroup.SUPPLEMENT,
    "suplementacion_v5": lambda f, s: s in WORKOUT and f.group is FoodGroup.SUPPLEMENT,
    "sal_himalaya": lambda f, s: f.canonical_name == "sal del himalaya",
    "mujeres_sal_himalaya": lambda f, s: f.canonical_name == "sal del himalaya",
    "ansiedad_chocolate_o_gelatina": lambda f, s: f.canonical_name in ("chocolate negro", "gelatina"),
    "mujeres_chocolate_gelatina": lambda f, s: f.canonical_name in ("chocolate negro", "gelatina"),
    "agua_2.5L": lambda f, s: f.canonical_name == "agua",
    "grasas_base": lambda f, s: FoodGroup.FAT in _groups(f),
    "cafe_te_permitidos": lambda f, s: f.flags.is_fasting_compatible and f.group is FoodGroup.BEVERAGE,
    "sustituir_pescado_por_pollo": lambda f, s: s is MealSlot.DINNER and f.family == "ave",
    "pescado_pollo_v1": lambda f, s: s is MealSlot.DINNER and f.family == "ave",
}


def supporting_rules(food: Food, slot: MealSlot, applicable: list[Rule]) -> tuple[RuleSupport, ...]:
    return tuple(RuleSupport(r.id, r.prevalence, r.lift) for r in applicable if r.id in BACKS and BACKS[r.id](food, slot))


def attach_rule_support(meals: list[ProposedMeal], applicable: list[Rule], catalog: dict[int, Food]) -> list[ProposedMeal]:
    from dataclasses import replace
    out = []
    for m in meals:
        groups = []
        for g in m.groups:
            options = []
            for o in g.options:
                food = catalog.get(o.item.food_id)
                rules = supporting_rules(food, m.slot, applicable) if food else ()
                options.append(ProposedItem(o.item, replace(o.evidence, rules=rules)))
            groups.append(replace(g, options=tuple(options)))
        out.append(replace(m, groups=tuple(groups)))
    return out
