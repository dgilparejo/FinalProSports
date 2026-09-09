# -*- coding: utf-8 -*-
"""Conformance of a GENERATED diet against the professional's sixteen review observations.

Why this exists, and why it is the deliverable rather than the fixes it drives. The first round of this work was verified
with corpus statistics and with good lines found in the exported PDF, and that is not verification: finding one
«160 gr Arroz integral» does not show that two bare «Arroz» are not sitting three lines above it — and they were. Every check
here is an assertion **over the artefact**, and every failure names the offending line, so a defect cannot hide behind an
aggregate that looks healthy.

Every threshold comes from his own diets; none is chosen here. Where a check needs a number it reads it from the mined
artefacts (`plausibility_envelope.json`, `rotation_analysis.json`, `pipeline/data/portion_units.json`,
`pipeline/data/food_variants.json`), and the docstring of each check says which of his behaviours it encodes.

Run:  python -m finalprosports.infrastructure.adapter.inbound.eval.conformance [--sample 50] [--client <uuid>]
Out:  the list of infractions, grouped by check, and a summary table. Exit code 1 when anything is found.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
import dataclasses
from dataclasses import dataclass
from pathlib import Path

from finalprosports.domain.composition.factory.proposal_factory import to_diet
from finalprosports.domain.composition.policy.document_template_policy import SLOT_LABEL, TRAINING, item_text
from finalprosports.domain.model import DietProposal, FoodGroup, Goal, MealSlot, Unit
from finalprosports.domain.composition.policy.composition_policy import MIN_CASE_SUPPORT
from finalprosports.infrastructure.config.paths import repo_root

MAX_ALTERNATIVES = 4
"""His measured ceiling. The maximum group size of a diet averages 4,07 and the p90 of a single group is 4; the composer was
capped at 5 and printed a dinner with five proteins in one line, which is what prompted the observation."""

HIS_EMPTY_RATE = {MealSlot.POST_WORKOUT: 0.134, MealSlot.PRE_WORKOUT: 0.223, MealSlot.INTRA_WORKOUT: 0.349}
"""How often HE prints a training slot and leaves it empty, among his volume diets that declare it. Measured, because «no
poner nada es una errata» is his ideal and not his practice: he does it in 13,4 % of the post-workout slots he declares, and
writes «Nada» explicitly 46 times. The check reports the infraction and the rate together, so the comparison is visible."""

CONSECUTIVE = (MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.BRUNCH, MealSlot.LUNCH, MealSlot.SNACK,
               MealSlot.DINNER, MealSlot.LATE_SNACK)


VIOLATION, CALIBRATION = "violacion", "calibracion"
_HIDRA = re.compile(r"agua|hidrata", re.I)
# El contacto real del profesional NO va en el código: la auditoría de PII no admite excepciones por fichero.
CONTACT_PLACEHOLDER = "contacto@ejemplo / Tel: 000"
_LITROS = re.compile(r"litros?|\bml\b", re.I)
# Grupos de alternativas por dieta, medidos sobre el corpus v3 (1.203 dietas): media 7,08, mediana 7.
ALT_GROUPS_MEDIAN, ALT_GROUPS_P05, ALT_GROUPS_P95 = 7, 2, 12
NON_PRINTABLE_SLOTS = frozenset({MealSlot.OTHER})   # el cajón del extractor no es una franja suya
"""Two classes of check, and mixing them is how a review turns into over-correction.

A VIOLATION is a defect without nuance: emitting the family generic when a retrieved case wrote the variant, offering as
alternatives two foods he never writes as alternatives, overwriting a quantity he had written for THIS client. Target: zero.

