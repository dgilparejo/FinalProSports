"""DietValidator (E4.3;): independent component that validates ANY proposal (composer, LLM fallback, edited by hand).

Priority order: (1) hard restrictions of the profile — allergies / intolerances — veto foods (restriction_policy, in the
configured RestrictionMode); (1b) disliked foods of the intake sheet are removed as soft exclusions (S3); (2) enforceable
prohibitions of the constitution (rule_engine.ENFORCEABLE) remove the offending foods when `enforce_rules` is on; (2b) prescriptive
rules that demand PRESENCE are completed by adding the missing food; (3) every applicable rule is evaluated on the result.
Removing an option from an alternative group keeps the group; removing the last option removes the group.

**Why the completion exists.** Until now the validator could only SUBTRACT. Satisfying a prohibition is removing a food; satisfying
a prescription is adding one and deciding which — so every prescriptive rule demanding presence was structurally unenforceable, and
a client whose dinner had no vegetable was simply left that way. That is not a metric problem, it is a product defect measured
against the professional's own rules. The completion picks the best supported food for that slot and group among the k retrieved
cases (the evidence the composer already has), never violating the client's restrictions, and quantifies it with the corpus median
so the result stays inside the plausibility envelope. When no valid candidate exists — a coeliac who would need bread — the rule is
declared UNSATISFIABLE in the report instead of forcing something implausible.

**Only PRESCRIPTIVE rules are completed.** `hidratos_en_cena` is descriptive with prevalence 0,104 (the professional puts a
carbohydrate in the dinner of 50 of the 479 diets of those goals). Demanding it of a proposal would move the system away from his
practice, not towards it: a descriptive rule is reported, never required (Fase 9 B).
"""
from __future__ import annotations

from dataclasses import replace

from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope
from finalprosports.domain.composition.policy.restriction_policy import veto_reasons, warnings
from finalprosports.domain.composition.policy.rule_applicability import applies
from finalprosports.domain.composition.policy.rule_engine import ENFORCEABLE, WORKOUT, RuleEngine
from finalprosports.domain.model import (
    AlternativeGroup, ClientProfile, DietItem, DietProposal, Food, FoodGroup, ForcedChange, ItemEvidence, MealSlot, ProposedItem,
    ProposedMeal, Quantity, RestrictionMode, Rule, RuleCheck, Unit, ValidationReport,
)

# what an enforceable rule forbids: (slot or None for any, predicate on the food)
FORBIDS = {
    "prohibido_azucar_procesados": (None, lambda f: f.flags.is_processed_sugar or f.flags.is_soft_drink),
    "mujeres_prohibicion_azucar": (None, lambda f: f.flags.is_processed_sugar or f.flags.is_soft_drink),
    "soja_prohibida": (None, lambda f: f.flags.contains_soy),
    "sin_hidratos_cena": (MealSlot.DINNER, lambda f: f.group is FoodGroup.CARB),
    # Primary group ONLY, same semantics as RuleEngine.groups_in(primary_only=True). The secondary group is
    # botanical; the rule is about the culinary role. Reading it convicted the avocado (FAT, secondary FRUIT) of
    # being dessert and pulled it out of dinner -- a dinner the professional writes 169 times out of its 661 uses.
    "fruta_no_en_cena": (MealSlot.DINNER, lambda f: f.group is FoodGroup.FRUIT),
}

FIRST_HALF_ORDER = (MealSlot.LUNCH, MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.SNACK, MealSlot.BRUNCH)   # where he would put it first

# mirror image of FORBIDS: what a prescriptive rule REQUIRES -> (slots where it may be satisfied, groups that must be present)
REQUIRES: dict[str, tuple[tuple[MealSlot, ...], tuple[FoodGroup, ...]]] = {
    "cena_proteina_grasa_verdura": ((MealSlot.DINNER,), (FoodGroup.PROTEIN, FoodGroup.VEGETABLE)),
    "desayuno_avena_cereales": ((MealSlot.BREAKFAST,), (FoodGroup.CARB,)),
    "hidratos_primera_mitad_dia": (FIRST_HALF_ORDER, (FoodGroup.CARB,)),
    "suplementacion_pre_post": (WORKOUT, (FoodGroup.SUPPLEMENT,)),
}


