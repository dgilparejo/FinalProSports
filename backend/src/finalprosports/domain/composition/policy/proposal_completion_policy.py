"""ProposalCompletionPolicy (S2): the plausibility layer applied AFTER a strategy composed a proposal and BEFORE the validator.

The golden suite showed where a raw proposal falls outside the professional's envelope even though every ingredient came from his
cases: (a) a slot may lack a group his style requires (dinner without vegetable, breakfast without cereal) or end up thinner than he
ever writes it, because the inclusion threshold cut the consensus; (b) a quantity may fall outside the band he uses for that food
and unit — the median of k cases can sit above p95, and a species rotated within its family inherits the quantity and unit of the
species it replaces («1 unidad de piña» where he writes «2 lonchas»).

Two pure functions, both deterministic and both explained in the returned change list:
  complete_structure     adds, per slot, the best-supported food of each missing required group (slot_composition_policy) and tops the
                         slot up to the professional's minimum (p05 distinct foods) with the next best-supported candidates of the
                         retrieved cases. Nothing is invented: candidates come from the cases, in support order.
  normalize_quantities   clamps every quantity into [p05, p95] of its (food, unit) band and, when the unit was never observed for that
                         food, switches to his most frequent unit with its median; a food he never quantified that inherits a food-specific
                         unit from the species it replaced («3 dientes de sacarina») is left without amount.
The evaluation harness measures the raw strategies (composition alone); this layer is applied by the use case (API, golden suite).
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from dataclasses import dataclass, replace

from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope
from finalprosports.domain.composition.policy.composition_policy import MIN_CASE_SUPPORT
from finalprosports.domain.composition.policy.quantity_policy import on_his_grid
from finalprosports.domain.composition.policy.restriction_policy import veto_reasons
from finalprosports.domain.composition.policy.slot_composition_policy import REQUIRED_GROUPS
from finalprosports.domain.model import (AlternativeGroup, ClientProfile, DietItem, Food, FoodGroup, ItemEvidence, MealSlot, ProposedItem,
                                         ProposedMeal, Quantity, RestrictionMode, RetrievedCase, Unit)

FOOD_SPECIFIC_UNITS = frozenset({Unit.CLOVE, Unit.SLICE, Unit.CAN, Unit.SCOOP, Unit.CAPSULE, Unit.HANDFUL, Unit.DASH, Unit.TABLESPOON, Unit.TEASPOON})   # units that belong to a kind of food (dientes de ajo, latas de atún)


@dataclass(frozen=True)
class CompletionChange:
    kind: str                     # added_required_group | topped_up | quantity_clamped | unit_replaced
    slot: str
    food_id: int | None
    canonical_name: str | None
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "slot": self.slot, "food_id": self.food_id, "canonical_name": self.canonical_name, "detail": self.detail}


def _groups(f: Food) -> set[FoodGroup]:
    return {f.group} | ({f.secondary_group} if f.secondary_group else set())


def _fmt(v: float) -> str:
    return f"{int(v)}" if float(v).is_integer() else f"{v:g}"


def _support_by_slot(cases: tuple[RetrievedCase, ...], catalog: dict[int, Food]) -> dict[MealSlot, dict[int, tuple[list[str], list[Quantity], Counter]]]:
    """slot -> food -> (case ids containing it, quantities, normalized keys) over the retrieved cases."""
    out: dict[MealSlot, dict[int, tuple[list[str], list[Quantity], Counter]]] = defaultdict(lambda: defaultdict(lambda: ([], [], Counter())))
    for c in cases:
        for m in c.diet.meals:
            seen = set()
            for it in m.items:
                if it.food_id is None or it.food_id not in catalog:
                    continue
                ids, qs, keys = out[m.slot][it.food_id]
                if it.food_id not in seen:
                    ids.append(c.diet.id); seen.add(it.food_id)
                qs.append(it.quantity); keys[it.normalized_key] += 1
    return out


def _median_quantity(qs: list[Quantity]) -> Quantity:
    from finalprosports.domain.composition.policy.quantity_policy import median_quantity
    return median_quantity(qs)


def _new_item(slot: MealSlot, position: int, food: Food, support: tuple[list[str], list[Quantity], Counter], n_cases: int) -> ProposedItem:
    ids, qs, keys = support
    q = _median_quantity(qs)
    key = keys.most_common(1)[0][0] if keys else food.canonical_name
    item = DietItem(meal_slot=slot, position=position, component_index=0, food_id=food.id, canonical_name=food.canonical_name, normalized_key=key,
                    raw_text=food.canonical_name, quantity=q)
    return ProposedItem(item, ItemEvidence(tuple(ids), round(len(ids) / n_cases, 4) if n_cases else 0.0))


def complete_structure(meals: list[ProposedMeal], cases: tuple[RetrievedCase, ...], envelope: PlausibilityEnvelope | None, catalog: dict[int, Food],
                       top_up: bool = True, profile: ClientProfile | None = None,
                       mode: RestrictionMode = RestrictionMode.STRICT) -> tuple[list[ProposedMeal], list[CompletionChange]]:
    """Completes the structure of each slot from the retrieved cases: the missing required groups first, then a top-up to the
    minimum number of foods he writes for that slot.

    `profile` is not optional in spirit. This function ADDS food, and a function that adds food must know what the client may
    not eat: without it the completion could put bread into a coeliac's breakfast and rely on the validator running afterwards
    to take it out again — which works only for as long as nobody reorders the pipeline and is already false for the
    `plausible_unvalidated` variant of the harness, where no validator runs. The restriction is checked HERE, at the point of
    choice, so a forbidden food is never a candidate rather than being repaired downstream (2.E: hard restrictions are the one
    thing in this system that is never calibrated)."""
    allowed = (lambda fid: fid in catalog and not veto_reasons(catalog[fid], profile, mode)) if profile is not None else (lambda fid: True)
    support = _support_by_slot(cases, catalog)
    changes: list[CompletionChange] = []
    out: list[ProposedMeal] = []
    for m in meals:
        with_slot = sum(1 for c in cases if c.diet.meal(m.slot) is not None) or len(cases) or 1
        present_foods = {o.item.food_id for o in m.items if o.item.food_id is not None}
        present_groups: set[FoodGroup] = set()
        for f in present_foods:
            if f in catalog:
                present_groups |= _groups(catalog[f])
        floor = min(MIN_CASE_SUPPORT, len(cases))          # a candidate backed by ONE case is that client's choice, not evidence
        ranked = sorted(((fid, s) for fid, s in support.get(m.slot, {}).items()
                         if fid not in present_foods and allowed(fid) and len(s[0]) >= floor),
                        key=lambda t: (-len(t[1][0]), t[0]))
        groups = list(m.groups)
        # (a) required groups of the slot
        for g in sorted(REQUIRED_GROUPS.get(m.slot, frozenset()) - present_groups, key=lambda x: x.value):
            cand = next(((fid, s) for fid, s in ranked if g in _groups(catalog[fid])), None)
            if cand is None:
                continue
            fid, s = cand
            groups.append(AlternativeGroup(len(groups), (_new_item(m.slot, len(groups), catalog[fid], s, with_slot),)))
            present_foods.add(fid); present_groups |= _groups(catalog[fid])
            ranked = [t for t in ranked if t[0] != fid]
            changes.append(CompletionChange("added_required_group", m.slot.value, fid, catalog[fid].canonical_name,
                                            f"grupo {g.value} exigido en la franja; añadido el alimento del grupo con más soporte ({len(s[0])} de {with_slot} casos)"))
        # (b) top up to the professional's minimum for the slot
        band = envelope.items_per_slot.get(m.slot) if envelope else None
        if top_up and band:
            while len(present_foods) < band[0] and ranked:
                fid, s = ranked.pop(0)
                groups.append(AlternativeGroup(len(groups), (_new_item(m.slot, len(groups), catalog[fid], s, with_slot),)))
                present_foods.add(fid)
                changes.append(CompletionChange("topped_up", m.slot.value, fid, catalog[fid].canonical_name,
                                                f"la franja tenía menos alimentos que el mínimo del profesional (p05 = {_fmt(band[0])}); añadido el siguiente por soporte ({len(s[0])} de {with_slot} casos)"))
        out.append(replace(m, groups=tuple(groups)))
    return out, changes


def normalize_quantities(meals: list[ProposedMeal], envelope: PlausibilityEnvelope, catalog: dict[int, Food]) -> tuple[list[ProposedMeal], list[CompletionChange]]:
    changes: list[CompletionChange] = []
    out: list[ProposedMeal] = []
    for m in meals:
        groups = []
        for g in m.groups:
            options = []
            for o in g.options:
                it = o.item
                if it.inherited and it.quantity.value is not None:
                    # THE INVARIANT (A2 of the expert review): a value the professional wrote for THIS client is never
                    # overwritten with a statistic of the corpus. Four of the branches below would do it — substitute the
                    # unit, clamp the quantity, drop it, or impose the curated ration — and one of them turned his
                    # «2 hamburguesas de pollo (290 gr aprox.)» into «160 gr Hamburguesa», the median of a different role.
                    # The envelope bounds what the system INVENTS; it does not correct what it INHERITS.
                    #
                    # It forbids OVERWRITING a value of his, not SUPPLYING one he never gave: an inherited item with no
                    # quantity at all has nothing to protect, and «1 Batido de proteínas» with no grams anywhere is the
                    # defect the professional opened this review with.
                    options.append(o); continue
                # (0) his ration, for the foods that must never be written as a bare count. A protein shake without grams and
                # a «1 pasas» are the same defect: the number does not describe the portion. Both lists are mined and curated
                # (`pipeline/data/portion_units.json`); this runs BEFORE the band checks because those need n >= 10 per
                # (food, unit) and several of these foods have fewer gram observations than that.
                # The name has to come from the CATALOGUE, not from the item: an item inherited by the rotation from the
                # client's previous version arrives with `canonical_name` unset — it is filled in at the REST boundary, far
                # downstream of here — so looking the portion up by the item's own name silently missed every rotated diet.
                food = catalog.get(it.food_id)
                name = it.canonical_name or (food.canonical_name if food else None)
                portion = envelope.gram_portion(name) if envelope else None
                if portion is not None and it.quantity.unit is Unit.GRAM and it.quantity.value is not None:
                    # Already in grams and this food is one of the curated ones: the gram IS its unit and nothing below may
                    # trade it away. The envelope has no gram band for these foods — that is precisely why they are curated,
                    # they have fewer than its n >= 10 gram observations — so the unit-substitution branch would look at the
                    # units it DOES know and turn «30 gr Caseína» back into «1 Caseína», undoing the fix from the other side.
                    options.append(o); continue
                if portion is not None and (it.quantity.value is None or it.quantity.unit is Unit.PIECE):
                    new_q = on_his_grid(Quantity(portion, Unit.GRAM))
                    options.append(ProposedItem(replace(it, quantity=new_q,
                                                        raw_text=f"{_fmt(new_q.value)} g {name}".strip()), o.evidence))
                    changes.append(CompletionChange("portion_in_grams", m.slot.value, it.food_id, name,
                                                    f"«{name}» no se prescribe por unidades; escrito con su ración habitual "
                                                    f"{_fmt(new_q.value)} g"))
                    continue
                if it.quantity.value is None and envelope is not None:
                    ration = envelope.supplement_ration(name)     # §2: a supplement he doses always carries his dose
                    if ration is not None:
                        q = on_his_grid(Quantity(ration[0], Unit(ration[1])))
                        options.append(ProposedItem(replace(it, quantity=q,
                                                            raw_text=f"{_fmt(q.value)} {ration[1]} {name}".strip()), o.evidence))
                        changes.append(CompletionChange("supplement_ration", m.slot.value, it.food_id, name,
                                                        f"«{name}» sin cantidad; escrita su dosis habitual {_fmt(q.value)} {ration[1]}"))
                        continue
                if it.food_id is None or it.quantity.value is None:
                    options.append(o); continue
                band = envelope.quantities.get((it.food_id, it.quantity.unit.value))
                if band is None:
                    seen = [envelope.quantities[(it.food_id, u)] for u in envelope.units_of(it.food_id)]
                    if seen:
                        best = max(seen, key=lambda b: b.n)
                        new_q = on_his_grid(Quantity(best.p50, Unit(best.unit)))
                        options.append(ProposedItem(replace(it, quantity=new_q, raw_text=f"{_fmt(new_q.value)} {best.unit} {it.canonical_name}".strip()), o.evidence))
                        changes.append(CompletionChange("unit_replaced", m.slot.value, it.food_id, it.canonical_name,
                                                        f"unidad «{it.quantity.unit.value}» no observada para el alimento; sustituida por {_fmt(best.p50)} {best.unit} (mediana del profesional, n={best.n})"))
                        continue
                    if it.quantity.unit in FOOD_SPECIFIC_UNITS:            # no envelope at all and a unit that belongs to another kind of food («3 dientes de sacarina»): drop the amount
                        options.append(ProposedItem(replace(it, quantity=Quantity(None), raw_text=it.canonical_name or it.raw_text), o.evidence))
                        changes.append(CompletionChange("quantity_dropped", m.slot.value, it.food_id, it.canonical_name,
                                                        f"unidad «{it.quantity.unit.value}» heredada de la especie sustituida y sin observaciones del profesional para este alimento; se deja sin cantidad"))
                        continue
                    options.append(o); continue
                v = float(it.quantity.value)
                if band.contains(v):
                    options.append(o); continue
                new_q = on_his_grid(Quantity(band.p05 if v < band.p05 else band.p95, it.quantity.unit))
                new_v = new_q.value
                options.append(ProposedItem(replace(it, quantity=new_q, raw_text=f"{_fmt(new_v)} {band.unit} {it.canonical_name}".strip()), o.evidence))
                changes.append(CompletionChange("quantity_clamped", m.slot.value, it.food_id, it.canonical_name,
                                                f"{_fmt(v)} {band.unit} fuera de [{_fmt(band.p05)}, {_fmt(band.p95)}] {band.unit} (n={band.n}); ajustado a {_fmt(new_v)} {band.unit}"))
            groups.append(replace(g, options=tuple(options)))
        out.append(replace(m, groups=tuple(groups)))
    return out, changes


def name_variants(meals: list[ProposedMeal], envelope: PlausibilityEnvelope | None,
                  cases: tuple[RetrievedCase, ...] = ()) -> list[ProposedMeal]:
    """Write the component the way HE writes it when his wording is more specific than the catalogue's canonical (§3).

    The catalogue collapses «Arroz vaporizado», «Arroz integral» and «Arroz blanco» into `arroz`; he writes a specific rice
    75,8 % of the times he writes rice, and the composer could only ever say «Arroz». Regenerating the catalogue would cost the
    dataset, the embeddings and every published figure, but the distinction survives in `normalized_key` — which the composer
    already consensuses over the retrieved cases — so it only has to reach the page. Nothing but the printed name changes:
    `food_id` and `canonical_name` stay as they were, and the engine is none the wiser."""
    if envelope is None or not envelope.food_variants:
        return meals
    # What the RETRIEVED CASES say, not what the item happens to carry. The composer keeps the modal `normalized_key` of the
    # neighbours, and for rice the modal key is the bare «arroz» even when several neighbours wrote «Arroz integral»: one of
    # the three rices of a diet came out specific and the other two did not. The variant with the most support among the
    # cases wins, and it needs at least MIN_CASE_SUPPORT of them, like every other consensus in this system.
    votes: dict[int, Counter] = defaultdict(Counter)
    for c in cases:
        for meal in c.diet.meals:
            for it in meal.items:
                text = envelope.variant_text(it.normalized_key)
                if text and it.food_id is not None:
                    votes[it.food_id][text] += 1
    out = []
    for m in meals:
        groups = []
        for g in m.groups:
            options = []
            for o in g.options:
                text = envelope.variant_text(o.item.normalized_key)
                if not text and o.item.food_id in votes:
                    best, n = votes[o.item.food_id].most_common(1)[0]
                    text = best if n >= MIN_CASE_SUPPORT else None
                options.append(ProposedItem(replace(o.item, display_name=text), o.evidence) if text else o)
            groups.append(replace(g, options=tuple(options)))
        out.append(replace(m, groups=tuple(groups)))
    return out



def split_mixed_groups(meals: list[ProposedMeal], catalog: dict[int, Food]) -> tuple[list[ProposedMeal], list[CompletionChange]]:
    """Un grupo de alternativas cuyos miembros no comparten papel se PARTE en grupos por papel.

    Ofrecer «280 gr Pollo / 2 Hamburguesa / 180 gr Tomate» como si fueran intercambiables es el defecto que el
    profesional señaló dos veces (§4b y §4c): una alternativa suya sustituye una cosa por otra que hace lo mismo en
    el plato, y un tomate no sustituye a un pollo. Aparecen sobre todo por la rotación, que cambia la especie dentro
    del grupo sin comprobar el macrogrupo del resultado.

    Partir en vez de descartar: no se pierde ningún alimento —siguen todos en la franja, en grupos separados— y la
    dieta deja de proponer un intercambio que él no firma. El papel es el grupo PRIMARIO del alimento, el mismo
    criterio que `fruta_no_en_cena` usa para no confundir la botánica con la función.
    """
    out, changes = [], []
    for m in meals:
        nuevos = []
        for g in m.groups:
            por_papel: dict[str, list] = {}
            for o in g.options:
                f = catalog.get(o.item.food_id)
                papel = f.group.value if f is not None else "?"
                por_papel.setdefault(papel, []).append(o)
            if len(por_papel) <= 1:
                nuevos.append(g)
                continue
            nombres = sorted({(catalog[o.item.food_id].canonical_name if catalog.get(o.item.food_id) else "?")
                              for o in g.options})
            changes.append(CompletionChange("grupo_mixto_partido", m.slot.value, None, None,
                                            f"grupo con papeles {sorted(por_papel)} partido en {len(por_papel)}: {nombres}"))
            for papel in sorted(por_papel):
                nuevos.append(replace(g, options=tuple(por_papel[papel])))
        out.append(replace(m, groups=tuple(replace(g, position=i) for i, g in enumerate(nuevos))))
    return out, changes



_PARENTETICO = re.compile(r"\(([^)]{3,60})\)")


def preserve_parentheticals(meals: list[ProposedMeal], cases: tuple[RetrievedCase, ...] = ()) -> list[ProposedMeal]:
    """Conserva el paréntesis con el que ÉL matiza un alimento: «(2 o 3 rebanadas)», «(cualquier parte a la plancha
    o asada)», «(290 gr aprox.)», «(omega 3 si no tienes)».

    El 20,9 % de los componentes del corpus llevan uno, y son instrucciones de verdad: cómo cocinarlo, cuánto es en
    la práctica, con qué sustituirlo. El compositor los perdía porque consensúa sobre `normalized_key`, que no los
    lleva. Mismo mecanismo que el tipo de arroz —el texto viaja en `display_name` y ni `food_id` ni `canonical_name`
    cambian— y mismo suelo de consenso: el matiz tiene que aparecer en al menos MIN_CASE_SUPPORT vecinos para no
    copiar la coletilla de un cliente suelto.
    """
    votos: dict[int, Counter] = defaultdict(Counter)
    for c in cases:
        for meal in c.diet.meals:
            for it in meal.items:
                m = _PARENTETICO.search(it.raw_text or "")
                if m and it.food_id is not None:
                    votos[it.food_id][m.group(1).strip()] += 1
    out = []
    for meal in meals:
        grupos = []
        for g in meal.groups:
            opciones = []
            for o in g.options:
                c = votos.get(o.item.food_id)
                mejor = c.most_common(1)[0] if c else None
                if mejor and mejor[1] >= MIN_CASE_SUPPORT and "(" not in (o.item.display_name or ""):
                    base = o.item.display_name or o.item.canonical_name or o.item.normalized_key or ""
                    opciones.append(replace(o, item=replace(o.item, display_name=f"{base} ({mejor[0]})")))
                else:
                    opciones.append(o)
            grupos.append(replace(g, options=tuple(opciones)))
        out.append(replace(meal, groups=tuple(grupos)))
    return out


def harmonise_rations(meals: list[ProposedMeal], envelope: PlausibilityEnvelope | None, catalog: dict[int, Food]) -> tuple[list[ProposedMeal], list[CompletionChange]]:
    """Make the rations of one slot commensurate with each other (§5 of the expert review).

    Every quantity is sampled food by food, and nobody looks at how they read TOGETHER. The professional put it plainly:
    «no tiene sentido que pollo y ternera sean 280 gr y hamburguesa solo 160». Taken alone, 160 g of burger is a perfectly
    ordinary quantity and sits inside the plausibility envelope; what is wrong is the RELATION.

    The proxy is his own: two foods of the same macrogroup in the same slot should keep a ratio compatible with the ratio of
    their corpus medians. Measured over his diets, that ratio (observed / predicted) has a band per macrogroup — PROTEIN
    [0,56, 1,67] over 5.144 pairs, CARB [0,45, 2,67], VEGETABLE [0,42, 2,19] — and the tolerance comes from there, not from a
    guess. The anchor of each slot is the food with the strongest corpus evidence; the others are moved onto the predicted
    ratio only when they fall OUTSIDE the band.

    Declared, because it is the honest reading of his own example: the burger he complained about scores 0,71 against a
    PROTEIN band that starts at 0,56, so **this rule does not flag it**. His 360 g would score 1,61, also inside. Both are
    quantities he himself writes; what he was applying is knowledge the corpus does not encode.
    """
    if envelope is None or not envelope.gram_medians or not envelope.ration_bands:
        return meals, []
    med, bands = envelope.gram_medians, envelope.ration_bands
    changes: list[CompletionChange] = []
    out: list[ProposedMeal] = []
    for m in meals:
        # the leading option of each group is the one that carries the ration; alternatives follow their own leader
        rows = []
        for gi, g in enumerate(m.groups):
            for oi, o in enumerate(g.options):
                it = o.item
                f = catalog.get(it.food_id)
                if f is None or it.quantity.unit is not Unit.GRAM or it.quantity.value is None or it.inherited:
                    continue                    # the invariant: an inherited ration is his and is not moved onto a ratio
                name = it.canonical_name or f.canonical_name
                if name in med:
                    rows.append((gi, oi, f.group.value, name, float(it.quantity.value)))
        by_group: dict[str, list] = {}
        for r in rows:
            by_group.setdefault(r[2], []).append(r)
        moved: dict[tuple[int, int], float] = {}
        for gname, rs in by_group.items():
            band = bands.get(gname)
            if band is None or len(rs) < 2:
                continue
            anchor = max(rs, key=lambda r: med[r[3]])          # the largest typical ration is the reference of the slot
            lo, hi = band
            for gi, oi, _, name, value in rs:
                if (gi, oi) == (anchor[0], anchor[1]):
                    continue
                predicted = med[name] / med[anchor[3]]
                observed = value / anchor[4]
                ratio = observed / predicted if predicted else 1.0
                if lo <= ratio <= hi:
                    continue
                # This pass runs AFTER the band pass, so it is the only thing that could push a quantity back out of his
                # own [p05, p95]; the harmonised value is clamped into it before being written.
                # Two measurements of his practice can disagree: the ration ratio says one thing and the [p05, p95] band of
                # that single food says another (chía sits at 15 g in its band while its ratio against nueces asks for 4).
                # The ratio wins here — it is what the reader of the sheet sees — and the conformance check exempts the case
                # instead, because there is no value that satisfies both and it is not a defect the system can remove.
                target = on_his_grid(Quantity(anchor[4] * predicted, Unit.GRAM))
                if target.value and abs(target.value - value) >= 5:
                    moved[(gi, oi)] = target.value
                    changes.append(CompletionChange(
                        "ration_harmonised", m.slot.value, None, name,
                        f"{_fmt(value)} g junto a {_fmt(anchor[4])} g de {anchor[3]} da una razón {ratio:.2f} fuera de "
                        f"[{lo:.2f}, {hi:.2f}] del macrogrupo {gname}; ajustado a {_fmt(target.value)} g "
                        f"(la razón de sus medianas: {predicted:.2f})"))
        if not moved:
            out.append(m); continue
        groups = []
        for gi, g in enumerate(m.groups):
            options = []
            for oi, o in enumerate(g.options):
                v = moved.get((gi, oi))
                if v is None:
                    options.append(o); continue
                it = o.item
                options.append(ProposedItem(replace(it, quantity=Quantity(v, Unit.GRAM),
                                                    raw_text=f"{_fmt(v)} g {it.canonical_name}".strip()), o.evidence))
            groups.append(replace(g, options=tuple(options)))
        out.append(replace(m, groups=tuple(groups)))
    return out, changes
