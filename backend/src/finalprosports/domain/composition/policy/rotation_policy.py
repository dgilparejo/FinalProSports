"""RotationPolicy (2.3): the professional's variation policy applied to a recurrent client.

Measured behaviour (la memoria (análisis de rotación)): between consecutive versions he keeps the STRUCTURE by family (14 of 27 families
persist >= 0,85) and rotates the SPECIES inside the family (most individual foods persist <= 0,5); base supplements persist moderately
but with lift 2-5 (kept on purpose); ubiquitous foods (arroz, pollo, AOVE: lift ~1) persist because they are everywhere.

Rule implemented: start from the client's previous version; keep every item whose food is an anchor — persistence >= `anchor_persistence`
OR lift >= `anchor_lift` with enough evidence —; for the others, in order of lowest persistence, replace the species by a food of the
SAME family taken from the archetype consensus (not present in the previous version) until the renewal target is reached; items with
no same-family candidate are kept. The renewal target is the professional's own rate: `renewal_same_goal` (0,27) when the goal is
unchanged, `renewal_goal_change` (0,42) otherwise. Deterministic; every replacement is recorded with its reason.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from finalprosports.domain.composition.policy.substitution_policy import counts_as_renewal, may_substitute
from finalprosports.domain.model import (AlternativeGroup, Diet, DietItem, Food, FoodGroup, ItemEvidence, MealSlot, ProposedItem,
                                         ProposedMeal, RotationStats)


@dataclass(frozen=True)
class RotationParams:
    anchor_persistence: float = 0.80
    anchor_lift: float = 2.0
    min_n: int = 10                      # below this evidence a food is neither anchor nor rotatory: it is kept
    renewal_target: float | None = None  # None -> the professional's measured rate for the goal transition
    supplement_renewal_target: float = 0.173
    """How much of the SUPPLEMENT macrogroup may rotate, measured separately because he treats it separately.

    Between consecutive versions of the same client and the same goal, his renewal is 29,3 % for food and **17,3 % for
    supplements, with a median of 0 % and no change at all in 52,1 % of the revisions** — he carries them over. The reason he
    gives is not nutritional: «si el cliente se compró un batido de proteínas, pues no se quede con medio bote sin usar porque
    se lo hemos cambiado». A single budget for the whole diet cannot express that, and the novelty control of the next feature
    would make it worse precisely when the professional asks for more variety, so supplements get their own budget and the
    novelty level does not touch it."""
    max_extra_from_consensus: int = 0    # consensus items added on top of the previous structure (0 = keep the previous size)
    use_repertoire: bool = True          # False: replace only with same-family foods present in the archetype consensus (conservative rotation)
    check_line_role: bool = True
    """Whether a substitute must share a macrogroup with the OTHER members of the line it lands in.

    It stops «yuca» being offered beside «quinoa» as if they were the same thing, but it costs renewal, and how much is
    measured rather than assumed: see the sweep in the batch report."""


@dataclass(frozen=True)
class RotationChange:
    slot: MealSlot
    removed_food_id: int
    removed_name: str | None
    added_food_id: int
    added_name: str | None
    family: str | None
    persistence: float | None
    reason: str


def is_anchor(food_id: int, stats: RotationStats, p: RotationParams) -> bool:
    if stats.n(food_id) < p.min_n:
        return False
    pers, lift = stats.persistence(food_id), stats.lift(food_id)
    return (pers is not None and pers >= p.anchor_persistence) or (lift is not None and lift >= p.anchor_lift)


def rotate(previous: Diet, consensus: list[ProposedMeal], goal_changed: bool, stats: RotationStats, catalog: dict[int, Food],
           params: RotationParams = RotationParams(), case_ids: tuple[str, ...] = (),
           repertoire: dict[str, list[int]] | None = None, allowed=None,
           medians: dict[tuple[int, str], float] | None = None) -> tuple[list[ProposedMeal], list[RotationChange], list[str]]:
    """`repertoire`: family -> food ids of the professional's repertoire ordered by preference (same-goal prevalence); used when the
    consensus offers no same-family replacement. Items replaced from the repertoire carry the consensus-less evidence (support 0).

    `allowed(food) -> bool` filters candidates INSIDE the selection: the client's hard restrictions and dislikes have to
    be known here, not downstream. Rotating a coeliac onto a food with gluten and letting the validator strip it afterwards leaves the
    slot short of an item, which is exactly what the functional test produced (five items lost in one proposal).
    `medians[(food_id, unit)]` is the corpus median used by the scale check of substitution_policy.
    Returns (meals, changes, refusals): the refusals explain why a candidate was rejected."""
    target = params.renewal_target if params.renewal_target is not None else (stats.renewal_goal_change if goal_changed else stats.renewal_same_goal)
    sup_target = params.supplement_renewal_target
    prev_foods = {i.food_id for m in previous.meals for i in m.items if i.food_id is not None}
    # candidate replacements from the consensus: per (slot, family) then per family, excluding foods already in the previous version
    by_slot_family: dict[tuple[MealSlot, str], list[ProposedItem]] = {}
    by_family: dict[str, list[ProposedItem]] = {}
    for m in consensus:
        for o in m.items:
            f = catalog.get(o.item.food_id)
            if f is None or o.item.food_id in prev_foods or not f.family:
                continue
            by_slot_family.setdefault((m.slot, f.family), []).append(o)
            by_family.setdefault(f.family, []).append(o)
    used: set[int] = set()
    refusals: list[str] = []

    def acceptable(original: Food, cand: Food, siblings: tuple[Food, ...] = (), line_is_his: bool = False,
                   original_has_amount: bool = False) -> bool:
        """`siblings` are the OTHER members of the alternative group the substitute is joining.

        A substitution was only ever checked against the food it replaces, and that is not enough: replacing «patata» with
        «yuca» inside «arroz / patata / quinoa» produces the pair «yuca / quinoa», which he never writes as alternatives, and
        nothing looked at it. The candidate has to be interchangeable with every member of the line it lands in — the group is
        a single offer to the client, not a chain of pairwise swaps."""
        if allowed is not None and not allowed(cand):
            refusals.append(f"{cand.canonical_name}: no permitido para este cliente (restricción o gusto)")
            return False
        # Un sustituto al que no se le va a poder escribir una CANTIDAD no sirve. «4 dientes de ajo» rotado a perejil
        # deja «Perejil» a secas: la unidad «diente» es del ajo, el perejil no tiene ninguna banda medida, y la capa de
        # plausibilidad -- correctamente -- prefiere quitar la cantidad heredada antes que inventarle una. El resultado
        # es una línea sin ración en mitad de la comida, que es una de las cosas que el preparador señaló. Se rechaza
        # aquí, donde todavía se puede elegir otro candidato, en vez de arreglarlo después, cuando ya no hay marcha atrás.
        if medians and original_has_amount and not any(k[0] == cand.id for k in medians):
            refusals.append(f"{original.canonical_name} -> {cand.canonical_name}: sin cantidad observada; "
                            f"quedaría escrito sin ración")
            return False
        inter = stats.are_interchangeable if stats.interchangeable else None
        ok, why = may_substitute(original, cand, medians, interchangeable=inter)
        if not ok:
            refusals.append(f"{original.canonical_name} -> {cand.canonical_name}: {why}")
            return False
        # Against the OTHER members of the line, the requirement is the role, not the written pairing. Demanding that he had
        # written the candidate as an alternative of every sibling too collapsed the renewal to 9,3 % against his measured
        # 27,2 %: with four or five options in a line almost nothing survives, and a rotation that cannot rotate makes the
        # novelty control of §8 meaningless. Sharing the macrogroup is what stops «yuca» landing beside «quinoa» as if they
        # were the same offer, which is the defect that was actually visible on the sheet.
        # ... and only on a line the SYSTEM composed. When the line is his — every option inherited from the client's own
        # previous version — its internal coherence is his, exactly as the conformance checker exempts his own groups from
        # the same rule. Imposing it there refused 1.137 candidates and left the rotation delivering 63 % of its budget.
        for other in (siblings if (params.check_line_role and not line_is_his) else ()):
            if other.id == cand.id:
                return False
            ma = {other.group} | ({other.secondary_group} if getattr(other, "secondary_group", None) else set())
            mb = {cand.group} | ({cand.secondary_group} if getattr(cand, "secondary_group", None) else set())
            if not (ma & mb):
                refusals.append(f"{other.canonical_name} / {cand.canonical_name}: distinto papel en la misma línea")
                return False
        return True

    def take(slot: MealSlot, original: Food, template: DietItem, siblings: tuple[Food, ...] = (),
             line_is_his: bool = False) -> ProposedItem | None:
        family = original.family
        for pool in (by_slot_family.get((slot, family), []), by_family.get(family, [])):
            for o in pool:
                cand = catalog.get(o.item.food_id)
                if o.item.food_id in used or cand is None or not acceptable(
                        original, cand, siblings, line_is_his, template.quantity.value is not None):
                    continue
                used.add(o.item.food_id)
                return o
        for fid in ((repertoire or {}).get(family, []) if params.use_repertoire else []):   # professional's repertoire of the family, by preference
            cand = catalog.get(fid)
            if fid in used or fid in prev_foods or cand is None or not acceptable(
                    original, cand, siblings, line_is_his, template.quantity.value is not None):
                continue
            used.add(fid)
            item = replace(template, food_id=fid, canonical_name=cand.canonical_name, normalized_key=cand.canonical_name, raw_text=cand.canonical_name)
            return ProposedItem(item, ItemEvidence((), 0.0))
        return None

    # rotation candidates in order of lowest persistence (only foods with evidence, not anchors)
    items = [(m.slot, g, o_idx, it) for m in previous.meals for g in _groups(m) for o_idx, it in enumerate(g)]
    group_of: dict[int, tuple] = {id(it): tuple(g) for m in previous.meals for g in _groups(m) for it in g}
    scored = []
    for slot, g, idx, it in items:
        if it.food_id is None or is_anchor(it.food_id, stats, params) or stats.n(it.food_id) < params.min_n:
            continue
        scored.append((stats.persistence(it.food_id), slot, id(g), idx, it))
    scored.sort(key=lambda t: (t[0], t[1].value, t[3]))
    def is_supplement(food_id: int | None) -> bool:
        f = catalog.get(food_id)
        return f is not None and f.group is FoodGroup.SUPPLEMENT

    prev_items = [i for m in previous.meals for i in m.items if i.food_id is not None]
    n_sup = sum(1 for i in prev_items if is_supplement(i.food_id)) or 0
    n_food = len(prev_items) - n_sup or 1
    budget = round(target * n_food)                       # the food budget is computed over FOOD, not over the whole diet
    sup_budget = round(sup_target * n_sup)                # ... and the supplements carry their own, much smaller one
    used_sup = 0
    replacements: dict[int, tuple[ProposedItem, RotationChange]] = {}          # id(item) -> replacement
    for pers, slot, _, idx, it in scored:
        supplement = is_supplement(it.food_id)
        if supplement:
            if used_sup >= sup_budget:
                continue                                  # his supplements are carried over: an open tub is the client's money
        elif len(replacements) - used_sup >= budget:
            break
        f = catalog.get(it.food_id)
        if f is None or not f.family:
            continue
        line = group_of.get(id(it), ())
        siblings = tuple(x for x in (catalog.get(o.food_id) for o in line if o is not it) if x is not None)
        cand = take(slot, f, it, siblings, line_is_his=len(line) > 1)   # a line of the previous version IS his
        if cand is None:
            continue
        cand_food = catalog.get(cand.item.food_id)
        if cand_food is not None and not counts_as_renewal(f, cand_food):
            continue                                                    # a swap that renews nothing must not consume the budget
        replacements[id(it)] = (cand, RotationChange(slot, it.food_id, it.canonical_name, cand.item.food_id, cand.item.canonical_name, f.family, pers,
                                                     f"rotatorio (persistencia {pers:.2f}) -> misma familia desde el consenso"
                                                     + (" [presupuesto de suplementos]" if supplement else "")))
        used_sup += supplement
    out, changes = [], []
    for m in previous.meals:
        groups = []
        for pos, g in enumerate(_groups(m)):
            options = []
            for ci, it in enumerate(g):
                if id(it) in replacements:
                    cand, ch = replacements[id(it)]
                    changes.append(ch)
                    new_item = replace(cand.item, meal_slot=m.slot, position=pos, component_index=ci, alternative_group=it.alternative_group,
                                        # el compuesto es del SITIO, no de la especie: si sustituye el batido dentro de
                                        # «batido + amilopectina + sales», el reemplazo sigue formando parte del compuesto
                                        compound_group=it.compound_group)
                    options.append(ProposedItem(new_item, replace(cand.evidence, rules=cand.evidence.rules)))
                else:
                    kept = replace(it, position=pos, component_index=ci, inherited=True)   # his value for this client
                    options.append(ProposedItem(kept, ItemEvidence((previous.id,), 1.0)))
            groups.append(AlternativeGroup(pos, tuple(options)))
        out.append(ProposedMeal(m.slot, tuple(groups)))
    return out, changes, refusals


def _groups(meal) -> list[list[DietItem]]:
    """Items of a meal grouped by position (alternatives share the position), in order."""
    by_pos: dict[int, list[DietItem]] = {}
    for it in meal.items:
        by_pos.setdefault(it.position, []).append(it)
    return [sorted(v, key=lambda i: i.component_index) for _, v in sorted(by_pos.items())]
