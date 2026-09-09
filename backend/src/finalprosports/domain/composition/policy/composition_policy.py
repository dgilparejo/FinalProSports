"""Case-based composition (E4.2): a diet composed by consensus over the k retrieved cases.

Reproduces the professional's structure instead of picking one food per position:
  - a slot is included when it appears in at least `slot_threshold` of the k cases;
  - inside a slot, a food is included when it appears in at least `inclusion_threshold` of the cases that have the slot
    (support); the threshold is what controls the size of the proposal (precision / recall trade-off);
  - foods that the professional writes as alternatives of each other («150 gr Pollo / 160 gr Pavo / 180 gr Lomo») are
    grouped into AlternativeGroups of up to `max_alternatives` options, in order of support;
  - quantities are medians within the (food, unit) pair, keeping the most frequent unit (quantity_policy);
  - the notes block is composed from the notes of the cases: notes shared by at least `note_threshold` of the cases, topped
    up to `min_notes` with the most frequent ones so that the note-level rules are evaluable and the diet is complete.
Evidence (case ids, support) travels with every item; the rules backing it are attached by rule_support.
Pure functions over domain objects; no I/O.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from finalprosports.domain.composition.policy.note_catalogue import NoteCatalogue
from finalprosports.domain.composition.policy.quantity_policy import median_quantity
from finalprosports.domain.model import AlternativeGroup, DietItem, Food, ItemEvidence, MealSlot, ProposedItem, ProposedMeal, RetrievedCase

SLOT_ORDER = tuple(MealSlot)
# The ones a person reads as meals; the repeat penalty is about them. MEDIA TARDE joins them (dataset-v3: it is
# an afternoon meal, and until v3 its content was being counted inside MERIENDA anyway). SUPLEMENTOS, AGUA and
# RECIEN LEVANTADO stay out: they are intake occasions, not meals, like the training slots.
MAIN_SLOTS = frozenset({MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.BRUNCH, MealSlot.LUNCH, MealSlot.SNACK,
                        MealSlot.MID_AFTERNOON, MealSlot.DINNER, MealSlot.LATE_SNACK})

# OTHER is a BUCKET, not a slot, and it is never composed into a proposal.
#
# It holds whatever header shape the vocabulary could not map (528 distinct ones), so its contents are heterogeneous
# BETWEEN cases in a way no real slot is: two neighbours' OTHER have nothing in common except that both were
# unrecognised. Consensus over that produced exactly what you would expect -- 24 distinct foods in a single OTHER,
# and one golden profile whose entire proposal was a single OTHER slot. The bucket stays in the DATA, with its
# `raw_slot_label`, because nothing is thrown away; it simply cannot be proposed inside. It is excluded from the
# metrics for the same reason (see loo_harness.SCORED_SLOTS): scoring a system against something it is not allowed
# to produce measures nothing.
NON_COMPOSABLE_SLOTS = frozenset({MealSlot.OTHER})

# Condimentos que él NUNCA escribe como línea propia de una comida. Medido sobre el corpus: `edulcorante` y
# `perejil` suman 110 apariciones y solo 3 de ellas son una línea suya —el resto van dentro de la línea de otro
# alimento—, así que proponerlos como componente es inventarle una conducta. No es una lista de condimentos: `ajo`
# (172 líneas propias) y `cúrcuma` (80) sí los escribe solos y siguen siendo proponibles.
NEVER_ON_THEIR_OWN = frozenset({"edulcorante", "perejil"})

MIN_CASE_SUPPORT = 2
"""The absolute floor under every threshold expressed as a share of k.

A share is not evidence when k is small: with two retrieved cases, `count / k >= 0,35` is satisfied by ONE client, and the
composer then presents that client's private choice as a consensus. It had already bitten twice — the note block, fixed with
`MIN_NOTE_SUPPORT`, and the alternative groups, which offered «multivitamínico / electrolitos» as interchangeable on the
strength of a pairing that appears ONCE in the whole corpus. A sweep of every fractional threshold found seven; two were
already guarded (this one for notes, `RotationParams.min_n = 10` for the rotation anchors) and five were not: the slot
threshold, the food inclusion threshold, the compound link, the alternative link and the candidate ranking of the structural
completion. They all take this floor now.

