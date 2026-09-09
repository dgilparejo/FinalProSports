"""RuleEngine (E4.3): given a diet (case or proposal) and a profile, determines the applicable rules of the constitution
(goal / sex / phase) and evaluates each one. Pure domain policy.

Every rule of _dataset/validated_rules.json is implemented: 22 at item level (catalogue groups, flags, canonical names by
slot) and 9 at note level (patterns over the notes block; the composer composes notes from the cases, so they are evaluable).
Evaluation returns None when the rule cannot be judged on this diet (e.g. no dinner slot): such checks are not counted.

Descriptive / behaviour rules ("más frecuente en mujeres ...") are evaluated as the PRESENCE of the pattern they describe;
they are informative for the explainability panel, and they are disabled by default when their confidence is low.
"""
from __future__ import annotations

import re

from finalprosports.domain.composition.policy.rule_applicability import applies, phase_of
from finalprosports.domain.model import ClientProfile, Diet, Food, FoodGroup, MealSlot, Rule, RuleCheck

FIRST_HALF = {MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.BRUNCH, MealSlot.LUNCH, MealSlot.SNACK}
# The supplementation rules describe what he gives AROUND the training session. Until dataset-v2 the intra-workout intake was
# fused into ANTES DE ENTRENAR, so their prevalence was mined with it inside: leaving the new slot out would both change what
# the rule measures and make it inapplicable to a proposal whose training supplements sit in the intra slot (88 % of it).
WORKOUT = (MealSlot.PRE_WORKOUT, MealSlot.INTRA_WORKOUT, MealSlot.POST_WORKOUT)


def _rx(p: str) -> re.Pattern:
    return re.compile(p, re.I)


# note-level patterns (the same matchers that validated the rules on the corpus: _tools/build_validated_rules.py)
NOTE_PATTERNS: dict[str, re.Pattern] = {
    "agua_2.5L": _rx(r"litros de agua|2[.,]5 litros|ingesta de agua|beber agua|beber.*litros"),
    "comer_despacio": _rx(r"masticar|despacio"),
    "ayuno_16h": _rx(r"16\s*(a\s*17\s*)?horas|ayuno intermitente|16 h"),
    "ayuno_estable_por_fase": _rx(r"16\s*(a\s*17\s*)?horas|ayuno intermitente|16 h"),
    "comida_tarde_cena_temprano": _rx(r"lo m[aá]s tarde|lo m[aá]s temprano|m[aá]s tarde posible|m[aá]s temprano posible"),
    "sustituir_pescado_por_pollo": _rx(r"sustituir el pescado|sustituir el huevo|por pollo"),
    "refuerzo_fibra": _rx(r"fibra"),
    "alta_fibra_fases_tempranas": _rx(r"fibra"),
    "mujeres_alta_fibra": _rx(r"fibra"),
    "saltarse_comidas_fibra": _rx(r"saltarte 1 comida|dos comidas|2 comidas|saltar.*comida"),
    "saltarse_comidas_fases_tempranas": _rx(r"saltarte 1 comida|dos comidas|2 comidas|saltar.*comida"),
}
# rules whose violation the validator may enforce (prohibitions with high confidence, item level)
ENFORCEABLE = ("prohibido_azucar_procesados", "sin_hidratos_cena", "fruta_no_en_cena", "soja_prohibida", "mujeres_prohibicion_azucar")


