"""PlausibilityPolicy (S2): is a proposal plausible in the professional's own terms?

The limits come from the DATA (plausibility envelope mined from the corpus by pipeline/plausibility_envelope.py), never from the
author's judgement: a quantity is plausible when it lies within [p05, p95] of what the professional wrote for that food and unit
(n >= 10 observations); a slot is plausible when its number of distinct foods lies within the slot's observed band; and so on.
The remaining checks are structural invariants of the professional's style (no repeated food in a slot, share of alternative groups
without a common macro group under his p95, dinner = protein + vegetable ...) or safety (declared restrictions, enforceable prohibitions).

Pure functions over domain objects. Consumed by the golden test suite (`make golden`) and reusable by any caller that wants to
audit a proposal; every violation names the slot, the food, the value and the range so that the failure is readable.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from finalprosports.domain.composition.policy.restriction_policy import veto_reasons
from finalprosports.domain.composition.policy.rule_engine import ENFORCEABLE
from finalprosports.domain.composition.policy.slot_composition_policy import REQUIRED_GROUPS
from finalprosports.domain.model import MAJORITY_PREVALENCE, Diet, DietProposal, Food, MealSlot, RestrictionMode, Rule, RuleScope, Unit

# a goal-conditional rule is REQUIRED only when it is PRESCRIPTIVE (Rule.nature: kept and followed in the majority of the group, cut
# MAJORITY_PREVALENCE = 0.5, decided by the constitution builder); a kept but minority rule is descriptive evidence, never a violation
NOVELTY_BAND = (0.35, 0.60)          # 1 - Jaccard(food sets) of a rotated version vs the previous one: the professional's measured renewal band (RESULTS §9)


@dataclass(frozen=True)
class QuantityRange:
    food_id: int
    unit: str
    n: int
    p05: float
    p50: float
    p95: float

    def contains(self, value: float) -> bool:
        return self.p05 <= value <= self.p95


@dataclass(frozen=True)
class PlausibilityEnvelope:
    quantities: dict[tuple[int, str], QuantityRange]        # (food_id, unit) -> band
    items_per_slot: dict[MealSlot, tuple[float, float]]      # slot -> (p05, p95) distinct foods
    slots_per_diet: tuple[float, float]                      # (p05, p95)
    mixed_alternatives_p95: float | None = None              # per-diet share of alternative groups with no macro group in common (p95, all goals); None = not measured
    mixed_alternatives_p95_by_goal: dict[str, float] | None = None   # the same per goal (n >= 10); goals without enough diets fall back to the max of these
    repeats_p95: dict[MealSlot, float] | None = None                  # slot -> p95 of repeated food occurrences in the slot (Fase 9: his habit, not a defect)
    repeats_p95_by_goal: dict[str, dict[MealSlot, float]] | None = None   # goal -> slot -> p95 (n >= 10); None / missing slot = fall back to repeats_p95, then to 0
    weighed_foods: dict[str, float] | None = None            # canonical name -> his gram median, for foods he never counts (§6: «1 pasas»)
    shake_foods: dict[str, float] | None = None              # canonical name -> his gram median, for protein shakes (§2: never «1 batido»)
    gram_medians: dict[str, float] | None = None             # canonical name -> his gram median (n >= 20), for the ration-coherence check
    ration_bands: dict[str, tuple[float, float]] | None = None   # macrogroup -> (p05, p95) of observed/predicted ration ratio
    food_variants: dict[str, str] | None = None              # normalized_key -> how he writes it («arroz integral» -> «Arroz integral»)
    supplement_rations: dict[str, tuple[float, str]] | None = None   # canonical -> (median, unit) with which HE doses it

    def supplement_ration(self, canonical_name: str | None) -> tuple[float, str] | None:
        """His dose for a supplement, used ONLY to give a quantity to one emitted without any (§2). Never to overwrite."""
        return (self.supplement_rations or {}).get(canonical_name or "")

    def variant_text(self, normalized_key: str | None) -> str | None:
        """His own, more specific wording for a component whose canonical the catalogue has flattened (§3)."""
        return (self.food_variants or {}).get((normalized_key or "").replace("_", " ").strip().lower())

    def gram_portion(self, canonical_name: str | None) -> float | None:
        """His gram ration for a food that must not be written as a bare count.

        Two curated lists, both mined and both versioned in `pipeline/data/portion_units.json`: foods he weighs and of which
        he NEVER writes a count other than one — «1 pasas» is not a ration — and the protein shakes, which he always names in
        grams and the composer emitted as «1 batido». The plausibility envelope cannot carry them on its own because it needs
        n >= 10 per (food, unit) and several of these have fewer gram observations than that."""
        if not canonical_name:
            return None
        return (self.weighed_foods or {}).get(canonical_name) or (self.shake_foods or {}).get(canonical_name)

    def repeats_limit(self, goal: str | None, slot: MealSlot) -> float:
        """How many repeated occurrences of a food the professional himself allows in this slot for this goal (p95); 0 when not measured."""
        if goal and self.repeats_p95_by_goal and slot in self.repeats_p95_by_goal.get(goal, {}):
            return self.repeats_p95_by_goal[goal][slot]
        if self.repeats_p95 and slot in self.repeats_p95:
            return self.repeats_p95[slot]
        return 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "PlausibilityEnvelope":
        q = {(int(v["food_id"]), v["unit"]): QuantityRange(int(v["food_id"]), v["unit"], int(v["n"]), float(v["p05"]), float(v["p50"]), float(v["p95"]))
             for v in d["quantities"].values()}
        slots = {}
        for name, v in d["items_per_slot"].items():
            try:
                slots[MealSlot(name)] = (float(v["p05"]), float(v["p95"]))
            except ValueError:
                continue
        sd = d["slots_per_diet"]
        alt = d.get("alternative_groups") or {}
        ag = alt.get("per_diet_mixed_macro_share")
        by_goal = {g: float(v["p95"]) for g, v in (alt.get("per_goal_mixed_macro_share") or {}).items()} or None

        def slot_p95(table: dict) -> dict[MealSlot, float]:
            out = {}
            for name, v in (table or {}).items():
                try:
                    out[MealSlot(name)] = float(v["p95"])
                except ValueError:
                    continue
            return out
        repeats = slot_p95(d.get("repeats_per_slot")) or None
        repeats_goal = {g: slot_p95(t) for g, t in (d.get("repeats_per_slot_by_goal") or {}).items()} or None
        portions = d.get("portion_units") or {}
        weighed = {r["food"]: float(r["gram_median"]) for r in portions.get("weighed_foods", [])} or None
        shakes = {r["food"]: float(r["gram_median"]) for r in portions.get("shake_foods", [])} or None
        medians = {k: float(v) for k, v in (portions.get("food_gram_medians") or {}).items()} or None
        bands = {g: (float(v["p05"]), float(v["p95"])) for g, v in ((portions.get("ration_coherence") or {}).get("by_group") or {}).items()} or None
        variants = {v["key"]: v["text"] for vs in (d.get("food_variants") or {}).values() for v in vs} or None
        rations = {r["food"]: (float(r["median"]), r["unit"]) for r in portions.get("supplement_rations", [])} or None
        return cls(q, slots, (float(sd["p05"]), float(sd["p95"])), float(ag["p95"]) if ag else None, by_goal, repeats, repeats_goal,
                   weighed, shakes, medians, bands, variants, rations)

    def mixed_alternatives_limit(self, goal: str | None) -> float | None:
        """p95 of the goal when measured; otherwise the largest p95 among measured goals (whatever he does in some goal is acceptable); else global."""
        if self.mixed_alternatives_p95_by_goal:
            return self.mixed_alternatives_p95_by_goal.get(goal or "", max(self.mixed_alternatives_p95_by_goal.values()))
        return self.mixed_alternatives_p95

    def units_of(self, food_id: int) -> frozenset[str]:
        return frozenset(u for (f, u) in self.quantities if f == food_id)


@dataclass(frozen=True)
class Violation:
    check: str                          # quantity_out_of_range | items_per_slot | slot_count | repeated_food | alternative_groups_mixed | restriction |
    #                                     forbidden_by_constitution | goal_rule_unsatisfied | slot_structure | novelty | unseen_unit
    detail: str
    slot: str | None = None
    food_id: int | None = None
    canonical_name: str | None = None

    def __str__(self) -> str:
        where = f"{self.slot} · " if self.slot else ""
        who = f"{self.canonical_name} · " if self.canonical_name else ""
        return f"[{self.check}] {where}{who}{self.detail}"


def _fmt(v: float) -> str:
    return f"{int(v)}" if float(v).is_integer() else f"{v:g}"


def novelty(previous: Diet, proposal: DietProposal) -> float:
    a, b = previous.food_ids, proposal.food_ids
    return 1.0 - (len(a & b) / len(a | b) if (a | b) else 0.0)


def check_plausibility(proposal: DietProposal, envelope: PlausibilityEnvelope, catalog: dict[int, Food], rules: tuple[Rule, ...] = (),
                       previous: Diet | None = None, expected_slots: int | None = None, novelty_band: tuple[float, float] = NOVELTY_BAND,
                       mode: RestrictionMode = RestrictionMode.STRICT) -> tuple[Violation, ...]:
    out: list[Violation] = []
    by_id = {r.id: r for r in rules}
    alt_total, mixed = 0, []            # alternative groups with >= 2 options / those with no macro group in common

    # 1-2. quantities and units, per item
    for m in proposal.meals:
        for o in m.items:
            it = o.item
            if it.food_id is None or it.quantity.value is None:
                continue
            band = envelope.quantities.get((it.food_id, it.quantity.unit.value))
            if band is None:
                seen = envelope.units_of(it.food_id)
                # The name comes from the CATALOGUE: an item the rotation inherited from the previous version arrives with
                # `canonical_name` unset (it is filled in at the REST boundary), and looking it up by the item's own name
                # silently skipped the exemption for every rotated diet.
                _f = catalog.get(it.food_id)
                curated = (envelope.gram_portion(it.canonical_name or (_f.canonical_name if _f else None)) is not None
                           and it.quantity.unit is Unit.GRAM)
                if seen and it.quantity.unit.value not in seen and not curated:
                    out.append(Violation("unseen_unit", f"unidad «{it.quantity.unit.value}» no observada para este alimento (observadas: {', '.join(sorted(seen))})",
                                         m.slot.value, it.food_id, it.canonical_name))
                continue
            if not band.contains(float(it.quantity.value)):
                out.append(Violation("quantity_out_of_range", f"{_fmt(it.quantity.value)} {band.unit} fuera de [{_fmt(band.p05)}, {_fmt(band.p95)}] {band.unit} (n={band.n})",
                                     m.slot.value, it.food_id, it.canonical_name))

    # 3. distinct foods per slot
    # The FLOOR does not apply to a proposal built under a hard restriction, and the ceiling always does. The band
    # is mined over a corpus of clients who had no such restriction, so demanding its p05 of a client who cannot
    # eat a whole family means demanding they eat it: with the tree-nut and peanut restriction the golden profile
    # 17 gets MERIENDA = {aguacate, pavo} = 2, below the p05 of 3, and the SAME profile without the restriction
    # gets 3 -- one of which is `almendras`. Nuts are 13,2 % of his MERIENDA components, so the slot shrinking is
    # the restriction working, not the composer failing. Ceiling kept: nothing about an allergy makes a slot of
    # nineteen foods plausible.
    restricted = bool(getattr(proposal.profile, "restrictions", ()) or ()) if proposal.profile is not None else False
    for m in proposal.meals:
        foods = [o.item.food_id for o in m.items if o.item.food_id is not None]
        band = envelope.items_per_slot.get(m.slot)
        if not band:
            continue
        n = len(set(foods))
        low = band[0] if not restricted else 0.0
        if not (low <= n <= band[1]):
            out.append(Violation("items_per_slot", f"{n} alimentos distintos fuera de [{_fmt(low)}, {_fmt(band[1])}]", m.slot.value))
        # 5. repeated food in the slot: a violation only beyond the professional's own p95 for this goal and slot (0 when not measured)
        repeated = len(foods) - len(set(foods))
        limit = envelope.repeats_limit(proposal.profile.goal.value if proposal.profile and proposal.profile.goal else None, m.slot)
        if repeated > limit:
            worst = Counter(foods).most_common(1)[0][0]
            out.append(Violation("repeated_food", f"{repeated} repeticiones de alimento en la franja, por encima de su p95 ({_fmt(limit)})", m.slot.value, worst,
                                 catalog[worst].canonical_name if worst in catalog else None))
        # 6. alternatives: collected here, judged at proposal level (see below)
        for g in m.groups:
            groups_of = [{catalog[o.item.food_id].group} | ({catalog[o.item.food_id].secondary_group} if catalog[o.item.food_id].secondary_group else set())
                         for o in g.options if o.item.food_id in catalog]
            if len(groups_of) > 1:
                alt_total += 1
                if not set.intersection(*groups_of):
                    mixed.append(f"{m.slot.value}: " + " / ".join(o.item.canonical_name or "?" for o in g.options))
        # 10. required structure of the slot
        required = REQUIRED_GROUPS.get(m.slot)
        if required:
            present = set()
            for o in m.items:
                f = catalog.get(o.item.food_id)
                if f:
                    present.add(f.group)
                    if f.secondary_group:
                        present.add(f.secondary_group)
            missing = required - present
            if missing:
                out.append(Violation("slot_structure", f"faltan grupos exigidos: {', '.join(sorted(g.value for g in missing))}", m.slot.value))

    # 6. alternatives: the corpus refutes «same family» (63 % of his groups mix families) and even «same macro group» (21 %); the data-driven
    #    limit is the per-diet share of groups with no macro group in common, p95 of the corpus
    limit = envelope.mixed_alternatives_limit(proposal.profile.goal.value if proposal.profile.goal else None)
    if alt_total and limit is not None and len(mixed) / alt_total > limit:
        out.append(Violation("alternative_groups_mixed", f"{len(mixed)} de {alt_total} grupos de alternativas sin macrogrupo común ({len(mixed) / alt_total:.2f} > p95 "
                                                         f"del objetivo {limit:.2f}): " + "; ".join(mixed)))

    # 4. slot count
    n_slots = len(proposal.meals)
    if expected_slots is not None:
        if n_slots != expected_slots:
            out.append(Violation("slot_count", f"{n_slots} franjas, se pidieron {expected_slots}"))
    elif not (envelope.slots_per_diet[0] <= n_slots <= envelope.slots_per_diet[1]):
        out.append(Violation("slot_count", f"{n_slots} franjas fuera de [{_fmt(envelope.slots_per_diet[0])}, {_fmt(envelope.slots_per_diet[1])}]"))

    # 7. declared restrictions
    for m in proposal.meals:
        for o in m.items:
            f = catalog.get(o.item.food_id)
            if f:
                for reason in veto_reasons(f, proposal.profile, mode):
                    out.append(Violation("restriction", f"viola la restricción declarada {reason.split(':', 1)[1]}", m.slot.value, f.id, f.canonical_name))

    # 8-9. constitution: enforceable prohibitions and goal-conditional rules, from the validation report
    for c in proposal.rule_checks:
        if not c.applicable or c.satisfied is not False:
            continue
        rule = by_id.get(c.rule_id)
        if c.rule_id in ENFORCEABLE:
            out.append(Violation("forbidden_by_constitution", f"regla exigible incumplida: {c.rule_id}"))
        elif rule is not None and rule.scope is RuleScope.GOAL and rule.is_prescriptive                 and rule.evaluation_level == "item":
            # ITEM level only, and the restriction is about what the system can DO, not about how much we believe
            # the rule. An item-level rule is satisfiable: composition chooses the foods and the validator can force
            # them. A NOTE-level rule is satisfied only if the note survives the consensus over the k neighbours,
            # and no component can put it there: `ayuno_16h` is written in 57,8 % of his fasting diets over sixteen
            # different wordings, the theme catalogue consolidates them correctly, and the twenty neighbours of a
            # given query still carried it 25 % of the time -- under the 0,35 threshold. Demanding it of 100 % of
            # proposals asks the engine for something it has no mechanism to produce, which is not a violation of
            # plausibility but a limit of the instrument. It is reported as evidence instead (rule_checks keeps it).
            # Today this changes exactly one rule: the other three prescriptive goal rules are item-level.
            out.append(Violation("goal_rule_unsatisfied", f"regla condicional prescriptiva del objetivo incumplida: {c.rule_id} "
                                                          f"(prevalencia {rule.prevalence if rule.prevalence is not None else float('nan'):.2f} > {MAJORITY_PREVALENCE:.2f})"))

    # 11. novelty against the previous version
    if previous is not None:
        nv = novelty(previous, proposal)
        if not (novelty_band[0] <= nv <= novelty_band[1]):
            out.append(Violation("novelty", f"novedad {nv:.3f} fuera de la banda [{novelty_band[0]:.2f}, {novelty_band[1]:.2f}] respecto a {previous.id}"))
    return tuple(out)