It is capped by k so the declared `copy_top1` degradation still works: copying the single nearest case is a fallback the
evaluation measures, not an accident, and there a support of one is all there is."""


@dataclass(frozen=True)
class CompositionParams:
    k: int = 8
    inclusion_threshold: float = 0.4      # share of the cases having the slot that contain the food
    slot_threshold: float | None = None   # share of the k cases having the slot (defaults to inclusion_threshold)
    max_alternatives: int = 4
    """The p90 of his own groups, and the average of the largest group of a diet (4,07).

    It was raised to the p95 (5) to stop truncating his wider groups, and the professional read a dinner with five proteins
    on one line and said so. The p90 is the honest ceiling: it covers the group he usually writes without printing the tail."""
    note_threshold: float | None = None   # share of the k cases sharing a note (defaults to inclusion_threshold)
    min_notes: int = 3
    alternative_link: float = 0.5         # a food joins a group when it is written as an alternative of its leader in >= this share of its cases
    compound_link: float = 0.5            # two foods are emitted as ONE component («2 huevos con 3 claras») when he writes them compounded in >= this share of the cases that carry both
    similarity_weighting: float = 0.0     # 0 = every retrieved case counts the same; >0 = a case's vote is its similarity raised to this power (see _weights)
    repeat_penalty: float = 0.20
    """Extra support a food must have to be placed AGAIN in a later main slot of the same diet.

    A consensus picks the same high-support foods in every slot, so the composer repeated a food between two main slots in
    100 % of its proposals against his 88,6 %, and put two or more of them in lunch AND dinner in 84,3 % against his 63,0 %.
    He repeats — the reader of the sheet sees `arroz + pollo` twice in 287 of his diets — so the target is HIS RATE and never
    zero. Swept against it rather than chosen: 0 gives 82,7 %, 0,15 gives 66,6 %, **0,20 gives 61,9 % against his 63,0 %**,
    and 0,50 would give 35,6 %, which is as wrong as the excess was. The overlap costs 0,0001 of J `normalized_key`.

    It is deliberately calibrated on the lunch/dinner pair, which is what he complained about and what a person reads. The
    looser reading — any food shared by any two main slots — stays at 99 % against his 88,6 %: closing that one needs a
    penalty of 1,0, which drags the lunch/dinner rate down to 13,5 %. The two cannot be satisfied at once and this is the
    one he named."""
    degradation: str = "copy_top1"        # E5.6, when not every retrieved case shares the goal: 'none' | 'reduce_k' | 'copy_top1' (measured: copy 0,349 > reduce_k 0,329 > none 0,327 on the 23 minority queries)
    min_cases_to_compose: int = 3         # reduce_k only: below this many same-goal cases it falls back to copy_top1

    @property
    def slot_t(self) -> float:
        return self.inclusion_threshold if self.slot_threshold is None else self.slot_threshold

    @property
    def note_t(self) -> float:
        return self.inclusion_threshold if self.note_threshold is None else self.note_threshold

    def as_dict(self) -> dict:
        return {"k": self.k, "inclusion_threshold": self.inclusion_threshold, "slot_threshold": self.slot_t, "max_alternatives": self.max_alternatives,
                "note_threshold": self.note_t, "min_notes": self.min_notes, "alternative_link": self.alternative_link, "compound_link": self.compound_link,
                "degradation": self.degradation, "min_cases_to_compose": self.min_cases_to_compose,
                "similarity_weighting": self.similarity_weighting, "repeat_penalty": self.repeat_penalty}


def _quantity_text(item: DietItem) -> str:
    q = item.quantity
    if q.value is None:
        return item.canonical_name or item.normalized_key
    v = int(q.value) if float(q.value).is_integer() else q.value
    return f"{v} {q.unit.value} {item.canonical_name}".strip() if q.unit.value else f"{v} {item.canonical_name}"


def _weights(cases: list[RetrievedCase], power: float) -> dict[str, float]:
    """How much each retrieved case's vote is worth.

    With `power = 0` every case counts the same, which is what a consensus over k neighbours means and what the published
    measurement used. That has a cost the aggregate metrics cannot see: on a rule he applies to some clients and not others,
    a flat vote over 20 neighbours reproduces his AVERAGE behaviour and not his decision for THIS client — measured, the
    system's per-case agreement with him (0,806) fell below the trivial baseline of always predicting his majority (0,831).
    With `power > 0` a case votes with its similarity to the query raised to that power, so the nearest cases decide and the
    consensus keeps some of the discrimination the retrieval had already found. Scores are rescaled to the best case in the
    set: the absolute scale of the similarity is arbitrary, only the ratio between neighbours carries information."""
    if power <= 0:
        return {c.diet.id: 1.0 for c in cases}
    best = max((c.score.total for c in cases), default=0.0) or 1.0
    return {c.diet.id: max(1e-6, (c.score.total / best)) ** power for c in cases}


def _compound_partition(groups_out: list[list[int]], co_comp: Counter, case_ids: dict[int, list[str]],
                        link: float, slot: MealSlot) -> dict[int, str]:
    """Which of the selected foods he writes JOINED on one line, and therefore must not be emitted as separate components.

    A compound is not an alternative: «2 huevos con 3 claras», «batido de proteínas con agua», «pepino y tomate» are single
    components of the meal that happen to name two foods. The corpus carries them as a shared `compound_group`, 3.865 of them
    over 1.012 of the 1.033 diets (98 %) — and the composer used to produce NONE, which was the single descriptor an external
    discriminator needed to tell a generated diet from a real one (AUC 0,999).

    Two foods are joined when he compounds them in at least `link` of the retrieved cases that carry BOTH — the same
    consensus rule the alternatives use. The 0,5 cut is not a guess: over the 499 pairs he compounds at least once and that
    appear together 10+ times, P(compounded | both in the slot) is bimodal — a mode of real compounds at 0,85-1,00 (clara +
    yema 1,00 over 606 slots, electrolitos + multivitamínico 1,00, agua + batido 0,86) and a long tail of mere co-occurrence
    with median 0,08 (maíz + pepino 0,48 is a salad, not a component). The cut sits between the two modes; 9 % of the pairs
    pass it. What a consensus cannot recover is his one-off compounds, so the composer reaches 2,05 groups per diet against
    his 3,82 — a declared limit, not a defect: an idiosyncratic compound has no support to be inferred from. Foods that are alternatives of each other are never joined: he writes «pollo o pavo»,
    not «pollo con pavo». Transitive by union-find, because a compound can name three («atún con clara y yema»)."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    same_line = {f for g in groups_out if len(g) > 1 for f in g}          # members of an alternative group: never compounded together
    flat = [f for g in groups_out for f in g]
    for i, a in enumerate(flat):
        for b in flat[i + 1:]:
            if a in same_line and b in same_line and any(a in g and b in g for g in groups_out):
                continue
            both = len(set(case_ids[a]) & set(case_ids[b]))
            if both and co_comp[(a, b)] >= max(min(MIN_CASE_SUPPORT, both), link * both):
                union(a, b)
    roots: Counter = Counter(find(f) for f in flat)
    out: dict[int, str] = {}
    for n, (root, size) in enumerate(sorted((r, c) for r, c in roots.items() if c > 1)):
        for f in flat:
            if find(f) == root:
                out[f] = f"{slot.value}-c{n}"
    return out


