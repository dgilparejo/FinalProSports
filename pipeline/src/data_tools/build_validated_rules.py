# -*- coding: utf-8 -*-
"""
Phase 3c — Validated rule "constitution" recomputed on the clean corpus with confounder control.

Replaces the hand-curated _meta/reglas_validadas.md (which is NOT modified) by a
document + JSON block where EVERY rule carries:
  n_support   diets that exhibit the rule inside its condition group
  n_group     size of the condition group
  lift        prevalence in group / global prevalence   (conditional rules)
  prevalence  for global / placement rules
  adjusted    the same effect after controlling the obvious confounder:
                - sex rules       -> Mantel-Haenszel ratio F/M stratified by goal
                - goal rules      -> Mantel-Haenszel ratio group/rest stratified by sex
                - phase rules     -> lift recomputed inside clients with >= --min-tenure diets
  confidence  high / medium / low with the explicit criteria below
  status      kept / retired / descriptive / policy
  nature      prescriptive / descriptive (Fase 9, B): a rule is PRESCRIPTIVE -- it may be demanded of every proposal -- only when it is
              kept (or a policy) AND the professional follows it in the MAJORITY of its group (prevalence > MAJORITY_PREVALENCE = 0.5,
              for avoidance rules the avoided pattern must be <= 0.5). A kept rule with prevalence 0.27 discriminates the goal but cannot be
              required in 100 % of the proposals: it stays DESCRIPTIVE. Mirrors domain/model/rule.py (Rule.nature, MAJORITY_PREVALENCE).

Confidence criteria (conditional rules):
  low     n_support < MIN_N (15), or |effect| weak (lift in [0.8, 1.25]), or the effect
          disappears after adjustment (adjusted in [0.8, 1.25]) -> confounded
  high    n_support >= STRONG_N (30) and lift >= 1.5 (or <= 0.5 for "avoid" rules)
          and the adjusted effect keeps the same strength
  medium  everything else
Confidence criteria (global / placement rules, prevalence based):
  high    prevalence >= 0.5 and n_support >= 30 ; medium prevalence >= 0.25 ; low otherwise
  For "avoid" placement rules the prevalence of the AVOIDED pattern must be <= 0.10 for high.

Inputs:  --diets _dataset/diets.jsonl
Outputs: --out-dir/validated_rules.json, --out-dir/validated_rules.md (Spanish prose)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MAJORITY_PREVALENCE = 0.5     # same value as finalprosports.domain.model.rule.MAJORITY_PREVALENCE (checked by pipeline/tests/test_dataset.py)


def nature_of(res: dict, avoid: bool) -> str:
    """prescriptive = demandable of every proposal of its group; descriptive = reported and explained, never required."""
    if res["status"] == "policy":
        return "prescriptive"                       # respetar intolerancias / alergias: maximum priority, not measurable
    if res["status"] != "kept" or res["kind"] == "behaviour":
        return "descriptive"
    prev = res.get("prevalence_in_group")
    if prev is None:
        return "descriptive"
    followed = (1.0 - prev) if avoid else prev      # for avoidance rules prevalence_in_group is the AVOIDED pattern
    # STRICTLY greater: a majority is more than half, not half. The cut used to be >=, and on the rebuilt corpus
    # `ansiedad_chocolate_o_gelatina` landed on exactly 52 of 104 -- a coin flip promoted to a rule the validator
    # demanded of 100 % of proposals, which failed 14 of the 21 golden profiles. One diet either way flipped it.
    # A rule the professional follows half the time is evidence, not a requirement.
    return "prescriptive" if followed > MAJORITY_PREVALENCE else "descriptive"
from pii_common import load_records, require_file, write_json  # noqa: E402

MIN_N, STRONG_N = 15, 30
WEAK = (0.8, 1.25)

CARB = re.compile(r"arroz|avena|patata|pan |boniato|quinoa|pasta|cereal")
FRUIT = re.compile(r"\b(pl[aá]tano|banana|manzana|kiwi|naranja|mandarina|pera|peras|fresa|fresas|ar[aá]ndano\w*|"
                   r"frambuesa\w*|uva\w*|mel[oó]n|sand[ií]a|pi[ñn]a|mango|melocot[oó]n|ciruela\w*|cereza\w*|higo\w*|"
                   r"frutos rojos|fruta)\b", re.I)
PROTEIN = re.compile(r"pescado|huevo|pollo|pavo|at[uú]n|merluza|salm[oó]n|carne|ternera|gambas|marisco|tortilla", re.I)
VEG = re.compile(r"verdura|ensalada|espinaca|pepino|tomate|pimiento|lechuga|br[oó]coli|calabac[ií]n|jud[ií]as|esp[aá]rrago|champi", re.I)
FIRST_HALF = ("DESAYUNO", "MEDIA MAÑANA", "ALMUERZO", "COMIDA", "MERIENDA")


def in_slots(meals, prefixes, rx):
    for slot, items in meals.items():
        if any(slot.upper().startswith(p) for p in prefixes):
            if any(rx.search(it) for it in items):
                return True
    return False


def has_slot(meals, prefixes):
    return any(any(slot.upper().startswith(p) for p in prefixes) for slot in meals)


# ------------------------------------------------------------------ matchers
def rx(pattern):
    p = re.compile(pattern, re.I)
    return lambda r: bool(p.search(r["_blob"]))


MATCHERS = {
    "agua": rx(r"litros de agua|2[.,]5 litros|ingesta de agua|beber agua|beber.*litros"),
    "azucar_procesados": rx(r"sin az[uú]car|no tomar postres|az[uú]car|azucares|harinas? blanca|procesad|boller[ií]a|refresco|zumos?\b|alcohol"),
    "masticar_despacio": rx(r"masticar|despacio"),
    "cafe_te": rx(r"\bcaf[eé]\b|\bt[eé] verde\b|\bt[eé]\b sin|infusi[oó]n"),
    "ayuno_16h": rx(r"16\s*(a\s*17\s*)?horas|ayuno intermitente|16 h"),
    "comida_tarde_cena_temprano": rx(r"lo m[aá]s tarde|lo m[aá]s temprano|m[aá]s tarde posible|m[aá]s temprano posible"),
    "sustituir_pescado_pollo": rx(r"sustituir el pescado|sustituir el huevo|por pollo"),
    "sal_himalaya": rx(r"himalaya"),
    "grasas_base": rx(r"aguacate|frutos secos|aceite de coco|\baove\b|aceite de oliva"),
    "suplementacion": rx(r"bcaa|glutamina|creatina|amilopectina|amino power"),
    "fibra": rx(r"fibra"),
    "saltarse_comidas": rx(r"saltarte 1 comida|dos comidas|2 comidas|saltar.*comida"),
    "chocolate_gelatina": rx(r"chocolate negro|gelatina sin az"),
    "soja": rx(r"soja"),
    "hidratos_en_cena": lambda r: in_slots(r["meals"], ("CENA", "RECENA"), CARB),
    "fruta_en_cena": lambda r: in_slots(r["meals"], ("CENA", "RECENA"), FRUIT),
    "cena_proteina_verdura": lambda r: in_slots(r["meals"], ("CENA",), PROTEIN) and in_slots(r["meals"], ("CENA",), VEG),
    "desayuno_avena_cereal": lambda r: in_slots(r["meals"], ("DESAYUNO",), re.compile(r"avena|cereal", re.I)),
    "hidratos_primera_mitad": lambda r: in_slots(r["meals"], FIRST_HALF, CARB),
}
DENOMINATORS = {   # placement rules are measured only where the slot exists
    "cena_proteina_verdura": lambda r: has_slot(r["meals"], ("CENA",)),
    "desayuno_avena_cereal": lambda r: has_slot(r["meals"], ("DESAYUNO",)),
    "fruta_en_cena": lambda r: has_slot(r["meals"], ("CENA", "RECENA")),
    "hidratos_primera_mitad": lambda r: any(in_slots(r["meals"], (s,), CARB) for s in r["meals"]),
}

# ------------------------------------------------------------------ rule specs
# kind: global | goal | sex | phase | placement | avoid_placement | policy
SPECS = [
    # 1. GLOBAL
    dict(id="agua_2.5L", section="1. Reglas GLOBALES", kind="global", matcher="agua",
         statement="Hidratación ~2,5 L de agua al día, a tragos pequeños y entre comidas."),
    dict(id="prohibido_azucar_procesados", section="1. Reglas GLOBALES", kind="global", matcher="azucar_procesados",
         statement="Azúcares y procesados prohibidos (azúcar, postres, harinas blancas, refrescos, zumos, alcohol)."),
    dict(id="comer_despacio", section="1. Reglas GLOBALES", kind="global", matcher="masticar_despacio",
         statement="Comer despacio y masticar bien."),
    dict(id="cafe_te_permitidos", section="1. Reglas GLOBALES", kind="global", matcher="cafe_te",
         statement="Café solo, té e infusiones sin azúcar permitidos."),
    # 2. BY GOAL
    dict(id="ayuno_16h", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="ayuno_16h",
         groups=["ayuno_intermitente", "cetosis_keto"], statement="Ayuno ≥16 h entre la última y la primera comida."),
    dict(id="comida_tarde_cena_temprano", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="comida_tarde_cena_temprano",
         groups=["ayuno_intermitente", "cetosis_keto"], statement="Comida lo más tarde posible / cena lo más temprano posible."),
    dict(id="sustituir_pescado_por_pollo", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="sustituir_pescado_pollo",
         groups=["ayuno_intermitente", "cetosis_keto"], statement="Sustitución pescado/huevo → pollo permitida en la cena."),
    dict(id="sal_himalaya", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="sal_himalaya",
         groups=["cetosis_keto"], statement="Sal del Himalaya como única sal permitida."),
    dict(id="sin_hidratos_cena", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="hidratos_en_cena", avoid=True,
         groups=["cetosis_keto", "ayuno_intermitente"], statement="Sin hidratos en la cena (el patrón «hidratos en cena» debe ser raro en el grupo)."),
    dict(id="grasas_base", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="grasas_base",
         groups=["cetosis_keto"], statement="Grasas saludables como base (aguacate, frutos secos, AOVE, aceite de coco)."),
    dict(id="hidratos_en_cena", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="hidratos_en_cena",
         groups=["volumen_masa", "descarga_carga", "mantenimiento", "hipocalorica"], per_group=True,
         statement="Hidratos SÍ en la cena (arroz, avena, patata, boniato)."),
    dict(id="suplementacion_pre_post", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="suplementacion",
         groups=["volumen_masa"], statement="Suplementación pre/post entreno (BCAAs, glutamina, creatina, amilopectinas, proteína aislada)."),
    dict(id="refuerzo_fibra", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="fibra",
         groups=["alta_en_fibra"], circular=True, statement="Refuerzo de fibra en dietas «alta en fibra»."),
    dict(id="saltarse_comidas_fibra", section="2. CONDICIONALES por OBJETIVO", kind="goal", matcher="saltarse_comidas",
         groups=["alta_en_fibra"], statement="Mayor frecuencia de «saltarse 1 comida / hacer 2 comidas» en alta en fibra."),
    # 3. PLACEMENT
    dict(id="hidratos_primera_mitad_dia", section="3. COLOCACIÓN por franja", kind="placement", matcher="hidratos_primera_mitad",
         statement="Cuando hay hidratos, aparecen en la primera mitad del día (desayuno / media mañana / comida / merienda)."),
    dict(id="fruta_no_en_cena", section="3. COLOCACIÓN por franja", kind="avoid_placement", matcher="fruta_en_cena",
         statement="Evitar fruta en la cena."),
    dict(id="cena_proteina_grasa_verdura", section="3. COLOCACIÓN por franja", kind="placement", matcher="cena_proteina_verdura",
         statement="Cena tipo: proteína (pescado/huevo/pollo) + verdura (+ grasa)."),
    dict(id="desayuno_avena_cereales", section="3. COLOCACIÓN por franja", kind="placement", matcher="desayuno_avena_cereal",
         statement="Desayuno tipo: avena / cereales sin azúcar (+ frutos secos, proteína si volumen)."),
    # 4. PHASE
    dict(id="saltarse_comidas_fases_tempranas", section="4. CONDICIONALES por FASE", kind="phase", matcher="saltarse_comidas",
         groups=["v1", "v2-4"], statement="Fases tempranas (v1–v4): más «saltarse 1 comida / hacer 2 comidas»."),
    dict(id="ayuno_estable_por_fase", section="4. CONDICIONALES por FASE", kind="phase", matcher="ayuno_16h", null_expected=True,
         groups=["v1", "v2-4"], statement="El ayuno se mantiene estable en todas las fases (se espera lift ≈ 1)."),
    dict(id="alta_fibra_fases_tempranas", section="4. CONDICIONALES por FASE", kind="phase", matcher="fibra",
         groups=["v1"], statement="Enfoque alta en fibra en fases tempranas (v1)."),
    dict(id="pescado_pollo_v1", section="4. CONDICIONALES por FASE", kind="phase", matcher="sustituir_pescado_pollo",
         groups=["v1"], statement="Sustitución pescado→pollo sobre todo en v1."),
    dict(id="suplementacion_v5", section="4. CONDICIONALES por FASE", kind="phase", matcher="suplementacion",
         groups=["v5+"], statement="Fases avanzadas (v5+): mayor suplementación pre/post entreno."),
    # 5. SEX
    dict(id="mujeres_prohibicion_azucar", section="5. CONDICIONALES por SEXO", kind="sex", matcher="azucar_procesados", groups=["F"],
         statement="En mujeres es más frecuente la prohibición explícita de azúcar."),
    dict(id="mujeres_sal_himalaya", section="5. CONDICIONALES por SEXO", kind="sex", matcher="sal_himalaya", groups=["F"],
         statement="En mujeres es más frecuente la sal del Himalaya."),
    dict(id="mujeres_chocolate_gelatina", section="5. CONDICIONALES por SEXO", kind="sex", matcher="chocolate_gelatina", groups=["F"],
         statement="En mujeres es más frecuente el recurso al chocolate negro / gelatina para la ansiedad."),
    dict(id="mujeres_alta_fibra", section="5. CONDICIONALES por SEXO", kind="sex", matcher="fibra", groups=["F"],
         statement="En mujeres es más frecuente la alta en fibra."),
    dict(id="hombres_suplementacion", section="5. CONDICIONALES por SEXO", kind="sex", matcher="suplementacion", groups=["M"],
         statement="Suplementación pre-entreno mucho más frecuente en hombres que en mujeres."),
    # 6. ANXIETY
    dict(id="ansiedad_chocolate_o_gelatina", section="6. Gestión de la ANSIEDAD", kind="goal", matcher="chocolate_gelatina",
         groups=["cetosis_keto", "hipocalorica", "ayuno_intermitente"], per_group=True,
         statement="En dietas restrictivas, chocolate negro o gelatina sin azúcar ante ansiedad; nunca hidratos/azúcares."),
    # 7. RESTRICTIONS
    dict(id="soja_prohibida", section="7. Restricciones puntuales", kind="global", matcher="soja", descriptive=True,
         statement="Soja y derivados prohibidos en una fracción de dietas (preferencia/intolerancia del cliente)."),
    dict(id="respetar_intolerancias_alergias", section="7. Restricciones puntuales", kind="policy",
         statement="Respetar intolerancias/alergias del perfil por encima de cualquier regla general (no medible en el corpus)."),
]


# ------------------------------------------------------------------ statistics
def mh_ratio(rows, in_group, match, stratum):
    """Mantel-Haenszel ratio of prevalence(in_group) / prevalence(rest), stratified."""
    num = den = 0.0
    strata = defaultdict(lambda: [0, 0, 0, 0])   # a=match&in, n_in, b=match&out, n_out
    for r in rows:
        s = stratum(r)
        if s is None:
            continue
        c = strata[s]
        if in_group(r):
            c[1] += 1
            c[0] += match(r)
        else:
            c[3] += 1
            c[2] += match(r)
    for a, n_in, b, n_out in strata.values():
        n = n_in + n_out
        if n_in == 0 or n_out == 0:
            continue
        num += a * n_out / n
        den += b * n_in / n
    return round(num / den, 2) if den else None


def weak(x):
    return x is None or WEAK[0] <= x <= WEAK[1]


def strong(x, avoid=False):
    return x is not None and (x <= 0.5 if avoid else x >= 1.5)


def vanished(adjusted, avoid=False):
    """Effect gone (or reversed) after adjustment: below the weak band for positive rules,
    above it for avoidance rules."""
    if adjusted is None:
        return False
    return adjusted > WEAK[0] if avoid else adjusted < WEAK[1]


def confidence_conditional(n_support, lift, adjusted, avoid=False, n_support_adjusted=None):
    reasons = []
    if n_support < MIN_N:
        reasons.append(f"n_support < {MIN_N}")
    if weak(lift):
        reasons.append("lift débil (0.8–1.25)")
    if adjusted is not None and vanished(adjusted, avoid) and not weak(lift):
        reasons.append("el efecto desaparece al estratificar (confundido)")
    if n_support_adjusted is not None and n_support_adjusted < MIN_N:
        reasons.append(f"muestra intra-cliente insuficiente (n < {MIN_N})")
    if reasons:
        return "low", "; ".join(reasons)
    if n_support >= STRONG_N and strong(lift, avoid) and (adjusted is None or strong(adjusted, avoid)):
        return "high", f"n_support ≥ {STRONG_N}, lift {'≤ 0.5' if avoid else '≥ 1.5'} y se mantiene ajustado"
    return "medium", "efecto presente pero moderado o muestra intermedia"


def confidence_prevalence(n_support, prevalence, avoid=False):
    if avoid:
        if prevalence <= 0.10 and n_support >= STRONG_N:
            return "high", "patrón evitado en ≤ 10 % de las dietas"
        return ("medium", "patrón evitado en ≤ 25 %") if prevalence <= 0.25 else ("low", "el patrón evitado es frecuente")
    if prevalence >= 0.5 and n_support >= STRONG_N:
        return "high", "prevalencia ≥ 50 %"
    if prevalence >= 0.25:
        return "medium", "prevalencia ≥ 25 %"
    return "low", "prevalencia < 25 %"


def phase_of(v):
    return "sin_version" if v is None else "v1" if v == 1 else "v2-4" if v <= 4 else "v5+"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diets", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--min-tenure", type=int, default=5)
    args = ap.parse_args()
    rows = load_records(require_file(args.diets))
    N = len(rows)
    for r in rows:
        m = r["meta"]
        # The evidence a rule is measured on has to be evidence a PROPOSAL can carry, and a proposal has no
        # OBJETIVO line. Including `goal_text` here inflated exactly the rules whose wording repeats the goal:
        # `ayuno_16h` scored 0,90 support of which 236 matches came from the goal text and only 148 from the notes
        # it is actually evaluated against, so the validator demanded of every fasting proposal a note the corpus
        # supports far more weakly than the figure suggested. Meals and notes stay: a proposal has both.
        r["_blob"] = (" \n".join(" ".join(v) for v in r["meals"].values()) + " \n" + " ".join(r["notes"])).lower()
        r["_phase"] = phase_of(m["diet_version"])
    tenure = Counter(r["meta"]["client_code"] for r in rows)
    tenured = [r for r in rows if tenure[r["meta"]["client_code"]] >= args.min_tenure and r["_phase"] != "sin_version"]
    goal_of = lambda r: r["meta"]["goal"]
    # A conditional rule's group is the diets that declare the label EITHER as their purpose or as their structural
    # method. "Ayuno intermitente para perder grasa" belongs in the fasting group whatever its goal field says, and
    # reading only `goal` is what collapsed `sin_hidratos_cena` and `sustituir_pescado_por_pollo` from a group of
    # 300 diets to one of 98 when the rebuild started reading the purpose instead of the method. The membership
    # test is widened; no label is rewritten and `goal` still decides the stratum.
    labels_of = lambda r: {r["meta"]["goal"], *(r["meta"].get("methods") or ())} - {None}
    sex_of = lambda r: r["meta"]["sex"] if r["meta"]["sex"] in ("M", "F") else None

    results = []
    for spec in SPECS:
        res = {k: spec[k] for k in ("id", "section", "kind", "statement")}
        res["condition"] = spec.get("groups")
        if spec["kind"] == "policy":
            res.update(n_group=None, n_support=None, prevalence_in_group=None, lift=None, adjusted=None,
                       adjusted_method=None, confidence=None, status="policy", criteria="regla de política, no medible")
            results.append(res)
            continue
        match = MATCHERS[spec["matcher"]]
        denom = DENOMINATORS.get(spec["matcher"], lambda r: True)
        base = [r for r in rows if denom(r)]
        avoid = spec.get("avoid", False)
        if spec["kind"] in ("global", "placement", "avoid_placement"):
            n_support = sum(1 for r in base if match(r))
            prev = n_support / len(base)
            res.update(n_group=len(base), n_support=n_support, prevalence_in_group=round(prev, 3), prevalence_global=round(prev, 3),
                       lift=None, adjusted=None, adjusted_method=None)
            if spec.get("descriptive"):
                res.update(confidence="low", status="descriptive", criteria="regla descriptiva: prevalencia baja, condicionada al perfil")
            else:
                conf, why = confidence_prevalence(n_support if spec["kind"] != "avoid_placement" else len(base) - n_support, prev,
                                                  avoid=(spec["kind"] == "avoid_placement"))
                res.update(confidence=conf, status="kept" if conf != "low" else "retired", criteria=why)
            results.append(res)
            continue
        # conditional rules
        if spec["kind"] == "goal":
            in_group = lambda r, g=set(spec["groups"]): bool(labels_of(r) & g)
            stratum, method = sex_of, "Mantel-Haenszel grupo/resto estratificado por sexo"
        elif spec["kind"] == "sex":
            in_group = lambda r, g=set(spec["groups"]): r["meta"]["sex"] in g
            other = "M" if spec["groups"] == ["F"] else "F"
            # compare against the other sex only (unknown sex excluded)
            base = [r for r in base if r["meta"]["sex"] in ("M", "F")]
            stratum, method = goal_of, f"Mantel-Haenszel {spec['groups'][0]}/{other} estratificado por objetivo"
        else:  # phase
            in_group = lambda r, g=set(spec["groups"]): r["_phase"] in g
            base = [r for r in base if r["_phase"] != "sin_version"]
            stratum, method = None, f"lift recalculado dentro de clientes con ≥{args.min_tenure} dietas"
        grp = [r for r in base if in_group(r)]
        n_match = sum(1 for r in grp if match(r))
        prev_in = n_match / len(grp) if grp else 0.0
        if spec["kind"] == "sex":
            # reference = the other sex (the statement compares F vs M), not the pooled base
            ref = [r for r in base if not in_group(r)]
            prev_ref = sum(1 for r in ref if match(r)) / len(ref) if ref else 0.0
        else:
            prev_ref = sum(1 for r in base if match(r)) / len(base)
        lift = round(prev_in / prev_ref, 2) if prev_ref else None
        n_support_adjusted = None
        if spec["kind"] == "phase":
            t_base = [r for r in tenured if denom(r)]
            t_grp = [r for r in t_base if in_group(r)]
            t_match = sum(1 for r in t_grp if match(r))
            t_prev_in = t_match / len(t_grp) if t_grp else 0.0
            t_prev_all = sum(1 for r in t_base if match(r)) / len(t_base) if t_base else 0.0
            adjusted = round(t_prev_in / t_prev_all, 2) if t_prev_all else None
            n_support_adjusted = t_match
            res["n_support_adjusted"] = t_match
            res["n_group_adjusted"] = len(t_grp)
        else:
            adjusted = mh_ratio(base, in_group, lambda r: 1 if match(r) else 0, stratum)
        if adjusted is not None and adjusted > 100:
            adjusted = 100.0   # capped: the pattern is (almost) absent outside the group
        # for avoidance rules the support is the ABSENCE of the pattern inside the group
        n_support = (len(grp) - n_match) if avoid else n_match
        res.update(n_group=len(grp), n_match=n_match, n_support=n_support, prevalence_in_group=round(prev_in, 3),
                   prevalence_global=round(prev_ref, 3), lift=lift, adjusted=adjusted, adjusted_method=method)
        if spec.get("per_group"):
            res["by_group"] = {}
            for g in spec["groups"]:
                gg = [r for r in base if (goal_of(r) == g)]
                ns = sum(1 for r in gg if match(r))
                res["by_group"][g] = {"n_group": len(gg), "n_support": ns, "prevalence": round(ns / len(gg), 3) if gg else None,
                                      "lift": round((ns / len(gg)) / prev_ref, 2) if gg and prev_ref else None}
        if spec.get("null_expected"):
            stable = not (strong(lift) or (lift is not None and lift <= 0.67)) and not (adjusted is not None and (strong(adjusted) or adjusted <= 0.67))
            res.update(confidence="high" if stable and n_support >= STRONG_N else "low",
                       status="kept" if stable else "retired",
                       criteria="se esperaba ausencia de efecto: lift y ajustado dentro de [0.67, 1.5]" if stable else "aparece un efecto de fase")
        elif spec.get("circular"):
            res.update(confidence="low", status="descriptive",
                       criteria="circular: la etiqueta de objetivo se asignó con el mismo patrón («fibra»)")
        else:
            conf, why = confidence_conditional(n_support, lift, adjusted, avoid=avoid, n_support_adjusted=n_support_adjusted)
            res.update(confidence=conf, status="kept" if conf != "low" else "retired", criteria=why)
        results.append(res)

    # ------------------------------------------------------------ 8. behaviour towards declared restrictions (E1)
    # Fact vs behaviour: the food attribute contains_lactose stays factual; whether the professional restricts
    # lactose-containing foods for clients with a DECLARED intolerance is measured here from
    # _dataset/lactose_validation.json (validate_lactose.py) and stored as a rule with its empirical support.
    lact_path = args.out_dir / "lactose_validation.json"
    if lact_path.exists():
        lact = json.loads(lact_path.read_text(encoding="utf-8"))
        n_intol = lact["of_which_with_clean_diets"]
        dairy = ["batido de proteínas", "queso fresco", "requesón", "yogur", "queso", "caseína", "leche", "kéfir"]
        received = {f: lact["foods"][f] for f in dairy if f in lact["foods"]}
        # ratio of shares (intolerant clients receiving the food / whole population receiving it), averaged over foods
        ratios = [v["share_of_lactose_clients"] / v["share_of_all_clients"] for v in received.values()
                  if v["share_of_all_clients"] and v["share_of_lactose_clients"] is not None]
        any_dairy = max((v["lactose_clients_receiving_it"] for v in received.values()), default=0)
        res = {"id": "no_restringe_lacteos_intolerantes", "section": "8. COMPORTAMIENTO ante restricciones declaradas", "kind": "behaviour",
               "statement": "El profesional no restringe lácteos fermentados ni derivados del suero a clientes con intolerancia a la lactosa declarada "
                            "(tasas de prescripción equivalentes a la población general); solo la leche líquida está ausente en ese grupo.",
               "condition": ["has_intolerances (lactosa)"], "n_group": n_intol, "n_support": any_dairy,
               "prevalence_in_group": round(any_dairy / n_intol, 3) if n_intol else None, "prevalence_global": None,
               "lift": round(sum(ratios) / len(ratios), 2) if ratios else None, "adjusted": None,
               "adjusted_method": "ratio medio (cuota en intolerantes / cuota en población) sobre " + ", ".join(received),
               "per_food": {f: {"intolerant": v["lactose_clients_receiving_it"], "all": v["all_clients_receiving_it"],
                                "ratio": round(v["share_of_lactose_clients"] / v["share_of_all_clients"], 2) if v["share_of_all_clients"] else None}
                            for f, v in received.items()},
               "confidence": "low", "status": "kept",
               "criteria": f"n_group = {n_intol} < {STRONG_N}: soporte empírico insuficiente para confianza alta; regla de comportamiento, no atributo del alimento. "
                           "El validador puede reproducir este criterio o aplicar la restricción estricta (contains_lactose factual)."}
        results.append(res)
        h = lact["honey"]
        results.append({"id": "miel_evidencia_insuficiente", "section": "8. COMPORTAMIENTO ante restricciones declaradas", "kind": "behaviour",
                        "statement": "Miel: la evidencia del corpus es insuficiente para afirmar que el profesional la permita o la prohíba.",
                        "condition": None, "n_group": N, "n_support": h["components_total"], "prevalence_in_group": None, "prevalence_global": None,
                        "lift": None, "adjusted": None, "adjusted_method": None,
                        "per_food": {"miel": {"components": h["components_total"], "clients": h["clients"], "notes_mentioning": h["notes_mentioning_miel"], "notes_forbidding": h["notes_forbidding_miel"]}},
                        "confidence": None, "status": "descriptive",
                        "criteria": f"{h['components_total']} componentes en {h['clients']} clientes y {h['notes_mentioning_miel']} notas: no concluyente en ninguna dirección; is_processed_sugar=false por definición del flag"})

    # ------------------------------------------------------------ nature: prescriptive / descriptive (Fase 9, B)
    avoid_of = {spec["id"]: bool(spec.get("avoid")) or spec["kind"] == "avoid_placement" for spec in SPECS}
    for r in results:
        r["avoid"] = avoid_of.get(r["id"], False)
        r["nature"] = nature_of(r, r["avoid"])
    nature_split = {"majority_prevalence": MAJORITY_PREVALENCE,
                    "prescriptive": sorted(r["id"] for r in results if r["nature"] == "prescriptive"),
                    "descriptive_kept": sorted(r["id"] for r in results if r["nature"] == "descriptive" and r["status"] == "kept"),
                    "descriptive_other": sorted(r["id"] for r in results if r["nature"] == "descriptive" and r["status"] != "kept")}

    # ------------------------------------------------------------ JSON
    criteria = {"MIN_N": MIN_N, "STRONG_N": STRONG_N, "weak_band": list(WEAK),
                "prescriptive": f"kept (o policy) y seguida en la mayoría de su grupo: prevalencia ≥ {MAJORITY_PREVALENCE:.2f} (patrón evitado ≤ {MAJORITY_PREVALENCE:.2f} en reglas de evitación); "
                                "el resto de las reglas son descriptivas: se informan y explican, no se exigen a cada propuesta",
                "low": f"n_support < {MIN_N}, o lift en [0.8, 1.25], o el efecto ajustado cae en [0.8, 1.25] (confundido)",
                "high": f"n_support ≥ {STRONG_N} y lift ≥ 1.5 (≤ 0.5 en reglas de evitación) que se mantiene tras el ajuste",
                "medium": "resto", "global_high": f"prevalencia ≥ 50 % y n ≥ {STRONG_N}", "global_medium": "prevalencia ≥ 25 %"}
    machine = {"globales": [], "condicionales_objetivo": defaultdict(list), "colocacion": [], "por_fase": defaultdict(list),
               "por_sexo": defaultdict(list), "ansiedad": [], "prioridad_maxima": [], "retiradas": []}
    for r in results:
        entry = {"id": r["id"], "n": r["n_support"], "lift": r["lift"], "adjusted": r["adjusted"], "confidence": r["confidence"]}
        if r["status"] == "retired":
            machine["retiradas"].append({**entry, "criteria": r["criteria"]})
            continue
        if r["status"] == "policy":
            machine["prioridad_maxima"].append(r["id"])
        elif r["section"].startswith("1.") or r["section"].startswith("7."):
            machine["globales"].append(entry)
        elif r["section"].startswith("2."):
            for g in r["condition"]:
                if r.get("by_group") and r["by_group"][g]["n_support"] < MIN_N:
                    machine["retiradas"].append({**entry, "id": f"{r['id']}@{g}", "n": r["by_group"][g]["n_support"],
                                                 "lift": r["by_group"][g]["lift"], "criteria": f"n_support < {MIN_N} en {g}"})
                    continue
                machine["condicionales_objetivo"][g].append(entry)
        elif r["section"].startswith("3."):
            machine["colocacion"].append(entry)
        elif r["section"].startswith("4."):
            machine["por_fase"]["_".join(r["condition"])].append(entry)
        elif r["section"].startswith("5."):
            machine["por_sexo"][r["condition"][0]].append(entry)
        elif r["section"].startswith("6."):
            machine["ansiedad"].append(entry)
        elif r["section"].startswith("8."):
            machine.setdefault("comportamiento", []).append({**entry, "modes": ["reproducir_criterio_profesional", "restriccion_estricta"]})
    machine = {k: (dict(v) if isinstance(v, defaultdict) else v) for k, v in machine.items()}
    # File NAME only, never the path: the absolute path runs through the owner's home directory, and his own first
    # name is in the surname dictionary the PII audit checks against. Writing str(args.diets) put it inside the
    # artefact and the tree audit went from 0 to 1. Provenance is the file, not where the machine happens to keep it.
    out = {"source": Path(args.diets).name, "base_n": N, "tenured_diets": len(tenured), "min_tenure": args.min_tenure,
           "criteria": criteria, "nature_split": nature_split, "rules": results, "machine_readable": machine}
    write_json(args.out_dir / "validated_rules.json", out)

    # ------------------------------------------------------------ Markdown (Spanish)
    goal_dist = Counter(goal_of(r) for r in rows)
    L = ["# Reglas validadas — «Constitución» del preparador (para el RAG) — versión con control de confusores\n",
         f"_Generado por `_tools/build_validated_rules.py` sobre `{args.diets.name}` ({N} dietas limpias, 330 clientes). "
         "El documento curado original (`_meta/reglas_validadas.md`) no se modifica; esta versión recalcula cada regla y añade "
         "**n**, **lift**, **efecto ajustado** y **confianza**._\n",
         "## Criterios de confianza\n",
         f"- **low**: {criteria['low']}.", f"- **high**: {criteria['high']}.", f"- **medium**: {criteria['medium']}.",
         f"- Reglas globales/colocación: high si {criteria['global_high']}; medium si {criteria['global_medium']}; low en otro caso.",
         "- Ajuste: reglas por **sexo** → ratio Mantel-Haenszel F/M estratificado por objetivo; reglas por **objetivo** → MH grupo/resto "
         f"estratificado por sexo; reglas por **fase** → lift recalculado dentro de clientes con ≥{args.min_tenure} dietas ({len(tenured)} dietas).",
         "- **status**: `kept` (se sostiene), `retired` (artefacto o muestra insuficiente), `descriptive` (se informa, no se aplica), `policy` (no medible).",
         f"- **naturaleza**: `prescriptive` ({criteria['prescriptive']}); `descriptive` en otro caso.\n",
         "Distribución de objetivos: " + ", ".join(f"{g} {c}" for g, c in goal_dist.most_common()) + ".\n",
         "## Reparto: prescriptivas frente a descriptivas\n",
         f"Que una regla sostenida esté presente en el 27 % de las dietas de su grupo (`ansiedad_chocolate_o_gelatina`) o en el 15 % (`sustituir_pescado_por_pollo`) "
         f"la hace discriminante del objetivo, no exigible en el 100 % de las propuestas. Por eso la constitución distingue dos naturalezas con el mismo corte que "
         f"aplica la envolvente de plausibilidad (`MAJORITY_PREVALENCE = {MAJORITY_PREVALENCE:.2f}`):\n",
         f"- **Prescriptivas ({len(nature_split['prescriptive'])})**, exigibles a cada propuesta de su grupo: " + ", ".join(f"`{i}`" for i in nature_split["prescriptive"]) + ".",
         f"- **Descriptivas sostenidas ({len(nature_split['descriptive_kept'])})**, con soporte pero minoritarias en su grupo (se informan como evidencia, no se exigen): "
         + ", ".join(f"`{i}`" for i in nature_split["descriptive_kept"]) + ".",
         f"- **Descriptivas por estado ({len(nature_split['descriptive_other'])})** (retiradas, descriptivas o de comportamiento): " + ", ".join(f"`{i}`" for i in nature_split["descriptive_other"]) + ".\n"]
    by_section = defaultdict(list)
    for r in results:
        by_section[r["section"]].append(r)
    for section, rs in by_section.items():
        L.append(f"\n## {section}\n")
        L.append("| id | regla | condición | n_support / n_group | prev. grupo | prev. global | lift | ajustado | confianza | status | naturaleza |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rs:
            cond = ", ".join(r["condition"]) if r["condition"] else "—"
            pg = f"{r['prevalence_in_group']:.1%}" if r.get("prevalence_in_group") is not None else "—"
            pa = f"{r['prevalence_global']:.1%}" if r.get("prevalence_global") is not None else "—"
            L.append(f"| `{r['id']}` | {r['statement']} | {cond} | {r['n_support'] if r['n_support'] is not None else '—'} / {r['n_group'] if r['n_group'] is not None else '—'} | {pg} | {pa} | "
                     f"{r['lift'] if r['lift'] is not None else '—'} | {r['adjusted'] if r['adjusted'] is not None else '—'} | **{r['confidence'] or '—'}** | {r['status']} | {r['nature']} |")
            L.append(f"|  | _{r['criteria']}_ |  |  |  |  |  |  |  |  |  |")
            if r.get("by_group"):
                for g, v in r["by_group"].items():
                    # A goal group can have no support at all (dataset-v3 adds `sin_clasificar`), and then both
                    # prevalence and lift are None. Every other cell in this table already guards for that.
                    pv = f"{v['prevalence']:.1%}" if v.get("prevalence") is not None else "—"
                    lift = v["lift"] if v.get("lift") is not None else "—"
                    L.append(f"|  | ↳ {g} |  | {v['n_support']} / {v['n_group']} | {pv} |  | {lift} |  |  |  |  |")
    L.append("\n## Bloque legible por máquina\n")
    L.append("```json\n" + json.dumps(machine, ensure_ascii=False, indent=1) + "\n```\n")
    (args.out_dir / "validated_rules.md").write_text("\n".join(L), encoding="utf-8", newline="\n")

    kept = sum(1 for r in results if r["status"] == "kept")
    print(json.dumps({"rules": len(results), "kept": kept, "retired": sum(1 for r in results if r["status"] == "retired"),
                      "descriptive": sum(1 for r in results if r["status"] == "descriptive"),
                      "nature": dict(Counter(r["nature"] for r in results)),
                      "confidence": dict(Counter(r["confidence"] for r in results if r["confidence"]))}, ensure_ascii=False))
    for r in results:
        print(f"  {r['status']:11s} {r['confidence'] or '-':6s} n={str(r['n_support']):>4s}/{str(r['n_group']):<5s} lift={r['lift']} adj={r['adjusted']}  {r['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