class DietValidator:
    def __init__(self, catalog: dict[int, Food], mode: RestrictionMode = RestrictionMode.STRICT, enforce_rules: bool = True,
                 envelope: PlausibilityEnvelope | None = None):
        self._catalog, self._mode, self._enforce = catalog, mode, enforce_rules
        self._engine = RuleEngine(catalog)
        self._envelope = envelope            # the completion quantifies with the corpus median, so what it adds is plausible

    # --------------------------------------------------------------------------------------------------------- subtract
    def _filter(self, meals: tuple[ProposedMeal, ...], reason_for) -> tuple[tuple[ProposedMeal, ...], list[ForcedChange]]:
        changes, out = [], []
        for m in meals:
            groups = []
            for g in m.groups:
                kept = []
                for o in g.options:
                    food = self._catalog.get(o.item.food_id)
                    reason = reason_for(food, m.slot) if food else None
                    if reason:
                        changes.append(ForcedChange(m.slot, o.item.food_id, o.item.canonical_name, "removed", reason))
                    else:
                        kept.append(o)
                if kept:
                    groups.append(AlternativeGroup(g.position, tuple(kept)))
            if groups:
                out.append(replace(m, groups=tuple(groups)))
        return tuple(out), changes

    # ------------------------------------------------------------------------------------------------------------- add
    def _allowed(self, food: Food, profile: ClientProfile) -> bool:
        return not veto_reasons(food, profile, self._mode) and food.id not in (profile.disliked_food_ids or ())

    def _candidates(self, cases, slot: MealSlot, group: FoodGroup, profile: ClientProfile) -> list[tuple[int, int]]:
        """(food_id, support) for that slot and group among the retrieved cases, best supported first, already filtered by the
        client's restrictions and by the units the professional has actually written for that food."""
        support: dict[int, int] = {}
        for c in cases or ():
            diet = getattr(c, "diet", None)
            meal = diet.meal(slot) if diet is not None else None
            if meal is None:
                continue
            for fid in {i.food_id for i in meal.items if i.food_id is not None}:
                f = self._catalog.get(fid)
                if f is None or (f.group is not group and f.secondary_group is not group) or not self._allowed(f, profile):
                    continue
                support[fid] = support.get(fid, 0) + 1
        return sorted(support.items(), key=lambda kv: (-kv[1], kv[0]))

    def _quantity(self, food_id: int) -> Quantity:
        """The professional's own median for the food, in the unit he writes most; no envelope -> no quantity (never invented)."""
        if self._envelope is None:
            return Quantity(None, Unit.NONE)
        bands = [(u, b) for (fid, u), b in self._envelope.quantities.items() if fid == food_id]
        if not bands:
            return Quantity(None, Unit.NONE)
        unit, band = max(bands, key=lambda ub: ub[1].n)
        try:
            return Quantity(band.p50, Unit(unit))
        except ValueError:
            return Quantity(None, Unit.NONE)

    def _add(self, meals: tuple[ProposedMeal, ...], slot: MealSlot, food: Food, support: int, k: int) -> tuple[ProposedMeal, ...]:
        out = []
        for m in meals:
            if m.slot is not slot:
                out.append(m)
                continue
            pos = max((g.position for g in m.groups), default=-1) + 1
            item = DietItem(meal_slot=slot, position=pos, component_index=0, food_id=food.id, canonical_name=food.canonical_name,
                            normalized_key=food.canonical_name, raw_text=food.canonical_name, quantity=self._quantity(food.id))
            option = ProposedItem(item, ItemEvidence((), round(support / k, 4) if k else 0.0))
            out.append(replace(m, groups=m.groups + (AlternativeGroup(pos, (option,)),)))
        return tuple(out)

    def _complete(self, proposal: DietProposal, meals: tuple[ProposedMeal, ...], rules, profile: ClientProfile,
                  cases) -> tuple[tuple[ProposedMeal, ...], list[ForcedChange], list[str], set[str]]:
        added: list[ForcedChange] = []
        unsatisfiable: list[str] = []
        completed: set[str] = set()
        for r in rules:
            if r.id not in REQUIRES or not r.is_prescriptive:
                continue
            slots, groups = REQUIRES[r.id]
            for group in groups:
                diet = to_diet(replace(proposal, meals=meals))
                if any(group in self._engine.groups_in(diet, s) for s in slots):
                    continue                                            # already satisfied somewhere it may be satisfied
                target = next((s for s in slots if any(m.slot is s for m in meals)), None)
                if target is None:
                    continue                                            # none of the slots is in the proposal: not a completion problem
                cands = self._candidates(cases, target, group, profile)
                if not cands:
                    unsatisfiable.append(f"rule:{r.id}: sin candidato válido para {group.value} en {target.value} (restricciones del cliente)")
                    continue
                fid, sup = cands[0]
                meals = self._add(meals, target, self._catalog[fid], sup, len(cases or ()))
                added.append(ForcedChange(target, fid, self._catalog[fid].canonical_name, "added", f"rule:{r.id}"))
                completed.add(r.id)
        return meals, added, unsatisfiable, completed

    # -------------------------------------------------------------------------------------------------------- validate
    def validate(self, proposal: DietProposal, rules: tuple[Rule, ...], profile: ClientProfile | None = None,
                 cases: tuple = ()) -> DietProposal:
        profile = profile or proposal.profile
        applicable = [r for r in rules if applies(r, profile)]
        forced: list[ForcedChange] = []

        # 1. hard restrictions (maximum priority)
        meals, ch = self._filter(proposal.meals, lambda f, s: (veto_reasons(f, profile, self._mode) or (None,))[0])
        forced += ch
        # 1b. soft exclusions: foods the client dislikes (intake sheet, resolved against the catalogue) — a preference, recorded as such (S3)
        if profile.disliked_food_ids:
            meals, ch = self._filter(meals, lambda f, s: "preference:disliked" if f.id in profile.disliked_food_ids else None)
            forced += ch
        warn = tuple(sorted({w for m in meals for o in m.items if o.item.food_id in self._catalog for w in warnings(self._catalog[o.item.food_id], profile, self._mode)}))

        # 2. enforceable prohibitions of the constitution
        enforced_ids: set[str] = set()
        if self._enforce:
            active = [r for r in applicable if r.id in ENFORCEABLE and r.id in FORBIDS]
            for r in active:
                slot, pred = FORBIDS[r.id]
                meals, ch = self._filter(meals, lambda f, s, slot=slot, pred=pred: f"rule:{r.id}" if (slot is None or s is slot) and pred(f) else None)
                if ch:
                    enforced_ids.add(r.id)
                    forced += ch

        # 2b. completion: a prescriptive rule that demands presence is satisfied by ADDING, not by subtracting
        unsatisfiable: list[str] = []
        if self._enforce:
            meals, ch, unsatisfiable, completed = self._complete(proposal, meals, applicable, profile, cases)
            enforced_ids |= completed
            forced += ch

        # 3. evaluate every applicable rule on the result
        interim = replace(proposal, meals=meals)
        checks = [RuleCheck(c.rule_id, c.applicable, c.satisfied, enforced=c.rule_id in enforced_ids) for c in self._engine.check(applicable, to_diet(interim), profile)]
        return replace(interim, validation=ValidationReport(tuple(checks), tuple(forced), warn + tuple(unsatisfiable)))