def compose_meals(cases: tuple[RetrievedCase, ...], params: CompositionParams, catalog: dict[int, Food],
                  interchangeable=None, liked: frozenset[int] = frozenset()) -> list[ProposedMeal]:
    """`interchangeable` is a predicate `(food_id, food_id) -> bool` over the pairs the professional himself writes as
    alternatives, mined corpus-wide. The local co-occurrence among the k cases is not enough on its own: it offered
    «multivitamínico / electrolitos» as interchangeable on a pairing that appears ONCE in 1.033 diets. The rotation
    already used this criterion for substitution; the composition of alternative groups uses it too."""
    cases = cases[: params.k]
    k = len(cases)                                          # effective k = min(params.k, cases available)
    if k == 0:
        return []
    meals: list[ProposedMeal] = []
    placed_main: set[int] = set()                 # foods already written in an earlier MAIN slot of this diet
    for slot in SLOT_ORDER:
        if slot in NON_COMPOSABLE_SLOTS:
            continue
        with_slot = [c for c in cases if c.diet.meal(slot) is not None]
        if len(with_slot) / k < params.slot_t or len(with_slot) < min(MIN_CASE_SUPPORT, k):
            continue
        n = len(with_slot)
        w = _weights(with_slot, params.similarity_weighting)          # a case's vote; uniform unless the parameter says otherwise
        total_w = sum(w.values()) or 1.0
        case_ids: dict[int, list[str]] = defaultdict(list)
        weight_of: dict[int, float] = defaultdict(float)
        quantities: dict[int, list] = defaultdict(list)
        keys: dict[int, Counter] = defaultdict(Counter)
        co_alt: Counter = Counter()
        co_comp: Counter = Counter()                        # same-component co-occurrence: what he writes joined on ONE line
        for c in with_slot:
            meal = c.diet.meal(slot)
            seen_here = set()
            groups: dict[str, set[int]] = defaultdict(set)
            compounds: dict[str, set[int]] = defaultdict(set)
            for it in meal.items:
                if it.food_id is None or it.food_id not in catalog:
                    continue
                if it.food_id not in seen_here:
                    case_ids[it.food_id].append(c.diet.id); seen_here.add(it.food_id)
                    weight_of[it.food_id] += w[c.diet.id]
                quantities[it.food_id].append(it.quantity)
                keys[it.food_id][it.normalized_key] += 1
                if it.alternative_group:                                 # what he WROTE as alternatives («pollo / pavo»)
                    groups[it.alternative_group].add(it.food_id)
                if it.compound_group:                                    # what he WROTE joined on one line («2 huevos con 3 claras»)
                    compounds[it.compound_group].add(it.food_id)
            for members in groups.values():
                for a in members:
                    for b in members:
                        if a != b:
                            co_alt[(a, b)] += 1
            for members in compounds.values():
                for a in members:
                    for b in members:
                        if a != b:
                            co_comp[(a, b)] += 1
        support = {f: (weight_of[f] / total_w if params.similarity_weighting else len(ids) / n) for f, ids in case_ids.items()}
        floor = min(MIN_CASE_SUPPORT, n)
        need = lambda f: params.inclusion_threshold * (1 + (params.repeat_penalty if f in placed_main else 0.0))  # noqa: E731
        selected = [f for f in case_ids if support[f] >= need(f) and len(case_ids[f]) >= floor
                    and (catalog.get(f) is None or catalog[f].canonical_name not in NEVER_ON_THEIR_OWN)]
        # EL DESEMPATE POR GUSTOS (bloque 8.2b). `selected` ya contiene SOLO alimentos que superaron el umbral de
        # soporte entre los casos recuperados, asi que esta clave no puede introducir nada: reordena lo que el
        # consenso ya habia propuesto. Entra DESPUES del soporte y del numero de casos, y antes del desempate
        # arbitrario por id: solo decide cuando los dos candidatos estaban empatados de verdad.
        #
        # Se activa porque esta medido que EL lo hace: los alimentos que un cliente declara aparecen en sus dietas
        # +0,0643 [+0,0120, +0,1211] por encima de la tasa base del mismo alimento en el mismo objetivo, con el
        # control negativo saliendo en -0,0612 [-0,1093, -0,0110].
        selected.sort(key=lambda f: (-support[f], -len(case_ids[f]), 0 if f in liked else 1, f))
        def same_role(a: int, b: int) -> bool:
            """Two foods are alternatives only if they play the SAME ROLE in the meal — they share a macrogroup.

            The quantity-ratio criterion cannot see this one: «160 gr Arroz integral / 150 gr Espinacas / 160 gr Espárragos /
            130 gr Boniato» offers leaf vegetable as interchangeable with starch and every quantity is around 150 g, so the
            ratio check passes. What separates them is what they DO in the meal. The rotation already substituted on this
            criterion; the composition of the groups did not, and it is where the group is born."""
            fa, fb = catalog.get(a), catalog.get(b)
            if fa is None or fb is None:
                return False
            ma = {fa.group} | ({fa.secondary_group} if getattr(fa, "secondary_group", None) else set())
            mb = {fb.group} | ({fb.secondary_group} if getattr(fb, "secondary_group", None) else set())
            return bool(ma & mb)

        groups_out: list[list[int]] = []
        for f in selected:
            placed = False
            for g in groups_out:
                leader = g[0]
                if (len(g) < params.max_alternatives
                        and co_alt[(leader, f)] >= max(min(MIN_CASE_SUPPORT, n), params.alternative_link * len(case_ids[f]))
                        and same_role(leader, f)
                        and (interchangeable is None or interchangeable(leader, f))):
                    g.append(f); placed = True
                    break
            if not placed:
                groups_out.append([f])
        compound_of = _compound_partition(groups_out, co_comp, case_ids, params.compound_link, slot)
        alt_groups = []
        for pos, g in enumerate(groups_out):
            options = []
            for ci, f in enumerate(g):
                food = catalog[f]
                item = DietItem(meal_slot=slot, position=pos, component_index=ci, food_id=f, canonical_name=food.canonical_name,
                                normalized_key=keys[f].most_common(1)[0][0], raw_text="", quantity=median_quantity(quantities[f]),
                                compound_group=compound_of.get(f),
                                alternative_group=f"{slot.value}-{pos}" if len(g) > 1 else None)
                item = DietItem(**{**item.__dict__, "raw_text": _quantity_text(item)})
                options.append(ProposedItem(item, ItemEvidence(tuple(case_ids[f]), round(support[f], 4))))
            alt_groups.append(AlternativeGroup(pos, tuple(options)))
        if alt_groups:
            meals.append(ProposedMeal(slot, tuple(alt_groups)))
            if slot in MAIN_SLOTS:
                placed_main.update(f for g in groups_out for f in g)
    return meals