class RuleEngine:
    def __init__(self, catalog: dict[int, Food]):
        self._catalog = catalog

    # ------------------------------------------------------------------------------------------------ helpers
    def foods_in(self, diet: Diet, slot: MealSlot | None = None) -> list[Food]:
        meals = [m for m in diet.meals if slot is None or m.slot is slot]
        return [self._catalog[i.food_id] for m in meals for i in m.items if i.food_id in self._catalog]

    def groups_in(self, diet: Diet, slot: MealSlot, primary_only: bool = False) -> set[FoodGroup]:
        """The food groups present in a slot.

        The secondary group counts by default and must NOT count for rules that FORBID a group, which is what
        `primary_only` is for. The secondary group is botanical or incidental; the primary one is the culinary role.
        For a rule that REQUIRES a group ("dinner needs protein and vegetable") a food that secondarily plays that
        role does contribute it. For a rule that FORBIDS one ("no fruit at dinner") the secondary group convicts a
        food of something it is not: the avocado is `FAT` with a botanical secondary of `FRUIT`, and the rule was
        pulling it out of dinners the professional writes himself 169 times.
        """
        out = set()
        for f in self.foods_in(diet, slot):
            out.add(f.group)
            if f.secondary_group and not primary_only:
                out.add(f.secondary_group)
        return out

    @staticmethod
    def notes_text(diet: Diet) -> str:
        return "\n".join(diet.notes).lower()

    # ------------------------------------------------------------------------------------------------ evaluation
    def evaluate(self, rule: Rule, diet: Diet) -> bool | None:      # noqa: C901 (one branch per rule is the readable form)
        rid = rule.id
        has_dinner = diet.meal(MealSlot.DINNER) is not None
        dinner = self.groups_in(diet, MealSlot.DINNER) if has_dinner else set()
        names = {f.canonical_name for f in self.foods_in(diet)}
        all_foods = self.foods_in(diet)
        notes = self.notes_text(diet)

        if rid == "agua_2.5L":
            water = [i for m in diet.meals for i in m.items if i.canonical_name == "agua"]
            if any(i.quantity.has_amount for i in water):
                return True
            return bool(NOTE_PATTERNS[rid].search(notes)) if (notes or water) else None
        if rid in ("prohibido_azucar_procesados", "mujeres_prohibicion_azucar"):
            return not any(f.flags.is_processed_sugar or f.flags.is_soft_drink for f in all_foods)
        if rid == "soja_prohibida":
            return not any(f.flags.contains_soy for f in all_foods)
        if rid == "cafe_te_permitidos":
            return any(f.flags.is_fasting_compatible and f.group is FoodGroup.BEVERAGE for f in all_foods) if all_foods else None
        if rid == "sin_hidratos_cena":
            return (FoodGroup.CARB not in dinner) if has_dinner else None
        if rid == "hidratos_en_cena":
            return (FoodGroup.CARB in dinner) if has_dinner else None
        if rid == "fruta_no_en_cena":
            # Primary group only: this is an avoid rule (see groups_in). Measured on the corpus, the foods the
            # secondary group used to catch are ones he serves at dinner constantly -- aguacate 25,6 % of its 661
            # uses, guacamole 31,7 % of 164, aceitunas 57,4 % of 47 -- while real dessert fruit is at 0,0-1,4 %.
            return (FoodGroup.FRUIT not in self.groups_in(diet, MealSlot.DINNER, primary_only=True)) if has_dinner else None
        if rid == "cena_proteina_grasa_verdura":
            return (FoodGroup.PROTEIN in dinner and FoodGroup.VEGETABLE in dinner) if has_dinner else None
        if rid == "hidratos_primera_mitad_dia":
            carb_slots = {m.slot for m in diet.meals if FoodGroup.CARB in self.groups_in(diet, m.slot)}
            return bool(carb_slots & FIRST_HALF) if carb_slots else None
        if rid == "desayuno_avena_cereales":
            b = diet.meal(MealSlot.BREAKFAST)
            return any(f.family == "cereal" for f in self.foods_in(diet, MealSlot.BREAKFAST)) if b else None
        if rid in ("suplementacion_pre_post", "hombres_suplementacion", "suplementacion_v5"):
            if not any(diet.meal(s) for s in WORKOUT):
                return None
            return any(f.group is FoodGroup.SUPPLEMENT for s in WORKOUT for f in self.foods_in(diet, s))
        if rid in ("sal_himalaya", "mujeres_sal_himalaya"):
            if "sal" not in names and "sal del himalaya" not in names:
                return None
            return "sal del himalaya" in names
        if rid in ("sustituir_pescado_por_pollo", "pescado_pollo_v1"):
            if not has_dinner:
                return None
            if NOTE_PATTERNS["sustituir_pescado_por_pollo"].search(notes):
                return True
            return any(f.family == "ave" for f in self.foods_in(diet, MealSlot.DINNER))
        if rid == "grasas_base":
            return (FoodGroup.FAT in {f.group for f in all_foods}) if all_foods else None
        if rid in ("mujeres_chocolate_gelatina", "ansiedad_chocolate_o_gelatina"):
            return bool(names & {"chocolate negro", "gelatina"})
        if rid == "respetar_intolerancias_alergias":
            return None                                   # enforced by the restriction policy, not measured as a rule
        if rid in ("no_restringe_lacteos_intolerantes", "miel_evidencia_insuficiente"):
            return None                                   # behaviour / descriptive: handled by RestrictionMode
        if rule.evaluation_level == "note" and rid in NOTE_PATTERNS:
            return bool(NOTE_PATTERNS[rid].search(notes)) if notes else None
        return None

    def applicable(self, rules: tuple[Rule, ...] | list[Rule], profile: ClientProfile, diet: Diet | None = None) -> list[Rule]:
        phase = phase_of(diet.diet_version) if diet is not None else None
        return [r for r in rules if applies(r, profile, phase)]

    def check(self, rules: tuple[Rule, ...] | list[Rule], diet: Diet, profile: ClientProfile) -> list[RuleCheck]:
        out = []
        for r in self.applicable(rules, profile, diet):
            res = self.evaluate(r, diet)
            out.append(RuleCheck(rule_id=r.id, applicable=res is not None, satisfied=res))
        return out

    def compliance(self, rules, diet: Diet, profile: ClientProfile, only: set[str] | None = None) -> tuple[float | None, int]:
        checks = [c for c in self.check(rules, diet, profile) if c.applicable and (only is None or c.rule_id in only)]
        return ((sum(1 for c in checks if c.satisfied) / len(checks)), len(checks)) if checks else (None, 0)