A CALIBRATION is a behaviour he himself has at a rate that is neither 0 nor 1: he shares two or more foods between lunch and
dinner in 63,0 % of his diets, and leaves a declared pre-workout slot empty in 22,3 % of them. The target is HIS RATE, not
zero — driving these to zero would replace an excess by a defect of the opposite sign, which is the error this whole review
has been correcting. They are reported as a rate beside his, never as a count of infractions."""


@dataclass(frozen=True)
class Infraction:
    check: str
    slot: str
    line: str
    detail: str
    kind: str = VIOLATION

    def __str__(self) -> str:
        return f"[{self.check}] {self.slot}: «{self.line}» — {self.detail}"


# ------------------------------------------------------------ LA RECALIBRACION CONTRA SU PRACTICA
#
# El control real-contra-real dijo lo que nadie habia comprobado: **quince de las veinte comprobaciones miden su
# estilo**, no un defecto. El da 8,02 infracciones por dieta contra 1,54 del motor y NINGUNA de sus 200 dietas esta
# limpia. Y las dos que mas delatan al sistema en el discriminador estan INVERTIDAS: el repite un alimento dentro de
# la franja 3,79 veces por dieta y el sistema cero, y `16_alimento_repetido_en_la_franja` penaliza repetir. Se estaba
# optimizando contra una regla que alejaba del profesional.
#
# La recalibracion no se escribe a mano: sale de SUS PERCENTILES, igual que ya se hizo con los grupos de alternativas
# (mediana 7, p05 2, p95 12). `eval.conformance --measure-his-rates` pasa las mismas comprobaciones sobre N dietas
# suyas y escribe `$FPS_DATASET_DIR/his_check_rates.json` con la tasa de cada una. La regla de reclasificacion es
# categorica, no un umbral elegido:
#
#     su tasa == 0  -> VIOLACION. El nunca lo hace; que el sistema lo haga es un defecto sin matiz.
#     su tasa >  0  -> CALIBRACION, con SU tasa como objetivo. Es una regularidad suya y llevarla a cero
#                      sustituiria un exceso por un defecto del signo contrario.
#
# Lo que no se puede calibrar asi se RETIRA y se dice: `18_sin_pie` y `19_objetivo_vacio` son propiedades del
# exportador, no de la dieta, y su tasa sobre las dietas de el no significa nada.
RETIRED = {
    "18_sin_pie": "propiedad del exportador, no de la dieta: su tasa sobre las dietas de el no significa nada",
    "19_objetivo_vacio": "idem; ademas su causa esta encontrada y es GOAL_TEXT[UNCLASSIFIED] = cadena vacia",
}


def _his_bands() -> dict:
    """Las bandas de las tres comprobaciones nuevas, MEDIDAS sobre sus dietas. Ninguna se escribe a mano aqui."""
    try:
        from finalprosports.infrastructure.config.paths import dataset_dir
        return json.loads((dataset_dir() / "his_check_rates.json").read_text(encoding="utf-8")).get("bands", {})
    except (OSError, json.JSONDecodeError):
        return {}


def load_his_rates() -> dict:
    """La tasa medida de cada comprobacion sobre SUS dietas. Sin el fichero, se usa el respaldo escrito abajo."""
    try:
        from finalprosports.infrastructure.config.paths import dataset_dir
        data = json.loads((dataset_dir() / "his_check_rates.json").read_text(encoding="utf-8"))
        return {k: v["rate"] for k, v in data.get("checks", {}).items()}
    except (OSError, json.JSONDecodeError, KeyError):
        return {}


#: check name -> the rate HE has, for the calibration checks. Measured; the docstring of each check says how.
HIS_RATE = {
    "7b_alimento_repetido_entre_franjas": 0.886,
    "7b_par_repetido_entre_franjas": 0.886,
    "7b_comida_cena_dos_alimentos": 0.630,
    "11_franja_de_entreno_vacia": 0.223,
}
HIS_RATE |= load_his_rates()          # lo medido gana sobre el respaldo escrito a mano

# Bandas de las tres comprobaciones nuevas. Los valores de respaldo son los que midio el discriminador sobre las 815
# dietas reales (`descriptor_means`); si existe `his_check_rates.json`, gana lo medido alli.
_BANDS = _his_bands()
HIS_UNMAPPED_MEDIAN = _BANDS.get("unmapped_median", 0.025)
HIS_UNMAPPED_P05 = _BANDS.get("unmapped_p05", 0.0)
HIS_UNIT_SHARE = {Unit.TABLESPOON: tuple(_BANDS.get("unit_tablespoon", [0.0, 0.09])) + ("cucharada",),
                  Unit.PIECE: tuple(_BANDS.get("unit_piece", [0.15, 0.45])) + ("pieza",)}
HIS_GROUP_SHARE = {FoodGroup.FRUIT: tuple(_BANDS.get("group_fruit", [0.02, 0.12])),
                   FoodGroup.VEGETABLE: tuple(_BANDS.get("group_vegetable", [0.03, 0.18]))}


def classify(check: str, default_kind: str = VIOLATION) -> str:
    """VIOLACION solo si EL nunca lo hace. Es la regla del bloque 4 y no admite excepcion por comprobacion."""
    if check in RETIRED:
        return CALIBRATION
    return CALIBRATION if HIS_RATE.get(check, 0.0) > 0.0 else default_kind


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("_", " "))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


class Tables:
    """Everything the checks need, read from the mined artefacts. No threshold is invented in this module."""

    def __init__(self, root, pid: str):
        self.catalog = root.catalog
        self.env = root.envelope.load(pid)
        self.stats = root.rotation_stats.load(pid)
        data = json.loads((repo_root() / "pipeline" / "src" / "pipeline" / "data" / "portion_units.json").read_text(encoding="utf-8"))
        self.unquantified = {r["food"] for r in data.get("unquantified_supplements", [])}
        self.weighed = {r["food"]: r["gram_median"] for r in data.get("weighed_foods", [])}
        variants = json.loads((repo_root() / "pipeline" / "src" / "pipeline" / "data" / "food_variants.json").read_text(encoding="utf-8"))
        self.variants: dict[str, dict[str, str]] = {c: {v["key"]: v["text"] for v in vs} for c, vs in variants.get("variants", {}).items()}
        self.rations = {r["food"]: f"{r['median']:g} {r['unit']}" for r in data.get("supplement_rations", [])}
        totals = repo_root().parent / "Dietas"      # el dataset vive fuera del repositorio; se lee por FPS_DATASET_DIR
        from finalprosports.infrastructure.config.paths import dataset_dir
        f = dataset_dir() / "daily_totals_envelope.json"
        self.daily_totals = json.loads(f.read_text(encoding="utf-8"))["totals"] if f.exists() else {}
        self.medians = self.env.gram_medians or {}
        self.bands = self.env.ration_bands or {}

    def food(self, food_id):
        return self.catalog.get(food_id)

    def name(self, item) -> str:
        f = self.food(item.food_id)
        return item.canonical_name or (f.canonical_name if f else "") or item.normalized_key or ""

    def macro(self, food_id) -> set[str]:
        f = self.food(food_id)
        if f is None:
            return set()
        out = {f.group.value}
        sec = getattr(f, "secondary_group", None)
        if sec:
            out.add(sec.value if hasattr(sec, "value") else str(sec))
        return out


# --------------------------------------------------------------------------------------------------------------- checks
def check_supplements_quantified(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§2 — «batido de proteínas no hemos puesto la cantidad ni gramos ni cucharadas».

    Every supplement carries a quantity, EXCEPT the ones he himself leaves unquantified most of the time (electrolitos
    96,2 %, minerales 93,3 %, cafeína 69,7 %…). Emitting those without a quantity is fidelity, not a defect."""
    out = []
    for m in prop.meals:
        for g in m.groups:
            for o in g.options:
                f = t.food(o.item.food_id)
                if f is None or f.group is not FoodGroup.SUPPLEMENT:
                    continue
                n = t.name(o.item)
                # Only where he HAS a measured dose (n >= 10). «prebiótico» appears too rarely for the corpus to say whether
                # he quantifies it, and asserting on that would be asserting on noise.
                if o.item.quantity.value is None and n not in t.unquantified and n in t.rations:
                    out.append(Infraction("2_suplemento_sin_cantidad", m.slot.value, item_text(o),
                                          f"«{n}» sin cantidad; su dosis medida es {t.rations[n]}"))
    return out