_WS = re.compile(r"\s+")


def _norm(note: str) -> str:
    return _WS.sub(" ", note.strip()).lower()


MIN_NOTE_SUPPORT = 2      # a note is emitted only if at least two of the retrieved clients wrote it.
"""The floor under the min_notes fallback: never put one client's sentence into another client's diet.

A note is always emitted as some neighbour's literal wording — there is no paraphrase step — so a line only one of the k
clients wrote would be that person's own sentence, copied verbatim into a stranger's document. A line two or more of them
wrote independently is the professional's boilerplate, which is what the composer is supposed to be reproducing. The floor is absolute, not
relative: with few retrieved cases the share test `count / k >= note_t` is satisfied by a single client, so it cannot be the
only guard. Measured before the floor existed: 3.1 % of emitted notes (70 of 2,260 across 738 proposals) came from one neighbour."""


def compose_notes(cases: tuple[RetrievedCase, ...], params: CompositionParams,
                  catalogue: "NoteCatalogue | None" = None) -> list[str]:
    """The notes block of the proposal, by consensus over the retrieved cases.

    Two passes, in this order:
      1. **by theme** (when a catalogue is available). A theme is one instruction of his recognised in any of his wordings;
         its support is the share of cases carrying it, and what is emitted is the theme's canonical text. This is the pass
         that matters: consensus over literal strings cannot see an instruction he writes 396 different ways, and measured
         over the whole corpus NOT ONE note string reaches `note_t`.
      2. **by literal string**, for whatever the catalogue does not cover, exactly as before and under the same
         `MIN_NOTE_SUPPORT` floor, topped up to `min_notes`.
    Section headers and footer fragments are dropped in both passes: they are not instructions.
    Order follows support, so the block reads with his most constant instructions first."""
    cases = cases[: params.k]
    k = len(cases)
    if k == 0:
        return []
    is_artefact = catalogue.is_artefact if catalogue else (lambda _t: False)

    theme_count: Counter = Counter()
    theme_rank: dict[str, int] = {}
    first_seen: dict[str, str] = {}
    count: Counter = Counter()
    best_rank: dict[str, int] = {}
    for c in cases:
        seen: set[str] = set()
        themes_here: set[str] = set()
        for note in c.diet.notes:
            n = _norm(note)
            if not n or n in seen or is_artefact(n):
                continue
            seen.add(n)
            hits = catalogue.themes_in(n) if catalogue else frozenset()
            themes_here |= hits
            if not hits:                                        # only the uncovered remainder competes as literal text
                count[n] += 1
                first_seen.setdefault(n, note.strip())
                best_rank[n] = min(best_rank.get(n, c.rank), c.rank)
        for t in themes_here:
            theme_count[t] += 1
            theme_rank[t] = min(theme_rank.get(t, c.rank), c.rank)

    out: list[str] = []
    emitted: set[str] = set()                                   # a canonical text can serve two themes: emit it once
    for t in sorted(theme_count, key=lambda t: (-theme_count[t], theme_rank[t], t)):
        if theme_count[t] / k < params.note_t or theme_count[t] < MIN_NOTE_SUPPORT:
            continue
        text = catalogue.canonical_of(t) if catalogue else None
        if text and _norm(text) not in emitted:
            out.append(text); emitted.add(_norm(text))

    ranked = sorted(count, key=lambda n: (-count[n], best_rank[n], n))
    literal = [n for n in ranked if count[n] / k >= params.note_t and count[n] >= MIN_NOTE_SUPPORT]
    for n in ranked:
        if len(out) + len(literal) >= params.min_notes:
            break
        if n not in literal and count[n] >= MIN_NOTE_SUPPORT:
            literal.append(n)
    for n in literal:
        if _norm(first_seen[n]) not in emitted:
            out.append(first_seen[n]); emitted.add(_norm(first_seen[n]))
    return out
