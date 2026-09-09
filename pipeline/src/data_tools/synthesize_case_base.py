# -*- coding: utf-8 -*-
"""Genera una BASE DE CASOS SINTÉTICA con la que la aplicación funciona sin un solo dato de una persona real.

Por qué existe: el motor es basado en casos, así que sin base de casos no hay dietas — medido sobre una base vacía, 0
alimentos, 0 reglas y ni se puede dar de alta un cliente. Y el corpus real no puede viajar a un repositorio público:
301 personas, 96,4 % únicas por sexo+edad+altura+fecha de primera consulta, 18.121 parámetros de laboratorio, art. 9
RGPD. La salida son casos INVENTADOS con la forma del corpus, y con eso `docker compose up` sigue entregando dietas.

**De dónde sale la calidad.** No de imitar dietas, que sería copiar: de muestrear el CRITERIO, que es agregado y sí es
publicable. Cada decisión del generador tiene su fuente:

  qué franjas lleva una dieta y cuántas       synthetic_params: slots_per_diet_by_goal · slot_mix_by_goal
  cuántos ítems entran en cada franja         synthetic_params: items_per_slot_by_goal (respaldo: envolvente global)
  qué alimento aparece en qué franja          synthetic_params: foods_by_goal_slot (respaldo: foods_by_slot_fallback)
  en qué unidad y en qué cantidad             plausibility_envelope: units_per_food + quantities p05/p50/p95 (n>=10)
  qué se agrupa como alternativa              plausibility_envelope: alternative_groups + tamaños de grupo medidos
  qué notas lleva                             canonical_notes: las 14 formulaciones canónicas (soporte >=15 dietas)
  dónde va cada suplemento                    supplement_slots: la franja modal de cada suplemento
  quién es el cliente                         synthetic_params: sexo, tramos de edad, altura, actividad, objetivos

Las reglas del profesional no se aplican a mano: están IMPLÍCITAS en esas distribuciones, porque se derivaron de sus
dietas. Lo que sí se comprueba después es el resultado (`SYNTHETIC_QUALITY.md`, Fase 4).

**Invariantes que el generador se exige a sí mismo** y falla si no cumple:
  * ningún seudónimo `CLIENTE_NNN` en la salida; los casos se llaman `SINT_NNN` para que no se puedan confundir;
  * ningún alimento vetado por la restricción declarada del cliente sintético (se lee de las banderas del catálogo);
  * toda cantidad dentro de la banda observada de su (alimento, unidad), y toda unidad observada para ese alimento;
  * ninguna palabra del texto libre del corpus: los gustos salen del catálogo público y el resto de un vocabulario
    inventado que vive en este fichero, a la vista.

Determinista: la misma semilla da los mismos ficheros byte a byte.

Uso:
  python pipeline/src/data_tools/synthesize_case_base.py --aggregates seed/dataset_public --out seed/dataset_public \\
      --clients 300 --seed 20260909
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

PSEUDONYM = re.compile(r"CLIENTE_\d+")
CODE = "SINT_{:03d}"
NON_COMPOSABLE = {"OTHER", "SUPLEMENTOS"}          # OTHER es dato, no franja; los suplementos se colocan aparte
# El orden canónico del día. Las franjas se eligen por frecuencia y se ORDENAN por aquí, porque una dieta que empieza
# por la cena no es una dieta: es un conjunto de comidas.
SLOT_ORDER = ("RECIEN LEVANTADO", "DESAYUNO", "MEDIA MAÑANA", "ALMUERZO", "ANTES DE ENTRENAR",
              "MITAD DE ENTRENAMIENTO", "DESPUES DE ENTRENAR", "COMIDA", "MEDIA TARDE", "MERIENDA",
              "CENA", "ANTES DE DORMIR")
# Vocabulario INVENTADO para el texto libre. Ni una palabra sale del corpus.
SPORTS = ("gimnasio (fuerza)", "running", "ciclismo", "natación", "crossfit", "pádel", "boxeo", "fútbol sala",
          "escalada", "triatlón popular", "spinning", "pilates", "baloncesto", "caminar")
WORK = ("9:00-18:00", "8:00-15:00", "turnos rotativos", "turno de noche", "jornada partida", "13:00-21:00", "estudiante")
TRAIN_TIME = ("07:00-08:15", "13:15-14:00", "17:00-18:30", "19:00-20:30", "20:30-21:45", "10:00-11:00")
ACHIEVEMENTS = ("liga local", "media maratón terminada", "10 km por debajo de 50 min", "campeonato autonómico",
                "marcha cicloturista de 100 km", "primer torneo amateur")
BODY_TYPES = ("ectomorfo", "mesomorfo", "endomorfo")
GOAL_TEXTS = {                                   # prosa neutra, escrita aquí, no tomada de sus documentos
    "definicion_grasa": "Plan de definición: reducir grasa manteniendo la masa muscular.",
    "volumen_masa": "Plan de volumen: ganar masa muscular con la mínima ganancia de grasa.",
    "ayuno_intermitente": "Plan con ayuno intermitente 16/8 adaptado a los horarios de entrenamiento.",
    "cetosis_keto": "Plan cetogénico controlado, con hidratos muy limitados.",
}
UNIT_ROUND = {"g": 5, "ml": 10}                  # a qué múltiplo se redondea cada unidad
# TECHO DE LAS UNIDADES QUE SE CUENTAN, copiado del dominio (`quantity_policy.UNIT_CEILING`). No es una elección
# estética: el motor considera IMPOSIBLE un recuento por encima de su techo y lo REINTERPRETA como gramos («200
# unidades de cafeína» -> «200 g»), que es la corrección correcta para un extractor que perdió la unidad. El corpus
# tiene esos artefactos —la banda de `cafeína|unidad` llega a p50 = 100— y una base sintética que los reprodujera
# haría que la propuesta sirviera una unidad que ese alimento nunca tuvo. Aquí no se generan artefactos.
COUNT_CEILING = {"unidad": 20, "cucharada": 12, "cucharadita": 12, "loncha": 12, "diente": 10, "puñado": 6,
                 "cazo": 6, "cápsula": 12, "lata": 6, "chorrito": 6}
# Exponente con el que se concentra el reparto de alimentos por franja. Muestrear proporcional al conteo real
# desparrama la elección entre los 228 canónicos, y entonces el compositor —que solo conserva lo que aparece en al
# menos el 35 % de los 20 vecinos— entrega franjas de dos líneas. El profesional NO trabaja así: reutiliza un
# repertorio corto. Medido: con proporcional, 2,93 ítems por franja frente a 5,10 del corpus real; con este
# exponente y el repertorio por cliente, la forma se recupera.
CONCENTRATION = 2.0
# Cuántos alimentos distintos maneja un cliente en una franja. El repertorio se sortea UNA VEZ por cliente y todas
# sus versiones se componen de ahí: eso es lo que hace que las versiones de una persona se parezcan entre sí (y que
# la rotación tenga de dónde rotar) y que dos personas con el mismo objetivo coincidan.
# Medido: con (5, 9) la rotación se queda en 0,300 de novedad y su banda es [0,35, 0,60] — el repertorio no le daba
# de dónde rotar. Con (8, 14) hay margen sin desparramar el consenso.
REPERTOIRE_PER_SLOT = (8, 14)
# Una familia que él pone en MÁS DE LA MITAD de las veces que usa una franja no es un adorno: es la estructura de esa
# comida. Si el reparto sintético la deja fuera, el consenso de los vecinos tampoco la trae y la capa de plausibilidad
# lo canta con razón («CENA · faltan grupos exigidos: VEGETABLE»). Así que por encima de este corte la familia se
# GARANTIZA en el repertorio y en cada dieta. El corte es la mayoría simple, el mismo que usa el motor de reglas.
FAMILY_IS_STRUCTURAL = 0.5
# Y además hay una estructura que NO es estadística, es de dominio: `slot_composition_policy.REQUIRED_GROUPS` exige
# proteína y verdura en la cena, proteína en la comida e hidrato en el desayuno, y la capa de plausibilidad lo
# comprueba. Los casos sintéticos tienen que llevarla, o el consenso entrega cenas sin verdura y la violación es
# legítima. Se escribe aquí en vez de importarse porque este script vive fuera del hexágono (no depende de backend/).
REQUIRED_GROUPS = {"CENA": ("PROTEIN", "VEGETABLE"), "COMIDA": ("PROTEIN",), "DESAYUNO": ("CARB",)}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pick(rng: random.Random, weights: dict) -> str:
    """Una clave según su peso. Las claves llegan como cadenas (vienen de JSON)."""
    items = [(k, float(v)) for k, v in weights.items() if float(v) > 0]
    total = sum(w for _, w in items)
    x = rng.random() * total
    for k, w in items:
        x -= w
        if x <= 0:
            return k
    return items[-1][0]


def from_spread(rng: random.Random, s: dict, lo: float | None = None, hi: float | None = None) -> float:
    """Un valor dentro de un p05/p50/p95 medido, con la moda en la mediana (triangular, no uniforme)."""
    a, m, b = float(s.get("p05", s.get("min", 0))), float(s.get("p50", 0)), float(s.get("p95", s.get("max", 0)))
    a, b = (min(a, m), max(b, m))
    if a == b:
        v = a
    else:
        v = rng.triangular(a, b, m)
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


class Generator:
    def __init__(self, aggregates: Path, params: Path, seed: int):
        self.rng = random.Random(seed)
        self.seed = seed
        self.catalog = {f["id"]: f for f in load(aggregates / "foods.json")["foods"]}
        self.env = load(aggregates / "plausibility_envelope.json")
        self.notes = [t for t in load(aggregates / "canonical_notes.json")["themes"] if t.get("canonical")]
        self.supplements = load(aggregates / "supplement_slots.json").get("placements", {})
        self.P = load(params)
        self.D = self.P["derived"]
        self.restr_mix = self.P["modelled"]["restriction_kinds"]
        self.quant = self.env["quantities"]
        self.units = self.env["units_per_food"]
        self.group_sizes = self.D["alternative_group_size"]
        # alimento -> banderas, para poder vetar por restricción sin preguntarle a nadie
        self.flags = {fid: f.get("flags", {}) for fid, f in self.catalog.items()}
        # UNIDAD MODAL POR FAMILIA. El compositor, al rotar, cambia la especie DENTRO de la familia (arroz por pasta)
        # y se queda con la unidad de la que sale. Si en los casos el arroz va en gramos y la pasta en «unidad», la
        # propuesta acaba con una unidad que ese alimento nunca tuvo. Él no escribe así: la familia lleva su unidad.
        # Se calcula con los recuentos de la propia envolvente, no a mano.
        familia_unidades: dict[str, Counter] = defaultdict(Counter)
        for fid, food in self.catalog.items():
            for u, n in (self.units.get(str(fid)) or {}).items():
                if f"{fid}|{u}" in self.quant:
                    familia_unidades[food["family"]][u] += int(n)
        self.family_unit = {fam: c.most_common(1)[0][0] for fam, c in familia_unidades.items() if c}

    # ---------------------------------------------------------------- perfiles
    def profile(self, n: int, forzar_objetivo: str | None = None) -> dict:
        rng, D = self.rng, self.D
        code = CODE.format(n)
        sex = pick(rng, D["sex"])
        bucket = pick(rng, D["age_bucket"])
        age = round(from_spread(rng, D["age_in_bucket"].get(bucket, {"p05": 25, "p50": 32, "p95": 45})))
        h = D["height_cm_by_sex"][sex]
        height = int(round(min(max(rng.gauss(h["mean"], max(h["sd"], 3.0)), h["min"]), h["max"])))
        goal = forzar_objetivo or pick(rng, D["goal_mix"])
        w = D["scale"]["weight_kg_by_sex"][sex]
        weight = round(min(max(rng.gauss(w["mean"], max(w["sd"], 5.0)), w["min"]), w["max"]), 1)
        flags = {k: rng.random() < v for k, v in D["health_flags_share"].items()}
        kinds: list[str] = []
        if flags["has_intolerances"]:
            kinds.append(pick(rng, {k: v for k, v in self.restr_mix.items() if k in ("contains_lactose", "contains_gluten", "contains_soy")}))
        if flags["has_allergies"]:
            kinds.append(pick(rng, {k: v for k, v in self.restr_mix.items() if k not in ("contains_lactose", "contains_gluten", "contains_soy")}))
        n_diets = int(pick(rng, D["diets_per_client"]))
        gustos = [self.catalog[fid]["canonical_name"] for fid in rng.sample(sorted(self.catalog), 3)]
        aversiones = [self.catalog[fid]["canonical_name"] for fid in rng.sample(sorted(self.catalog), 2)]
        return {
            "client_code": code, "sex": sex, "age": float(age), "age_bucket": bucket, "height_cm": float(height),
            "weight_kg": weight, "initial_weight_kg": round(weight + rng.uniform(-4, 6), 1), "target_weight_kg": None,
            "waist_cm": round(weight * (0.98 if sex == "M" else 1.05) + rng.uniform(-8, 8), 1),
            "neck_cm": round((39.0 if sex == "M" else 32.0) + rng.uniform(-3, 4), 1),
            "wrist_cm": round((17.0 if sex == "M" else 15.5) + rng.uniform(-1.5, 1.5), 1),
            "hip_cm": (round(weight * 1.15 + rng.uniform(-6, 6), 1) if sex == "F" else None),
            "body_type": pick(rng, D["body_type"]) if D["body_type"] and rng.random() < 0.5 else None,
            "activity_level": int(pick(rng, D["activity_level"])), "activity_level_reported": rng.random() < 0.5,
            "is_athlete": rng.random() < D["is_athlete_share"],
            "goals": goal, "sport": rng.choice(SPORTS), "training_time": rng.choice(TRAIN_TIME),
            "sport_achievements": rng.choice(ACHIEVEMENTS) if rng.random() < 0.12 else None,
            "liked_foods": ", ".join(gustos), "disliked_foods": ", ".join(aversiones),
            "food_vices": None, "smokes": rng.random() < 0.15, "drinks_alcohol": rng.random() < 0.35,
            "work_schedule": rng.choice(WORK), "training_schedule": rng.choice(TRAIN_TIME),
            "sleep_hours": rng.choice([6.0, 7.0, 7.5, 8.0]), "own_supplements": None,
            "first_consultation_date": None,
            "has_allergies": flags["has_allergies"], "has_intolerances": flags["has_intolerances"],
            "has_medical_restrictions": flags["has_medical_restrictions"],
            "has_medication_or_pathology": rng.random() < 0.02, "has_surgeries": rng.random() < 0.2,
            "has_injuries": rng.random() < 0.3,
            "diet_count": n_diets, "diet_count_raw": n_diets, "diet_count_stored": n_diets,
            "empty_profile": False, "unmapped": False, "suspicious_demographics": False,
            "field_carryover_suspected": False, "carryover_fields": [], "redacted_public_fields": [],
            "extra_fields": {}, "questionnaire_count": 1, "has_scale_trajectory": False,
            "scale_reading_count": 0, "lab_report_count": 0, "field_sources": {},
            "_goal": goal, "_kinds": kinds, "_weight": weight,          # privado del generador, se quita al escribir
        }

    # ------------------------------------------------------------------ dietas
    def vetoed(self, kinds: list[str]) -> set[int]:
        return {fid for fid, fl in self.flags.items() if any(fl.get(k) for k in kinds)}

    def slots_for(self, goal: str) -> list[str]:
        rng, D = self.rng, self.D
        mix = {s: w for s, w in D["slot_mix_by_goal"].get(goal, {}).items() if s not in NON_COMPOSABLE}
        if not mix:
            mix = {s: 1.0 for s in ("DESAYUNO", "COMIDA", "MERIENDA", "CENA")}
        banda = dict(D["slots_per_diet_by_goal"].get(goal, {"p05": 4, "p50": 6, "p95": 9}))
        banda["p50"] = max(3.0, float(banda["p50"]) - 2)
        n = int(round(from_spread(rng, banda, lo=3, hi=min(7, len(mix)))))
        elegidas: set[str] = set()
        intentos = 0
        while len(elegidas) < n and intentos < 200:
            elegidas.add(pick(rng, mix))
            intentos += 1
        return [s for s in SLOT_ORDER if s in elegidas] or ["DESAYUNO", "COMIDA", "CENA"]

    def foods_for(self, goal: str, slot: str, veto: set[int]) -> dict:
        """Reparto de alimentos de esa franja para ese objetivo, ya concentrado y sin lo vetado."""
        tabla = self.D["foods_by_goal_slot"].get(f"{goal}|{slot}") or self.D["foods_by_slot_fallback"].get(slot) or {}
        libres = {k: float(v) ** CONCENTRATION for k, v in tabla.items() if int(k) not in veto and int(k) in self.catalog}
        if libres:
            return libres
        return {str(fid): 1.0 for fid in sorted(self.catalog) if fid not in veto}   # último recurso: el catálogo

    def structural_families(self, goal: str, slot: str) -> list[str]:
        share = self.D["families_by_goal_slot"].get(f"{goal}|{slot}", {})
        return [f for f, v in share.items() if float(v) >= FAMILY_IS_STRUCTURAL]

    def group_of(self, fid: int) -> tuple[str, ...]:
        f = self.catalog[fid]
        return tuple(g for g in (f.get("group"), f.get("secondary_group")) if g)

    def ensure_groups(self, goal: str, slot: str, elegidos: list[int], tabla: dict) -> list[int]:
        """La estructura de dominio: si a la cena le falta proteína o verdura, entra. Sustituyendo, no engordando."""
        for grupo in REQUIRED_GROUPS.get(slot, ()):
            if any(grupo in self.group_of(f) for f in elegidos):
                continue
            candidatos = {k: v for k, v in tabla.items() if grupo in self.group_of(int(k))}
            if not candidatos:
                candidatos = {str(fid): 1.0 for fid in sorted(self.catalog) if grupo in self.group_of(fid)}
            if not candidatos:
                continue
            nuevo = int(pick(self.rng, candidatos))
            sobrantes = [j for j, f in enumerate(elegidos)
                         if not any(g in REQUIRED_GROUPS.get(slot, ()) for g in self.group_of(f))]
            if sobrantes:
                elegidos[sobrantes[-1]] = nuevo
            else:
                elegidos.append(nuevo)
        return elegidos

    def repertoire(self, prof: dict, slots: list[str]) -> dict[str, dict]:
        """El repertorio del cliente: por franja, los pocos alimentos con los que se le compone TODA su serie."""
        rng, veto = self.rng, self.vetoed(prof["_kinds"])
        out: dict[str, dict] = {}
        for slot in slots:
            tabla = self.foods_for(prof["_goal"], slot, veto)
            n = rng.randint(*REPERTOIRE_PER_SLOT)
            elegidos: dict[str, float] = {}
            intentos = 0
            while len(elegidos) < min(n, len(tabla)) and intentos < 400:
                k = pick(rng, tabla)
                elegidos[k] = tabla[k]
                intentos += 1
            elegidos = elegidos or dict(tabla)
            for familia in self.structural_families(prof["_goal"], slot):
                if any(self.catalog[int(k)]["family"] == familia for k in elegidos):
                    continue
                candidatos = {k: v for k, v in tabla.items() if self.catalog[int(k)]["family"] == familia}
                if candidatos:
                    k = pick(rng, candidatos)
                    elegidos[k] = candidatos[k]
            for grupo in REQUIRED_GROUPS.get(slot, ()):
                if any(grupo in self.group_of(int(k)) for k in elegidos):
                    continue
                candidatos = {k: v for k, v in tabla.items() if grupo in self.group_of(int(k))}
                if not candidatos:
                    candidatos = {str(fid): 1.0 for fid in sorted(self.catalog)
                                  if grupo in self.group_of(fid) and fid not in veto}
                if candidatos:
                    k = pick(rng, candidatos)
                    elegidos[k] = candidatos[k]
            out[slot] = elegidos
        return out

    def observed_units(self, fid: int) -> set[str]:
        """Unidades de ese alimento que la envolvente respalda con banda propia. Lo demás no existe para el motor."""
        return {u for u in (self.units.get(str(fid)) or {}) if f"{fid}|{u}" in self.quant}

    def quantity(self, fid: int) -> tuple[float, str]:
        """Unidad observada para ese alimento y cantidad dentro de su banda. Si no hay banda, gramos con mediana 100."""
        rng = self.rng
        opciones = {u: n for u, n in (self.units.get(str(fid)) or {}).items() if f"{fid}|{u}" in self.quant}
        if not opciones:
            return 100.0, "g"
        modal = self.family_unit.get(self.catalog[fid]["family"])
        unit = modal if modal in opciones else pick(rng, opciones)
        band = self.quant[f"{fid}|{unit}"]
        lo, hi = float(band["p05"]), float(band["p95"])
        techo = COUNT_CEILING.get(unit)
        if techo is not None:                      # una unidad que se cuenta: por debajo de su techo, siempre
            hi = min(hi, float(techo))
            lo = min(lo, hi)
        v = from_spread(rng, band, lo=lo, hi=hi)
        # Redondear a un múltiplo bonito (5 g, 10 ml) puede sacar el valor de una banda estrecha -- «12 g de canela»
        # con banda [12, 18] se iría a 10. Así que se elige el múltiplo más cercano QUE SIGA DENTRO, y si la banda es
        # más estrecha que el paso, se queda la mediana observada. Nadie escribe «13,7 g», pero tampoco 10 si el
        # profesional nunca baja de 12.
        step = UNIT_ROUND.get(unit)
        if step:
            k0, k1 = int(lo // step), int(hi // step) + 1
            candidatos = [c for c in (k * step for k in range(k0, k1 + 1)) if lo <= c <= hi]
            v = min(candidatos, key=lambda c: abs(c - v)) if candidatos else round(float(band["p50"]), 1)
        else:
            v = round(v)
            if not (lo <= v <= hi):
                v = round(float(band["p50"]), 1)
        return float(v), unit

    def diet(self, prof: dict, version: int, day: date) -> tuple[dict, list[dict], list[dict]]:
        rng, goal = self.rng, prof["_goal"]
        code = prof["client_code"]
        diet_id = f"{code}::v{version:02d}"
        slots = prof["_slots"]                    # las mismas franjas en todas sus versiones: es la misma persona
        items: list[dict] = []
        meals: list[dict] = []
        meals_map: dict[str, int] = {}
        for pos, slot in enumerate(slots):
            s = dict(self.D["items_per_slot_by_goal"].get(f"{goal}|{slot}") or self.env["items_per_slot"].get(slot) or {"p05": 2, "p50": 4, "p95": 7})
            techo = min(float(s.get("p95", 7)), 12.0)          # p95 de COMIDA en volumen es 23: eso es su cola, no su norma
            s["p50"] = min(techo, float(s["p50"]) + 2)
            n_items = int(round(from_spread(rng, {**s, "p95": techo}, lo=1, hi=techo)))
            tabla = prof["_repertoire"][slot]
            elegidos: list[int] = []
            while len(elegidos) < n_items:
                fid = int(pick(rng, tabla))
                if fid in elegidos and rng.random() < 0.75:          # repetir en la misma franja es raro, no imposible
                    continue
                elegidos.append(fid)
                if len(tabla) <= len(set(elegidos)):
                    break
            estructurales = self.structural_families(goal, slot)
            for familia in estructurales:
                if any(self.catalog[f]["family"] == familia for f in elegidos):
                    continue
                candidatos = {k: v for k, v in tabla.items() if self.catalog[int(k)]["family"] == familia}
                if not candidatos:
                    continue
                nuevo = int(pick(rng, candidatos))
                sobrantes = [j for j, f in enumerate(elegidos)
                             if self.catalog[f]["family"] not in estructurales]
                if sobrantes:
                    elegidos[sobrantes[-1]] = nuevo
                else:
                    elegidos.append(nuevo)
            elegidos = self.ensure_groups(goal, slot, elegidos, tabla)
            # Agrupación como alternativas, con el tamaño medido. Y una condición que no es cosmética: los miembros de
            # un grupo tienen que COMPARTIR UNIDAD observada. El compositor, al rotar, sustituye un alimento por otro
            # de su grupo y arrastra la unidad del que sale; si el grupo mezcla «unidad» con «g», la propuesta acaba
            # sirviendo «cafeína en g», que la envolvente marca con razón (`unseen_unit`). Es un defecto del motor ya
            # declarado (DISCUSSION §9.1) y aquí basta no darle la ocasión.
            grupos: dict[int, str] = {}
            i = 0
            g = 0
            while i < len(elegidos):
                tam = int(pick(rng, self.group_sizes)) if self.group_sizes else 1
                tam = max(1, min(tam, len(elegidos) - i))
                miembros = elegidos[i:i + tam]
                comparten = set.intersection(*(self.observed_units(f) for f in miembros)) if tam > 1 else set()
                if tam > 1 and comparten and rng.random() < self.D["items_in_a_group_share"] + 0.25:
                    g += 1
                    for j in range(i, i + tam):
                        grupos[j] = f"{diet_id}|{slot}|g{g}"
                i += tam
            lineas = []
            for idx, fid in enumerate(elegidos):
                food = self.catalog[fid]
                qty, unit = self.quantity(fid)
                texto = f"{qty:g} {unit} de {food['canonical_name']}" if unit not in ("unidad",) else f"{qty:g} {food['canonical_name']}"
                lineas.append(texto)
                items.append({
                    "diet_id": diet_id, "meal_slot": slot, "position": pos, "component_index": idx,
                    "food_id": fid, "canonical_name": food["canonical_name"], "family": food["family"],
                    "group": food["group"], "normalized_key": food["canonical_name"], "raw_text": texto,
                    "food_text": food["canonical_name"], "quantity": qty, "unit": unit, "raw_unit": None,
                    "alternative_group": grupos.get(idx), "compound_item": False, "compound_group": None,
                    "unmapped": False, "unmapped_reason": None, "generic_assumption": False, "note": None,
                })
            meals_map[slot] = len(elegidos)
            meals.append({"slot": slot, "position": pos, "text": "\n".join(lineas), "item_count": len(elegidos)})

        n_notes = int(round(from_spread(rng, self.D["notes_per_diet"], lo=0, hi=8)))
        notas = [t["canonical"] for t in rng.sample(self.notes, min(n_notes, len(self.notes)))]
        # El TEXTO es el documento que el profesional entrega, no una lista de la compra: lleva su encabezado y sus
        # notas al final. Y no es cosmetico -- `test_texts_are_much_shorter_than_the_original_and_bounded` comprueba
        # una propiedad de diseno de E3.1: lo que se INDEXA es mucho mas corto que el documento. Con la lista pelada
        # la relacion se invertia (indice 759 frente a documento 572, ratio 1,33) mientras en el corpus real es 843
        # frente a 1.174 (0,72). Lo cazo `verify_clean_clone` sobre un clon del arbol publico.
        bloques = [f"OBJETIVO: {GOAL_TEXTS[goal]}", f"Fecha: {day.isoformat()}   -   Version {version}"]
        bloques += [f"{m['slot']}" + chr(10) + m["text"] for m in meals]
        if notas:
            bloques.append("NOTAS" + chr(10) + chr(10).join(f"- {n}" for n in notas))
        texto = (chr(10) * 2).join(bloques)
        meta = {
            "client_code": code, "diet_version": version, "goal": goal, "goals": [goal], "method": None, "methods": [],
            "goal_inferred": False, "goal_declared": GOAL_TEXTS[goal], "goal_is_compound": False,
            "goal_uncovered_purposes": [], "goal_text": GOAL_TEXTS[goal], "doc_date": day.isoformat(),
            "meal_count": len(meals), "item_count": len(items), "note_count": len(notas),
            "source_sha1": hashlib.sha1(diet_id.encode()).hexdigest(), "source_rel": f"sintetico/{diet_id}.md",
            "unmapped_slots": {}, "day_variants": [], "raw_slot_labels": {},
            "sex": prof["sex"], "age": prof["age"], "age_bucket": prof["age_bucket"],
            "activity_level": prof["activity_level"], "activity_level_reported": prof["activity_level_reported"],
            "has_intolerances": prof["has_intolerances"], "has_allergies": prof["has_allergies"],
            "suspicious_demographics": False, "is_athlete": prof["is_athlete"], "shared_diet": False,
            "shared_diet_signals": [], "template_group_id": None, "template_clients": [],
            "goal_content_predicted": goal, "goal_suspect": False, "goal_evidence": [],
        }
        diet = {"id": diet_id, "meta": meta, "meals": meals_map, "notes": notas, "text": texto,
                "item_variants": [], "raw_slot_labels": {}}
        meal_rows = [{"id": f"{diet_id}::{m['slot']}", "text": m["text"],
                      "meta": {**meta, "diet_id": diet_id, "meal_slot": m["slot"], "slot": m["slot"],
                               "item_count": m["item_count"]}} for m in meals]
        return diet, meal_rows, items

    # ----------------------------------------------------------- báscula y laboratorio
    def scale_rows(self, prof: dict, last_day: date) -> list[dict]:
        rng, D = self.rng, self.D["scale"]
        if rng.random() > D["clients_with_scale_share"]:
            return []
        n = int(round(from_spread(rng, D["readings_per_client"], lo=1, hi=24)))
        gap = max(7, int(round(from_spread(rng, D["days_between_readings"], lo=7, hi=120))))
        sex = prof["sex"]
        fat0 = from_spread(rng, D["fat_pct_by_sex"][sex])
        peso = prof["_weight"]
        deriva = (-0.4 if prof["_goal"] in ("definicion_grasa", "cetosis_keto") else 0.4)
        filas = []
        for k in range(n - 1, -1, -1):
            w = round(peso - deriva * k, 1)
            fat = round(max(4.0, min(55.0, fat0 - 0.5 * deriva * k)), 1)
            lean = w * (1 - fat / 100)
            bone = round(lean * 0.055, 2)
            filas.append({
                "client_code": prof["client_code"], "date": (last_day - timedelta(days=gap * k)).isoformat(),
                "source": "bascula", "height_cm": int(prof["height_cm"]), "age": int(prof["age"]),
                "is_male": sex == "M", "weight_kg": w, "fat_pct": fat,
                "hydration_pct": round(45.0 + (100 - fat) * 0.155, 2), "bone_mass_kg": bone,
                "muscle_mass_kg": round(lean - bone, 2),
                "physique_rating": 3 if fat <= (15 if sex == "M" else 24) else (5 if fat <= (23 if sex == "M" else 32) else 7),
                "visceral_fat_rating": round(fat / (2.2 if sex == "M" else 3.2), 1),
                "metabolic_age": int(round(prof["age"] + (fat - (15 if sex == "M" else 24)) / 2)),
                "basal_met_kcal": str(int(round(10 * w + 6.25 * prof["height_cm"] - 5 * prof["age"] + (5 if sex == "M" else -161)))),
            })
        return filas

    def lab_rows(self, prof: dict, last_day: date) -> list[dict]:
        rng, L = self.rng, self.D["labs"]
        if rng.random() > L["clients_with_labs_share"]:
            return []
        n_rep = int(round(from_spread(rng, L["reports_per_client"], lo=1, hi=4)))
        catalogo = L["markers"]
        filas = []
        for r in range(n_rep):
            day = last_day - timedelta(days=90 * r + rng.randint(0, 20))
            cuantos = rng.randint(8, min(16, len(catalogo)))
            marcadores = rng.sample(catalogo[:60], cuantos) if len(catalogo) >= 60 else rng.sample(catalogo, cuantos)
            valores = []
            for m in marcadores:
                sd = max(m["sd"], abs(m["mean"]) * 0.05, 0.1)
                v = rng.gauss(m["mean"], sd)
                if rng.random() < 0.15:                                  # algunos fuera de rango, para que se vea el color
                    v = m["mean"] + rng.choice([-1, 1]) * sd * rng.uniform(2.0, 3.0)
                valores.append({"indicator": m["marker"], "value": round(v, 2), "unit": m["unit"],
                                "range_low": m["ref_low"], "range_high": m["ref_high"]})
            filas.append({"client_code": prof["client_code"], "source_type": "laboratorio",
                          "report_sha1": hashlib.sha1(f"{prof['client_code']}|{r}|{self.seed}".encode()).hexdigest(),
                          "report_date": day.isoformat(), "level": 1, "level_reason": "informe sintético",
                          "values_unreliable": False, "extractable_chars": 0, "values": valores, "nearest_diets": []})
        return filas

    # ------------------------------------------------------------------- todo
    def run(self, n_clients: int, out: Path, last_day: date, min_por_objetivo: int = 30) -> dict:
        profiles, diets, meals, items, scale, labs = [], [], [], [], [], []
        kinds_por_cliente: dict[str, list[str]] = {}
        # SUELO POR OBJETIVO, y es una decisión de modelado declarada: la mezcla real de objetivos daría ~7 clientes
        # de `cetosis_keto` en 300, y con menos de k=20 clientes distintos el motor sirve en banda «declarando»
        # SIEMPRE. En una base de demostración eso es un aviso permanente que no dice nada del sistema, así que cada
        # objetivo servible arranca con un cupo mínimo y el resto se reparte por la mezcla medida.
        cupos = [g for g in self.D["goal_mix"] for _ in range(min_por_objetivo)]
        self.rng.shuffle(cupos)
        for i in range(1, n_clients + 1):
            p = self.profile(i, forzar_objetivo=cupos.pop() if cupos else None)
            kinds_por_cliente[p["client_code"]] = list(p["_kinds"])
            p["_slots"] = self.slots_for(p["_goal"])
            p["_repertoire"] = self.repertoire(p, p["_slots"])
            dias = [last_day - timedelta(days=45 * k + self.rng.randint(0, 15)) for k in range(p["diet_count"])][::-1]
            for v, day in enumerate(dias, start=1):
                d, mr, it = self.diet(p, v, day)
                diets.append(d); meals.extend(mr); items.extend(it)
            s = self.scale_rows(p, last_day)
            lb = self.lab_rows(p, last_day)
            scale.extend(s); labs.extend(lb)
            p["has_scale_trajectory"] = len(s) > 1
            p["scale_reading_count"] = len(s)
            p["lab_report_count"] = len(lb)
            profiles.append({k: v for k, v in p.items() if not k.startswith("_")})

        arque: dict[tuple, dict] = {}
        por_cliente = {p["client_code"]: p for p in profiles}
        for d in diets:
            p = por_cliente[d["meta"]["client_code"]]
            k = (p["sex"], p["age_bucket"], d["meta"]["goal"])
            a = arque.setdefault(k, {"sex": k[0], "age_bucket": k[1], "goal": k[2], "diet_count": 0, "clients": set()})
            a["diet_count"] += 1
            a["clients"].add(p["client_code"])
        archetypes = [{**a, "clients": sorted(a["clients"]), "client_count": len(a["clients"])}
                      for a in (dict(v) for v in arque.values())]

        self._check(profiles, diets, items, kinds_por_cliente)
        out.mkdir(parents=True, exist_ok=True)
        def jl(name, rows):
            with (out / name).open("w", encoding="utf-8", newline="\n") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            return round((out / name).stat().st_size / 1024, 1)
        tam = {
            "profiles.jsonl": jl("profiles.jsonl", profiles), "diets.jsonl": jl("diets.jsonl", diets),
            "meals.jsonl": jl("meals.jsonl", meals), "diet_items.jsonl": jl("diet_items.jsonl", items),
            "body_measurements.jsonl": jl("body_measurements.jsonl", scale), "lab_results.jsonl": jl("lab_results.jsonl", labs),
            "body_measurements_followup.jsonl": jl("body_measurements_followup.jsonl", []),
        }
        (out / "archetypes.json").write_text(json.dumps(archetypes, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        tam["archetypes.json"] = round((out / "archetypes.json").stat().st_size / 1024, 1)
        (out / "SYNTHETIC.json").write_text(json.dumps({
            "generated_by": "synthesize_case_base.py", "seed": self.seed, "clients": n_clients,
            "reference_day": last_day.isoformat(), "params": "synthetic_params.json",
            "what_this_is": ("Base de casos INVENTADA con la forma del corpus. Ninguna persona real, ninguna fecha real. "
                             "Los criterios (reglas, catálogo, bandas de cantidad, notas) SÍ son los medidos del "
                             "profesional; los casos no son suyos, así que las cifras de fidelidad de la memoria no se "
                             "reproducen desde aquí."),
            "counts": {"profiles": len(profiles), "diets": len(diets), "meals": len(meals), "items": len(items),
                       "scale_readings": len(scale), "lab_reports": len(labs), "archetypes": len(archetypes)},
        }, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        return {"out": str(out), "sizes_kb": tam, "counts": {"profiles": len(profiles), "diets": len(diets),
                "meals": len(meals), "items": len(items), "scale": len(scale), "labs": len(labs), "archetypes": len(archetypes)}}

    def _check(self, profiles, diets, items, kinds_por_cliente: dict[str, list[str]]):
        blob = json.dumps([profiles[:5], diets[:2]], ensure_ascii=False)
        if PSEUDONYM.search(blob):
            raise SystemExit("ABORTADO: la salida lleva seudónimos del corpus")
        veto_de = {p["client_code"]: self.vetoed(kinds_por_cliente.get(p["client_code"], [])) for p in profiles}
        malos = [(i["diet_id"], i["food_id"]) for i in items
                 if i["food_id"] in veto_de.get(i["diet_id"].split("::")[0], set())]
        if malos:
            raise SystemExit(f"ABORTADO: {len(malos)} componentes vetados por la restricción del cliente sintético")
        fuera = []
        for i in items:
            band = self.quant.get(f"{i['food_id']}|{i['unit']}")
            if band and not (band["p05"] - 1e-9 <= i["quantity"] <= band["p95"] + 1e-9):
                fuera.append((i["diet_id"], i["food_id"], i["quantity"]))
        if fuera:
            raise SystemExit(f"ABORTADO: {len(fuera)} cantidades fuera de la banda observada")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aggregates", type=Path, required=True, help="árbol con los agregados públicos")
    ap.add_argument("--params", type=Path, default=None, help="synthetic_params.json (por defecto, dentro de --aggregates)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--clients", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--reference-day", default="2026-09-01")
    ap.add_argument("--min-per-goal", type=int, default=30, help="cupo mínimo de clientes por objetivo servible")
    args = ap.parse_args()
    gen = Generator(args.aggregates, args.params or (args.aggregates / "synthetic_params.json"), args.seed)
    report = gen.run(args.clients, args.out, date.fromisoformat(args.reference_day), args.min_per_goal)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