def check_specific_variant(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§3 — «arroz no especificamos si debería ser integral o blanco o vaporizado».

    If any retrieved case writes this food with a specific variant, the proposal must write one too. The check looks at the
    CASES, not at the item: emitting «Arroz» while three of the twenty neighbours said «Arroz integral» is the defect."""
    out = []
    votes: dict[int, Counter] = defaultdict(Counter)
    for c in cases:
        for meal in c.diet.meals:
            for it in meal.items:
                key = _norm(it.normalized_key)
                canon = _norm(t.name(it))
                if canon in t.variants and key in t.variants[canon]:
                    votes[it.food_id][t.variants[canon][key]] += 1
    # Same floor as everywhere else: a variant ONE neighbour wrote is that client's wording, not a consensus. Asserting on it
    # would push the system to copy a single stranger's phrasing, which is the defect the note floor already fixed once.
    available = {fid: [v for v, n in c.items() if n >= MIN_CASE_SUPPORT] for fid, c in votes.items()}
    for m in prop.meals:
        for g in m.groups:
            for o in g.options:
                fid = o.item.food_id
                if available.get(fid) and not o.item.display_name:
                    out.append(Infraction("3_generico_con_variante_disponible", m.slot.value, item_text(o),
                                          f"los casos recuperados escriben {sorted(available[fid])}"))
    return out


def check_overlapping_supplements(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§4a — «si tú pones 2 electrolitos que ya son minerales, no tiene sentido poner otra vez minerales».

    **Refuted twice, and the second measurement is the one he asked for.** Not «two of the same function», which he does in
    42,5 % of his diets; the specific overlap he named. Measured over the corpus: of the 154 diets that carry electrolytes,
    26 also carry a generic «minerales» — **16,9 %, against a base rate of 7,9 %**. He does not avoid the combination, he
    tends to it, twice as often as chance. There is nothing to assert, and asserting it would make the system less like him.

    The check stays here, empty and documented, because the observation is part of the sixteen and its absence from the
    results should be a decision on the record rather than a gap."""
    return []


def _his_own(g) -> bool:
    """A group every member of which the professional wrote for THIS client. The same invariant as A2: what he wrote is not
    corrected. The checks below assert on what the SYSTEM builds — a group it composed, or one it altered by substituting a
    member — never on a line that is his verbatim."""
    return bool(g.options) and all(o.item.inherited for o in g.options)


def check_alternatives_interchangeable(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§4b — «es imposible que dé igual multivitamínico que electrolitos».

    Two foods are only alternatives of each other if HE writes them as alternatives somewhere in the corpus (1.071 pairs
    seen twice or more)."""
    out = []
    for m in prop.meals:
        for g in m.groups:
            if _his_own(g):
                continue
            ids = [o.item.food_id for o in g.options if o.item.food_id is not None]
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    if not t.stats.are_interchangeable(a, b):
                        out.append(Infraction("4b_alternativa_no_escrita", m.slot.value,
                                              " / ".join(item_text(o) for o in g.options),
                                              f"«{t.catalog[a].canonical_name}» y «{t.catalog[b].canonical_name}» no aparecen "
                                              f"como alternativas en ninguna de sus dietas"))
    return out


def check_alternatives_same_role(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """New (his reading of the delivered diet) — «160 gr Arroz integral / 150 gr Espinacas / 160 gr Espárragos /
    130 gr Boniato»: leaf vegetable offered as interchangeable with starch. The quantity-ratio criterion cannot see it
    because they all sit around 150 g; what separates them is the ROLE. Every food of a group must share a macrogroup."""
    out = []
    for m in prop.meals:
        for g in m.groups:
            if _his_own(g):
                continue
            macros = [t.macro(o.item.food_id) for o in g.options if o.item.food_id is not None]
            if len(macros) < 2:
                continue
            common = set.intersection(*macros) if macros else set()
            if not common:
                out.append(Infraction("4c_alternativas_de_distinto_papel", m.slot.value,
                                      " / ".join(item_text(o) for o in g.options),
                                      "los alimentos del grupo no comparten macrogrupo: "
                                      + ", ".join(f"{t.name(o.item)}={'/'.join(sorted(t.macro(o.item.food_id)))}" for o in g.options)))
    return out


def check_group_size(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """New — a dinner with five proteins on one line. His measured ceiling is four."""
    return [Infraction("4d_demasiadas_alternativas", m.slot.value, " / ".join(item_text(o) for o in g.options),
                       f"{len(g.options)} alternativas; su máximo medido es {MAX_ALTERNATIVES}")
            for m in prop.meals for g in m.groups if len(g.options) > MAX_ALTERNATIVES and not _his_own(g)]


def check_ration_coherence(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§5 and new — «300 gr Pechuga de pollo … 160 gr Salmón» in one group is the hamburger case again.

    Two foods of the same macrogroup in one slot keep a quantity ratio compatible with the ratio of their corpus medians;
    the tolerance is the p05-p95 band measured on his own diets, per macrogroup."""
    out = []
    for m in prop.meals:
        rows = []
        for g in m.groups:
            for o in g.options:
                f, it = t.food(o.item.food_id), o.item
                if f is None or it.quantity.unit is not Unit.GRAM or it.quantity.value is None or it.inherited:
                    continue          # A2: what he wrote for this client is neither rewritten nor reported as a defect
                n = t.name(it)
                if n in t.medians:
                    rows.append((f.group.value, n, float(it.quantity.value), o))
        by_group = defaultdict(list)
        for r in rows:
            by_group[r[0]].append(r)
        for gname, rs in by_group.items():
            band = t.bands.get(gname)
            if band is None or len(rs) < 2:
                continue
            lo, hi = band
            anchor = max(rs, key=lambda r: t.medians[r[1]])
            for gn, n, v, o in rs:
                if (n, v) == (anchor[1], anchor[2]):
                    continue
                pred = t.medians[n] / t.medians[anchor[1]]
                ratio = (v / anchor[2]) / pred if pred and anchor[2] else 1.0
                if not (lo <= ratio <= hi):
                    # Not a defect when his own two measurements disagree: if the ration the ratio asks for falls outside the
                    # [p05, p95] band of that food, there is no value that satisfies both and the system leaves his alone.
                    band_own = t.env.quantities.get((o.item.food_id, Unit.GRAM.value)) if t.env else None
                    target = t.medians[anchor[1]] and anchor[2] * pred
                    if band_own is not None and not band_own.contains(target):
                        continue
                    out.append(Infraction("5_racion_incoherente", m.slot.value, item_text(o),
                                          f"{v:g} g junto a {anchor[2]:g} g de {anchor[1]} da razón {ratio:.2f}, fuera de "
                                          f"[{lo:.2f}, {hi:.2f}] del macrogrupo {gname}"))
    return out


def check_absurd_units(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§6b — «1 pasas […] en todo caso poner gramos de pasa». Sixteen foods he weighs and never counts."""
    return [Infraction("6b_unidad_absurda", m.slot.value, item_text(o),
                       f"«{t.name(o.item)}» no se prescribe por unidades; su ración es {t.weighed[t.name(o.item)]:g} g")
            for m in prop.meals for g in m.groups for o in g.options
            if t.name(o.item) in t.weighed and o.item.quantity.unit is Unit.PIECE]


def check_number_agreement(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§6a — «1 pasas es error, debería ser 1 pasa». The exporter's business, checked on what the exporter writes."""
    from finalprosports.domain.composition.policy.document_template_policy import SINGULAR
    out = []
    for m in prop.meals:
        for g in m.groups:
            for o in g.options:
                q = o.item.quantity
                if q.unit is Unit.PIECE and q.value == 1 and _norm(t.name(o.item)) in SINGULAR:
                    if _norm(t.name(o.item)) in _norm(item_text(o)).split(" ", 1)[-1]:
                        out.append(Infraction("6a_concordancia", m.slot.value, item_text(o),
                                              f"un recuento de uno lleva singular: «{SINGULAR[_norm(t.name(o.item))]}»"))
    return out


def check_repeated_between_slots(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§7b — «zanahoria y remolacha los pones en comida y cena y el cliente debe ver cambios». CALIBRATION, both readings.

    Any two MAIN slots, not just contiguous ones: that the snack sits between lunch and dinner changes nothing for the person
    reading the sheet. Two readings were measured over his own diets and neither is rare:
      * a food shared by some pair of main slots — 88,6 % of his diets;
      * two or more foods shared by lunch and dinner specifically — 63,0 %;
      * the COMPLETE PAIR he named (two foods appearing together in two slots) — 88,6 %, `arroz + pollo` 287 times.
    So none of them is a violation. The system's rate is what has to come down to his, and the report puts the two side by
    side rather than counting infractions."""
    out = []
    present = {m.slot: {t.name(o.item) for g in m.groups for o in g.options if o.item.food_id is not None} for m in prop.meals}
    main = [s for s in CONSECUTIVE if s in present]
    shared_any = max((len(present[a] & present[b]) for i, a in enumerate(main) for b in main[i + 1:]), default=0)
    if shared_any >= 1:
        out.append(Infraction("7b_alimento_repetido_entre_franjas", "dieta", f"{shared_any} alimentos",
                              "algún alimento se repite entre dos franjas principales", CALIBRATION))
    if shared_any >= 2:
        out.append(Infraction("7b_par_repetido_entre_franjas", "dieta", f"{shared_any} alimentos",
                              "un par completo se repite entre dos franjas principales", CALIBRATION))
    if MealSlot.LUNCH in present and MealSlot.DINNER in present:
        shared = sorted(present[MealSlot.LUNCH] & present[MealSlot.DINNER])
        if len(shared) >= 2:
            out.append(Infraction("7b_comida_cena_dos_alimentos", "COMIDA / CENA", ", ".join(shared),
                                  f"{len(shared)} alimentos compartidos por comida y cena", CALIBRATION))
    return out


def check_empty_training_slot(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§11 — «DESPUES DE ENTRENAR: Nada» in a muscle-gain diet: «no poner nada es una errata».

    His ideal and his practice differ, but the practice turned out to be CONDITIONAL rather than random, and that is what
    decides the class of this check. Among his volume diets that declare a post-workout slot he leaves it empty in 13,4 %
    overall — but only **8,0 % when the client carries supplementation elsewhere in the diet**, against **53,3 % when he does
    not**. The signal is real, so for a supplemented client an empty printed post-workout slot is a VIOLATION. Ángel carries
    creatine, a shake and casein, so his «Nada» is a defect and not a coincidence.

    The pre-workout slot has no such signal (21,5 % against 28,9 %), so it stays a CALIBRATION against his 22,3 %.

    Note for the fix, not for the check: when the slot ends up empty he OMITS it more often than he prints it — 58,4 % of the
    time for post-workout. Printing «Nada» is the minority behaviour even for him."""
    if prop.profile.goal is not Goal.VOLUME:
        return []
    from finalprosports.domain.composition.policy.document_template_policy import TRAINING_EMPTY
    supplemented = any(t.food(o.item.food_id) is not None and t.food(o.item.food_id).group is FoodGroup.SUPPLEMENT
                       for m in prop.meals if m.slot not in TRAINING for g in m.groups for o in g.options)
    by_slot = {m.slot: m for m in prop.meals}
    out = []
    for slot in TRAINING:
        from finalprosports.domain.composition.policy.document_template_policy import OMIT_WHEN_EMPTY
        empty_text = TRAINING_EMPTY.get(slot)
        if empty_text is None or "nada" not in str(empty_text).lower() or slot in OMIT_WHEN_EMPTY:
            continue    # MITAD prints his water line, not «Nada»; and a slot the document OMITS when empty is never printed
        m = by_slot.get(slot)
        if m is not None and m.groups:
            continue
        label = SLOT_LABEL.get(slot, slot.value)
        if slot is MealSlot.POST_WORKOUT and supplemented:
            out.append(Infraction("11_post_entreno_vacio_con_suplementacion", label, str(empty_text),
                                  "dieta de volumen CON suplementación y franja post-entreno impresa vacía; "
                                  "él la deja así en el 8,0 % de esos casos, frente al 53,3 % sin suplementación", VIOLATION))
        else:
            out.append(Infraction("11_franja_de_entreno_vacia", label, str(empty_text),
                                  "franja de entreno impresa y vacía en una dieta de volumen", CALIBRATION))
    return out



def check_hydration_note(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§1 — «no dice cuánta agua». Él escribe la instrucción de hidratación en el 63,0 % de sus dietas.

    Se exige que la propuesta lleve una nota de hidratación Y que diga la cantidad: «beber agua» sin litros no es su
    instrucción. VIOLACIÓN y no calibración porque el propio profesional la señaló como falta, y porque la nota es
    reproducible por consenso —el catálogo canónico tiene el tema `hidratacion`— así que el sistema PUEDE emitirla.
    """
    tiene = [n for n in prop.notes if _HIDRA.search(n)]
    if not tiene:
        return [Infraction("1_sin_nota_de_hidratacion", None, "", "ninguna nota dice cuánta agua beber")]
    if not any(_LITROS.search(n) for n in tiene):
        return [Infraction("1_hidratacion_sin_cantidad", None, tiene[0][:70], "la nota de agua no dice la cantidad")]
    return []


def check_daily_totals(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """§nuevo — «la proteína total del día parece excesiva». Ninguna comprobación miraba TOTALES, solo ítems.

    Bandas p05–p95 de gramos por macrogrupo y día, minadas del corpus (`daily_totals_envelope.json`): proteína
    470–2.060 g, hidratos 140–1.560, grasa 15–205, verdura 80–750. Una dieta puede tener cada ración dentro de su
    banda y aun así sumar el doble de lo que él escribe nunca; eso es lo que esto ve y nada más lo veía.
    """
    if not t.daily_totals:
        return []
    tot: Counter = Counter()
    for m in prop.meals:
        for g in m.groups:
            for o in g.options[:1]:                       # la primera opción del grupo: una alternativa no se suma dos veces
                f = t.food(o.item.food_id)
                if f is None or o.item.quantity.unit is not Unit.GRAM or o.item.quantity.value is None:
                    continue
                tot[f.group.value] += float(o.item.quantity.value)
    out = []
    for grupo, suma in tot.items():
        banda = t.daily_totals.get(grupo)
        if not banda:
            continue
        if suma > banda["p95"]:
            out.append(Infraction("13_total_diario_alto", None, f"{grupo} {suma:.0f} g",
                                  f"por encima de su p95 diario ({banda['p95']:.0f} g, mediana {banda['p50']:.0f})"))
        elif suma < banda["p05"]:
            out.append(Infraction("13_total_diario_bajo", None, f"{grupo} {suma:.0f} g",
                                  f"por debajo de su p05 diario ({banda['p05']:.0f} g, mediana {banda['p50']:.0f})"))
    return out


def check_note_count(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """El número de bloques de notas dentro de lo que él escribe. Mediana 3, y una dieta sin ninguna nota no es suya."""
    n = len(prop.notes)
    if n == 0:
        return [Infraction("14_sin_notas", None, "", "el profesional escribe notas en el 73 % de sus dietas")]
    return []



# --------------------------------------------------------------------------------- comprobaciones sobre el DOCUMENTO
# Las ocho primeras miran la propuesta; éstas miran lo que se IMPRIME y la forma del documento, que es donde el
# preparador encontró más de una docena de defectos con el verificador diciendo 1. Un instrumento que no cubre lo
# que falla no vale, y ésta fue su frase.

def check_alternative_group_count(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """Grupos de alternativas por dieta dentro de su rango. Medido: media 7,08, mediana 7, p05 2, p95 12.

    La comprobación que habría cazado en el acto la regresión de `split_mixed_groups`: partía los grupos mixtos y de
    paso desmontaba los legítimos, dejando 46 grupos de una sola opción donde él escribe 7. El cliente se comía las
    cuatro opciones de hidratos en vez de elegir una.
    """
    con_alternativa = sum(1 for m in prop.meals for g in m.groups if len(g.options) > 1)
    if con_alternativa > ALT_GROUPS_P95:
        return [Infraction("15_demasiados_grupos", None, f"{con_alternativa} grupos",
                           f"por encima de su p95 ({ALT_GROUPS_P95}); su mediana es {ALT_GROUPS_MEDIAN}")]
    if con_alternativa < ALT_GROUPS_P05:
        return [Infraction("15_pocos_grupos", None, f"{con_alternativa} grupos",
                           f"por debajo de su p05 ({ALT_GROUPS_P05}); su mediana es {ALT_GROUPS_MEDIAN}")]
    return []


def check_no_duplicate_food_in_slot(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """El mismo alimento dos veces en la misma franja con cantidades distintas.

    «300 gr Pechuga de pollo» suelto y «320 gr Pechuga de pollo» dentro de un grupo, en la misma cena. No es una
    alternativa: es la misma comida escrita dos veces, y el cliente no sabe cuál seguir.
    """
    out = []
    for m in prop.meals:
        visto: dict[int, set] = defaultdict(set)
        for g in m.groups:
            for o in g.options:
                if o.item.food_id is not None:
                    visto[o.item.food_id].add(o.item.quantity.value)
        for fid, cantidades in visto.items():
            if len(cantidades) > 1:
                f = t.food(fid)
                out.append(Infraction("16_alimento_repetido_en_la_franja", m.slot.value,
                                      f.canonical_name if f else str(fid),
                                      f"aparece con {len(cantidades)} cantidades distintas: {sorted(x for x in cantidades if x)}"))
    return out


def check_printed_slot_names(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """Toda franja impresa lleva un nombre del vocabulario del profesional, y MEDIA TARDE se llama MEDIA TARDE.

    «OTROS» no es una franja suya: es el cajón del extractor asomando en el documento del cliente.
    """
    from finalprosports.domain.composition.policy.document_template_policy import SLOT_LABEL
    out = []
    for m in prop.meals:
        if m.slot in NON_PRINTABLE_SLOTS:
            out.append(Infraction("17_franja_no_suya", m.slot.value, SLOT_LABEL.get(m.slot, m.slot.value),
                                  "no es una franja del vocabulario del profesional"))
        elif SLOT_LABEL.get(m.slot) is None:
            out.append(Infraction("17_franja_sin_nombre", m.slot.value, "", "la franja no tiene nombre impreso"))
    if MealSlot.MID_AFTERNOON in {m.slot for m in prop.meals} and SLOT_LABEL[MealSlot.MID_AFTERNOON] != "MEDIA TARDE":
        out.append(Infraction("17_media_tarde_mal_nombrada", "MEDIA TARDE", SLOT_LABEL[MealSlot.MID_AFTERNOON],
                              "MEDIA TARDE se imprime con otro nombre"))
    return out


def check_document_footer(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """El pie con el correo y el teléfono. Está en todos sus documentos y es como el cliente le escribe."""
    from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import PdfDietExporterAdapter
    doc = PdfDietExporterAdapter(brand="FinalProSports", contact=CONTACT_PLACEHOLDER).document(prop, "X")
    pie = doc.of("footer")
    if not pie or not any("@" in p for p in pie):
        return [Infraction("18_sin_pie", None, str(pie), "el documento no lleva el pie con el contacto")]
    return []


def check_goal_printed_in_full(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """El objetivo impreso completo, incluidos los compuestos («Ganar masa muscular y tonificar»)."""
    from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import PdfDietExporterAdapter
    doc = PdfDietExporterAdapter(brand="x", contact="").document(prop, "X")
    linea = doc.of("objetivo")
    if not linea or not linea[0].strip():
        return [Infraction("19_objetivo_vacio", None, "", "el documento no imprime el objetivo")]
    return []


def check_post_workout_present(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """En dietas de VOLUMEN, la franja de después de entrenar existe y lleva contenido.

    Medido sobre las 482 dietas de volumen del corpus: **385 (79,9 %) tienen post-entreno CON CONTENIDO**. Omitirla
    no es lo mismo que imprimir «Nada» en una vacía: es perder una instrucción que él escribe en cuatro de cada
    cinco dietas de volumen («1 Batido de 60 gr proteínas con 30 gr Amilopeptinas + 1 ZMA + 1 Sales minerales»).
    """
    if prop.profile.goal is not Goal.VOLUME:
        return []
    m = next((x for x in prop.meals if x.slot is MealSlot.POST_WORKOUT), None)
    if m is None or not m.groups:
        return [Infraction("20_sin_post_entreno", "DESPUES DE ENTRENAR", "",
                           "en el 79,9 % de sus dietas de volumen esta franja lleva contenido")]
    return []

def check_unmapped_share(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """RASGO DELATOR #2 del discriminador (`share_unmapped`, AUC perdida 0,01124): **el 2,5 % de los items de sus
    dietas son cosas que el catalogo no sabe mapear, y en las generadas es el 0,0 %.**

    Es la firma mas limpia que tiene el sistema despues de la repeticion, y es estructural: el compositor solo puede
    emitir items del catalogo. La comprobacion NO pide inventar items sin mapear -- eso seria ensuciar a proposito --
    sino que declara el hecho cuando la propuesta esta al 0,0 % y el corpus no lo esta. Nace como CALIBRACION contra
    su tasa medida, nunca como violacion: un 0 % aqui no es un defecto de la dieta, es una consecuencia de componer
    desde un catalogo cerrado, y llevarlo a su tasa exigiria emitir texto que el motor no entiende.

    Caso que falla: una propuesta con 40 items, ninguno sin mapear, frente a su 2,5 % medido sobre 815 dietas.
    """
    items = [o for m in prop.meals for g in m.groups for o in g.options]
    if not items:
        return []
    sin_mapear = sum(1 for o in items if o.item.food_id is None)
    tasa = sin_mapear / len(items)
    # El p05 de su tasa es 0,0 -- mas de una de cada veinte dietas suyas no lleva ningun item sin mapear -- asi que
    # «por debajo de su p05» no puede ocurrir nunca y la comprobacion seria decorativa. La condicion es categorica:
    # salta cuando la propuesta esta EXACTAMENTE a cero y su mediana no lo esta.
    if tasa > 0 or HIS_UNMAPPED_MEDIAN <= 0:
        return []
    return [Infraction("21_todo_mapeado", None, f"{sin_mapear}/{len(items)}",
                       f"ningun item sin mapear; el escribe un {HIS_UNMAPPED_MEDIAN:.1%} (mediana), y esa "
                       "diferencia es el segundo rasgo que mas delata a una dieta generada", CALIBRATION)]


def check_unit_mix(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """RASGO DELATOR #4 (`unit_share_tablespoon`, 0,00507): **el sistema usa la cucharada mas que el** (5,2 % de sus
    items contra 4,0 %) **y la pieza menos** (22,6 % contra 28,9 %).

    Ninguna comprobacion miraba el REPARTO de unidades: `6b_unidad_absurda` solo caza absurdos. Se vigila la banda de
    su reparto por unidad, no un valor exacto, porque su propio reparto varia entre dietas.

    Caso que falla: una dieta donde mas del 9 % de los items van en cucharadas -- el doble de su tasa -- o donde
    menos del 15 % van en piezas.
    """
    items = [o for m in prop.meals for g in m.groups for o in g.options]
    if len(items) < 8:
        return []
    out = []
    for unidad, (bajo, alto, etiqueta) in HIS_UNIT_SHARE.items():
        n = sum(1 for o in items if o.item.quantity is not None and o.item.quantity.unit is unidad)
        tasa = n / len(items)
        if not (bajo <= tasa <= alto):
            out.append(Infraction("22_reparto_de_unidades", None, f"{etiqueta} {tasa:.1%}",
                                  f"fuera de su banda [{bajo:.1%}, {alto:.1%}] ({n} de {len(items)} items)",
                                  CALIBRATION))
    return out


def check_macro_share(prop: DietProposal, t: Tables, cases) -> list[Infraction]:
    """RASGOS DELATORES #5 y #12 (`share_FRUIT` 0,00181, `share_VEGETABLE` 0,00030): **el sistema propone menos fruta
    (3,8 % contra su 5,1 %) y menos verdura (6,4 % contra su 9,2 %)**.

    No existia ninguna comprobacion de composicion por macrogrupo: `15_*` cuenta grupos de alternativas y `13_*` mira
    gramos totales, y ninguna de las dos ve que la dieta lleve la mitad de verdura de la que el escribe. La banda sale
    de sus percentiles por dieta, no de un criterio nutricional: esto mide parecido con el, no salud.

    Caso que falla: una cena sin verdura en una dieta cuya proporcion global de verdura baja del p05 suyo.
    """
    items = [o for m in prop.meals for g in m.groups for o in g.options]
    conocidos = [o for o in items if o.item.food_id is not None and o.item.food_id in t.catalog]
    if len(conocidos) < 8:
        return []
    out = []
    for grupo, (bajo, alto) in HIS_GROUP_SHARE.items():
        n = sum(1 for o in conocidos if t.catalog[o.item.food_id].group is grupo)
        tasa = n / len(conocidos)
        if not (bajo <= tasa <= alto):
            out.append(Infraction("23_reparto_por_macrogrupo", None, f"{grupo.value} {tasa:.1%}",
                                  f"fuera de su banda [{bajo:.1%}, {alto:.1%}] ({n} de {len(conocidos)} items)",
                                  CALIBRATION))
    return out


CHECKS = (check_unmapped_share, check_unit_mix, check_macro_share,
          check_hydration_note, check_daily_totals, check_note_count,
          check_alternative_group_count, check_no_duplicate_food_in_slot, check_printed_slot_names,
          check_document_footer, check_goal_printed_in_full, check_post_workout_present,
          check_supplements_quantified, check_specific_variant, check_overlapping_supplements,
          check_alternatives_interchangeable, check_alternatives_same_role, check_group_size,
          check_ration_coherence, check_absurd_units, check_number_agreement,
          check_repeated_between_slots, check_empty_training_slot)


# ------------------------------------------------------------------------------ EL CONTROL: sus propias dietas
def as_proposal(diet, profile) -> DietProposal:
    """Una dieta REAL suya, con la forma que verifican las veinte comprobaciones.

    Existe porque un instrumento que solo se aplica a lo generado no distingue «el motor tiene un defecto» de «la
    comprobación mide el estilo del profesional». El precedente está en este proyecto: el validador simétrico daba
    1,000 mientras él estaba en 0,7873. Una comprobación que él incumple tanto o más que el sistema no mide un defecto:
    mide una regularidad suya que alguien escribió como norma.

    La conversión no inventa nada. Las alternativas se reconstruyen desde `alternative_group`, que es como el extractor
    guardó lo que él escribió con barras; los ítems sin grupo son un grupo de uno, igual que en una propuesta. La
    evidencia va VACÍA a propósito: una dieta suya no tiene casos recuperados detrás, y las comprobaciones que miran la
    evidencia (`3_variante_especifica`, `10_cantidad_sobrescrita`) no pueden aplicarse a ella. Se reportan aparte como
    NO APLICABLES en vez de contarlas como cero, que sería regalarle un aprobado.
    """
    from finalprosports.domain.model import AlternativeGroup, ItemEvidence, ProposedItem, ProposedMeal
    vacia = ItemEvidence(case_ids=(), support=0.0, rules=())
    meals = []
    for m in diet.meals:
        grupos, orden = {}, []
        for it in m.items:
            key = ("g", it.alternative_group) if it.alternative_group is not None else ("s", it.position, it.component_index)
            if key not in grupos:
                grupos[key] = []
                orden.append(key)
            grupos[key].append(ProposedItem(item=it, evidence=vacia))
        meals.append(ProposedMeal(slot=m.slot, groups=tuple(
            AlternativeGroup(position=i, options=tuple(grupos[k])) for i, k in enumerate(orden))))
    return DietProposal(profile=profile, meals=tuple(meals), notes=tuple(diet.notes),
                        retrieved_case_ids=(), strategy="REAL", parameters={}, validation=None)


# Comprobaciones que NO pueden aplicarse a una dieta suya, con el motivo. No se cuentan como cero: se declaran.
NOT_APPLICABLE_TO_REAL = {
    "3_generico_con_variante_disponible": "compara la propuesta con lo que escribieron los casos recuperados; una dieta suya no tiene casos detrás",
    "4b_alternativa_no_escrita": "pregunta si él escribe ese par como alternativa; sobre su propia dieta es una tautología",
    "18_sin_pie": "es una propiedad del exportador, no de la dieta",
}


def conform(prop: DietProposal, t: Tables, cases, reclassify: bool = True) -> list[Infraction]:
    """Pasa las comprobaciones y, salvo que se pida lo contrario, reclasifica cada una contra SU tasa medida.

    La reclasificacion se aplica AQUI y no en las 26 llamadas a `Infraction`: el tipo de una comprobacion no es una
    propiedad del sitio donde se detecta, es una decision sobre si el profesional lo hace o no, y esa decision tiene
    que estar en un solo sitio para que se pueda cambiar con una medicion y no con veintiseis ediciones.

    `reclassify=False` es lo que usa la medicion de sus tasas: reclasificar mientras se mide seria circular.
    """
    out: list[Infraction] = []
    for check in CHECKS:
        out += check(prop, t, cases)
    if not reclassify:
        return out
    return [dataclasses.replace(i, kind=classify(i.check, i.kind)) for i in out]


def measure_his_rates(root, pid, t, profiles, queries, args) -> int:
    """Pasa las comprobaciones sobre TODAS sus dietas y escribe la tasa de cada una, mas las bandas de las tres nuevas."""
    import dataclasses as _dc
    import statistics as _st
    from finalprosports.infrastructure.config.paths import dataset_dir

    muestra = list(queries) if args.sample >= len(queries) else random.Random(args.seed).sample(list(queries), args.sample)
    conteo: Counter = Counter()
    unmapped, unit_tbsp, unit_piece, g_fruit, g_veg = [], [], [], [], []
    for h in muestra:
        perfil = _dc.replace(profiles[h.client_code], goal=h.goal)
        prop = as_proposal(h, perfil)
        for i in {x.check for x in conform(prop, t, (), reclassify=False)}:
            conteo[i] += 1
        items = [o for m in prop.meals for g in m.groups for o in g.options]
        if not items:
            continue
        unmapped.append(sum(1 for o in items if o.item.food_id is None) / len(items))
        unit_tbsp.append(sum(1 for o in items if o.item.quantity is not None and o.item.quantity.unit is Unit.TABLESPOON) / len(items))
        unit_piece.append(sum(1 for o in items if o.item.quantity is not None and o.item.quantity.unit is Unit.PIECE) / len(items))
        conocidos = [o for o in items if o.item.food_id in t.catalog]
        if conocidos:
            g_fruit.append(sum(1 for o in conocidos if t.catalog[o.item.food_id].group is FoodGroup.FRUIT) / len(conocidos))
            g_veg.append(sum(1 for o in conocidos if t.catalog[o.item.food_id].group is FoodGroup.VEGETABLE) / len(conocidos))

    n = len(muestra)

    def pctl(xs, q):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else 0.0

    payload = {"diets_measured": n,
               "checks": {c: {"diets": v, "rate": v / n} for c, v in sorted(conteo.items(), key=lambda kv: -kv[1])},
               "bands": {"unmapped_median": _st.median(unmapped) if unmapped else 0.0,
                         "unmapped_p05": pctl(unmapped, 0.05),
                         "unit_tablespoon": [pctl(unit_tbsp, 0.05), pctl(unit_tbsp, 0.95)],
                         "unit_piece": [pctl(unit_piece, 0.05), pctl(unit_piece, 0.95)],
                         "group_fruit": [pctl(g_fruit, 0.05), pctl(g_fruit, 0.95)],
                         "group_vegetable": [pctl(g_veg, 0.05), pctl(g_veg, 0.95)]}}
    out = dataset_dir() / "his_check_rates.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    print(f"# SUS tasas, medidas sobre {n} dietas suyas")
    print("")
    print(f"{'comprobacion':44s}{'dietas':>9s}{'tasa':>9s}   pasa a")
    for c, v in payload["checks"].items():
        destino = "RETIRADA" if c in RETIRED else ("CALIBRACION" if v["rate"] > 0 else "violacion")
        print(f"{c:44s}{v['diets']:>9d}{v['rate']:>9.1%}   {destino}")
    nunca = [c.__name__ for c in CHECKS if not any(k in conteo for k in (c.__name__,))]
    print("")
    print("bandas medidas:")
    for k, v in payload["bands"].items():
        print(f"  {k:20} {v}")
    print("")
    print(f"-> {out}")
    return 0


# ------------------------------------------------------------------------------------------------------------------ run
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=50, help="generated diets to check (leave-one-out queries)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--client", help="also check the saved diet of this portfolio client (uuid)")
    ap.add_argument("--detail", type=int, default=6, help="infractions printed per check")
    ap.add_argument("--control", action="store_true",
                    help="EL CONTROL REAL CONTRA REAL: pasa las mismas comprobaciones sobre las dietas REALES del "
                         "profesional, misma muestra y mismo n. Sin esto no se puede distinguir «el motor falla» de "
                         "«la comprobacion mide su estilo»: el precedente es el validador simetrico, que daba 1,000 "
                         "mientras el estaba en 0,7873.")
    ap.add_argument("--json-out", type=Path, default=None, help="tabla comparada, para el informe")
    ap.add_argument("--measure-his-rates", action="store_true",
                    help="mide la tasa de CADA comprobacion sobre SUS dietas y escribe his_check_rates.json. Con esto "
                         "la reclasificacion violacion/calibracion sale de sus percentiles y no de una regla escrita "
                         "a mano. Se ejecuta SIN reclasificar: hacerlo mientras se mide seria circular.")
    ap.add_argument("--retrieval", choices=("motor", "D3"), default="motor",
                    help="con que vecindario se componen las dietas que se verifican: el del motor actual, o el "
                         "diverso con relleno por pureza (D3) del punto 2. Cambiar de siete votantes efectivos a "
                         "veinte altera que notas alcanzan el consenso, y eso hay que verificarlo antes de recomendarlo")
    args = ap.parse_args()

    from finalprosports.application.service.validation.diet_validator import DietValidator
    from finalprosports.domain.model import RestrictionMode
    from finalprosports.infrastructure.adapter.inbound.eval.loo_harness import (apply_plausibility, composer_like, retrieve_all, setup)

    root, pid, diets, profiles, queries, rules = setup()
    t = Tables(root, pid)
    rng = random.Random(args.seed)
    if args.measure_his_rates:
        return measure_his_rates(root, pid, t, profiles, queries, args)
    chosen = rng.sample(list(queries), min(args.sample, len(queries)))
    retrieved = retrieve_all(root, pid, chosen, profiles, root.composer.params.k)[0] if chosen else {}
    if args.retrieval == "D3":
        import dataclasses as _dc
        from finalprosports.infrastructure.adapter.inbound.eval.scarce_goals import variants as _variants
        svc = root.retrieve_similar_cases_service
        for _q in chosen:
            _perfil = _dc.replace(profiles[_q.client_code], goal=_q.goal)
            _cands = root.case_repository.find_similar(pid, svc.query_for(_perfil), root.composer.params.k * 8,
                                                       frozenset(svc.mandatory_exclusions(pid, _perfil) | {_q.id}))
            retrieved[_q.id] = (retrieved[_q.id][0], _variants(_cands, _q.goal, root.composer.params.k)["D3"])
    composer = composer_like(root)
    validator = DietValidator(root.catalog, RestrictionMode.STRICT, True)
    env = root.envelope.load(pid)

    per_check: dict[str, list[Infraction]] = defaultdict(list)
    diets_with: Counter = Counter()
    reports: list[tuple[str, list[Infraction]]] = []

    if args.client:
        prof = root.client_repository.get(pid, args.client)
        if prof is not None:
            prop = root.propose_diet_use_case.propose(pid, prof, k=20)
            cases = root.retrieve_similar_cases_service.retrieve(pid, prof, 20)
            reports.append((f"CLIENTE {args.client}", conform(prop, t, cases)))

    for h in chosen:
        profile, cases = retrieved[h.id]
        raw = composer.propose(profile, cases, rules)
        plaus, _ = apply_plausibility(raw, cases, env, root.catalog)
        prop = validator.validate(plaus, rules, profile, cases=cases)
        reports.append((h.id, conform(prop, t, cases)))

    for name, infractions in reports:
        for i in infractions:
            per_check[i.check].append(i)
        if infractions:
            diets_with[name] = len(infractions)

    n_diets = len(reports)
    viol = {c: v for c, v in per_check.items() if v and v[0].kind == VIOLATION}
    calib = {c: v for c, v in per_check.items() if v and v[0].kind == CALIBRATION}

    print(f"# Conformidad de la dieta generada · {n_diets} dietas · {len(CHECKS)} comprobaciones\n")
    print("## VIOLACIONES  (objetivo: 0)\n")
    print(f"{'comprobación':44s} {'infracciones':>12s} {'dietas':>8s} {'% dietas':>9s}")
    total_v = 0
    for check in sorted(viol, key=lambda c: -len(viol[c])):
        n_d = len({r[0] for r in reports if any(i.check == check for i in r[1])})
        total_v += len(viol[check])
        print(f"{check:44s} {len(viol[check]):12d} {n_d:8d} {n_d/n_diets:9.1%}")
    if not viol:
        print("   (ninguna)")
    clean = sum(1 for _, v in reports if not any(i.kind == VIOLATION for i in v))
    print(f"\nTOTAL {total_v} violaciones · dietas SIN ninguna violación: {clean}/{n_diets} = {clean/n_diets:.1%}")

    print("\n## CALIBRACIONES  (objetivo: su tasa medida)\n")
    print(f"{'comprobación':44s} {'sistema':>9s} {'él':>9s} {'exceso':>9s}")
    for check in sorted(calib, key=lambda c: -len(calib[c])):
        n_d = len({r[0] for r in reports if any(i.check == check for i in r[1])})
        rate, his = n_d / n_diets, HIS_RATE.get(check)
        mark = f"{rate - his:+9.1%}" if his is not None else f"{'—':>9s}"
        print(f"{check:44s} {rate:9.1%} {his if his is None else f'{his:9.1%}'} {mark}")
    if not calib:
        print("   (ninguna)")

    for label, table in (("VIOLACIÓN", viol), ("CALIBRACIÓN", calib)):
        for check in sorted(table, key=lambda c: -len(table[c])):
            print(f"\n## [{label}] {check}  ({len(table[check])})")
            for i in table[check][: args.detail]:
                print(f"   {i}")
            if len(table[check]) > args.detail:
                print(f"   … y {len(table[check]) - args.detail} más")
    # ------------------------------------------------------------------- EL CONTROL: las MISMAS comprobaciones sobre SUS dietas
    control_rows = {}
    if args.control:
        import dataclasses as _dc
        real_reports = []
        for h in chosen:
            perfil_real = _dc.replace(profiles[h.client_code], goal=h.goal)
            real_reports.append((h.id, conform(as_proposal(h, perfil_real), t, ())))
        n_real = len(real_reports)
        real_per_check = defaultdict(list)
        for _, infractions in real_reports:
            for i in infractions:
                real_per_check[i.check].append(i)

        print("")
        print(f"# CONTROL REAL CONTRA REAL · las mismas {len(CHECKS)} comprobaciones sobre {n_real} dietas SUYAS")
        print("")
        print("Una comprobacion que EL incumple tanto o mas que el sistema no mide un defecto del motor: mide una")
        print("regularidad suya que alguien escribio como norma. Esas hay que recalibrarlas o retirarlas.")
        print("")
        limpias_real = sum(1 for _, v in real_reports if not any(i.kind == VIOLATION for i in v))
        print(f"dietas SUYAS sin ninguna violacion: {limpias_real}/{n_real} = {limpias_real/n_real:.1%}   "
              f"(el sistema: {clean}/{n_diets} = {clean/n_diets:.1%})")
        total_real = sum(len(v) for v in real_per_check.values() if v and v[0].kind == VIOLATION)
        print(f"violaciones por dieta: EL {total_real/n_real:.2f}  ·  SISTEMA {total_v/n_diets:.2f}")
        print("")

        print(f"{'comprobacion':44s} {'sistema':>9s} {'el':>9s} {'diff':>9s}  veredicto")
        todas = sorted(set(per_check) | set(real_per_check) | {c for c in NOT_APPLICABLE_TO_REAL})
        for check in todas:
            sis = len({r[0] for r in reports if any(i.check == check for i in r[1])}) / n_diets
            if check in NOT_APPLICABLE_TO_REAL:
                print(f"{check:44s} {sis:9.1%} {'n/a':>9s} {'—':>9s}  NO APLICABLE: {NOT_APPLICABLE_TO_REAL[check]}")
                control_rows[check] = {"system": sis, "his": None, "verdict": "not_applicable"}
                continue
            suy = len({r[0] for r in real_reports if any(i.check == check for i in r[1])}) / n_real
            diff = sis - suy
            # Dos grupos, y el criterio es el signo: si EL puntua igual o peor, la comprobacion mide su estilo.
            verdict = "MIDE SU ESTILO -> recalibrar o retirar" if suy >= sis else "DEFECTO REAL del motor"
            if sis == 0 and suy == 0:
                verdict = "ninguno de los dos la incumple"
            print(f"{check:44s} {sis:9.1%} {suy:9.1%} {diff:+9.1%}  {verdict}")
            control_rows[check] = {"system": sis, "his": suy, "diff": diff, "verdict": verdict}
        mide_estilo = [c for c, r in control_rows.items() if r.get("verdict", "").startswith("MIDE")]
        defectos = [c for c, r in control_rows.items() if r.get("verdict", "").startswith("DEFECTO")]
        print("")
        print(f"RESUMEN: {len(mide_estilo)} comprobaciones miden SU ESTILO · {len(defectos)} son DEFECTOS REALES · "
              f"{len(NOT_APPLICABLE_TO_REAL)} no aplicables")
        print(f"  miden su estilo : {', '.join(mide_estilo) or '(ninguna)'}")
        print(f"  defectos reales : {', '.join(defectos) or '(ninguna)'}")

    if args.json_out:
        args.json_out.write_text(json.dumps(
            {"retrieval": args.retrieval, "n_generated": n_diets, "violations_total": total_v,
             "clean_generated": clean, "checks": len(CHECKS), "control": control_rows},
            ensure_ascii=False, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    total = total_v
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
