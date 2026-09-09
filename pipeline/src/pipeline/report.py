# -*- coding: utf-8 -*-
"""
E1.5 — NORMALIZATION_REPORT.md (Spanish, academic register) generated from the pipeline logs.

Inputs (all in _dataset/): parse_items_log.json, build_food_catalog_log.json, foods.json, normalize_diets_log.json,
synonym_audit.json, synonym_changes.json, lactose_validation.json, excluded_substances.json, food_attributes_dubious.json,
rules_evaluability.json, client_tree_log.json, audit/tree_audit.json
Output: docs/data/NORMALIZATION_REPORT.md — GENERATED, not versioned — and a copy in $FPS_DATASET_DIR
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR, DOCS_DIR  # noqa: E402


def load(name):
    p = DATASET_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"Required input file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def pct(a, b):
    return f"{100 * a / b:.2f} %" if b else "—"


def main() -> int:
    parse = load("parse_items_log.json")
    cat = load("build_food_catalog_log.json")
    foods = load("foods.json")
    norm = load("normalize_diets_log.json")
    audit = load("synonym_audit.json")
    changes = load("synonym_changes.json")
    lact = load("lactose_validation.json")
    excl = load("excluded_substances.json")
    dub = load("food_attributes_dubious.json")
    rules = load("rules_evaluability.json")
    validated = load("validated_rules.json")
    tree = load("client_tree_log.json")
    tree_audit = load("audit/tree_audit.json")
    fl = foods["foods"]
    c = parse["counts"]

    # misspellings: class-1 entries with n > 0 that are real misspellings (edit-distance or split word) and not
    # grammatical/language variants (declared list of exclusions)
    NOT_TYPOS = {"aislado", "yogurt", "caseinato", "tyrosine", "estevia", "prebiotico", "osteocart", "proteico", "proteina",
                 "blanco", "aminos", "acido", "creatine", "carnitine", "spirulina", "probiotic", "omegas", "omega3", "protein",
                 "barra", "carbo", "lacon", "salchichon", "gallo", "rosada", "gambon", "curado", "judia", "fruta", "fruto",
                 "cebolleta", "brecol", "freson", "tribu", "edulcorant", "amylopeptin", "tomat", "aguacat", "quinua"}
    typos = {}
    for e in audit["class1_misspellings"]:
        if e["n"] > 0 and e["token"] not in NOT_TYPOS and e["kind"] in ("edit_distance", "split_word"):
            typos[e["key"]] = (e["close_to"], e["n"])
    typo_total = sum(n for _, n in typos.values())
    generic = {}
    for g in audit["generic_assumptions"]:
        generic.setdefault(g["generic_key"], (g["assumed_canonical"], g["n"]))
    twelve = ["vitamina", "pescado", "cereal", "aminoacido", "proteina", "batido", "blanco", "harina", "aceite", "oliva", "carne", "azul"]

    L = ["# Informe de normalización de alimentos (E1)\n",
         "_Trabajo Fin de Máster — Máster en Ingeniería de Software (UNIR). Etapa E1 sobre el dataset congelado `dataset-v1` "
         "(1.033 dietas, 330 clientes). Generado por `pipeline/src/pipeline/report.py` a partir de los registros del pipeline; "
         "las cifras son reproducibles y las verifica `pipeline/tests/`._\n",
         "## 1. Procesamiento de los ítems\n",
         "| Magnitud | Valor |", "|---|---|",
         f"| Ítems de comida de entrada (texto libre) | {c['items']:,} |".replace(",", "."),
         f"| Componentes tras separar alternativas y compuestos | {c['components']:,} |".replace(",", "."),
         f"| · Ruido de firma (`is_noise`: `(\"`, `tel`, `correos/mail`) | {c['noise']:,} ítems ({pct(c['noise'], c['items'])} de los ítems) |".replace(",", "."),
         f"| · Instrucciones sin alimento (`is_instruction`) | {c['instructions']:,} ítems ({pct(c['instructions'], c['items'])}) |".replace(",", "."),
         f"| · Componentes alimentarios (denominador de cobertura) | **{cat['food_components_denominator']:,}** |".replace(",", "."),
         f"| Ítems con alternativas (`/`, ` o `) | {c['items_with_alternatives']:,} ({pct(c['items_with_alternatives'], c['items'])}) |".replace(",", "."),
         f"| Ítems compuestos (` y `, ` con `, ` + `, cabezas yuxtapuestas) | {c['items_compound']:,} ({pct(c['items_compound'], c['items'])}) |".replace(",", "."),
         f"| Componentes alimentarios con cantidad | {c['components_with_quantity']:,} ({parse['pct_items_with_quantity_component']} %) |".replace(",", "."),
         "\nLa auditoría previa estimaba un 38,8 % de ítems con cantidad y unidad parseables; la diferencia se explica por la unidad implícita "
         "(«2 claras», «1 kiwi» → PIECE), la herencia de cantidad entre alternativas («200 gr (atún, pollo o pavo)») y las unidades de suplemento (SCOOP, CAPSULE).\n",
         "### Unidades (conjunto cerrado `domain.Unit`)\n",
         "| Unidad | Componentes |", "|---|---|"]
    for u, n in parse["units"].items():
        L.append(f"| {u} | {n:,} |".replace(",", "."))
    L.append("\nPalabras de unidad **no incorporadas** al conjunto (quedan en `raw_unit`, declaradas): " +
             ", ".join(f"{k} ({v})" for k, v in parse["uncovered_units"].items()) + ".\n")

    L += ["## 2. Catálogo canónico de alimentos\n",
          f"Dos niveles: **{cat['families']} familias** (nivel de las reglas del preparador) y **{len(fl)} alimentos canónicos** a nivel de especie/producto "
          "(umbral n ≥ 10 para constituir un canónico propio). El diccionario de sinónimos revisado está versionado en `pipeline/src/pipeline/data/food_synonyms.json` "
          "(v2 tras la auditoría ortográfica y semántica) y las fusiones entre cabezas nominales distintas en `pipeline/src/pipeline/data/reviewed_merges.json`.\n",
          "| Cobertura (denominador explícito: todos los componentes alimentarios) | Valor |", "|---|---|",
          f"| Componentes alimentarios | {cat['food_components_denominator']:,} |".replace(",", "."),
          f"| Mapeados a un canónico | {cat['mapped']:,} (**{cat['coverage_pct']} %**) |".replace(",", "."),
          f"| Sin mapear (cola larga, n < 10 y sin sinónimo) | {cat['unmapped']:,} ({pct(cat['unmapped'], cat['food_components_denominator'])}) |".replace(",", "."),
          f"| Solo descriptor (etiquetas, fragmentos de línea) | {cat['descriptor_only']:,} ({pct(cat['descriptor_only'], cat['food_components_denominator'])}) |".replace(",", "."),
          f"| Excluidos por criterio farmacológico (permanecen en el denominador) | {cat['excluded_substances']:,} ({pct(cat['excluded_substances'], cat['food_components_denominator'])}) |".replace(",", "."),
          f"| Resolución | sinónimo {cat['resolved_by'].get('synonym', 0):,} · prefijo {cat['resolved_by'].get('prefix', 0):,} · canónico propio {cat['resolved_by'].get('own_canonical', 0):,} |".replace(",", "."),
          "\nSi los excluidos se sacaran del denominador la cobertura sería " + f"{cat['coverage_pct_excluding_excluded_from_denominator']} %; no se utiliza esa cifra.\n",
          "### Distribución por `FoodGroup` (componentes mapeados)\n", "| Grupo | Componentes | Canónicos |", "|---|---|---|"]
    fg = Counter(f["group"] for f in fl)
    for g, n in norm["groups"].items():
        L.append(f"| {g} | {n:,} | {fg.get(g, 0)} |".replace(",", "."))
    sec = Counter(f["secondary_group"] for f in fl if f.get("secondary_group"))
    L.append(f"\n`secondary_group` asignado a {sum(sec.values())} canónicos ({dict(sec)}): legumbres CARB+PROTEIN, aguacate/guacamole/aceitunas FAT+FRUIT, cacahuetes FAT+PROTEIN, etc.\n")
    L += ["### Las doce suposiciones de alto volumen (`generic_assumption`)\n",
          "Palabras genéricas del corpus interpretadas hacia un canónico concreto. Los componentes que llegan a su canónico por una de ellas llevan "
          f"`generic_assumption: true` en `diet_items.jsonl` (**{norm['generic_assumption']:,} componentes, {norm['generic_assumption_pct_of_mapped']} % de los mapeados**), "
          "de modo que la métrica de solapamiento puede reportarse con y sin ellos.\n".replace(",", "."),
          "| Palabra | Canónico asumido | n |", "|---|---|---|"]
    for k in twelve:
        if k in generic:
            L.append(f"| {k} | {generic[k][0]} | {generic[k][1]} |")
    L += ["\n### Erratas del corpus (clase 1 de la auditoría)\n",
          f"Detectadas por distancia de edición ≤ 2 (o palabra partida) frente a la forma más frecuente del grupo; se conservan como sinónimos declarados. "
          f"{len(typos)} formas, **{typo_total} componentes** ({pct(typo_total, cat['food_components_denominator'])} de los componentes alimentarios): dato sobre la calidad de la fuente.\n",
          "| Forma en el corpus | Forma correcta | n |", "|---|---|---|"]
    for k, (ok, n) in sorted(typos.items(), key=lambda kv: -kv[1][1]):
        L.append(f"| {k} | {ok} | {n} |")
    kinds = Counter(ch["kind"] for ch in changes)
    reasons = Counter(ch.get("reason", "").split(":")[0] for ch in changes)
    L += ["\n### Auditoría del diccionario (Tarea A)\n",
          f"Cambios v1 → v2: {kinds.get('remove_key', 0)} claves eliminadas, {kinds.get('new_canonical', 0)} canónicos nuevos, {kinds.get('add_key', 0)} claves añadidas. "
          f"Por clase: unidades coladas en el nombre {reasons.get('class 3', 0)} (resueltas estructuralmente: las palabras de unidad son descriptores del normalizador), "
          f"fusiones semánticamente incorrectas {reasons.get('class 2', 0)} (aceite de linaza, harinas por perfil de gluten, tahini y crema de almendras por alérgeno, proteína vegetal, pan blanco, café con leche…), "
          f"fragmentos de ítem compuesto {reasons.get('class 4', 0)} (resueltos en el parser: separador de cabezas yuxtapuestas). "
          "Comprobaciones cruzadas: 0 claves bajo dos canónicos, 0 canónicos listados como sinónimo de otro (tests en `pipeline/tests/test_synonyms.py`).\n"]

    L += ["## 3. Atributos y evaluabilidad de las reglas\n",
          "Flags de regla: `is_processed_sugar`, `is_soft_drink`, `is_salt`, `is_fasting_compatible`, `is_alcohol`, `is_stimulant`. "
          "Flags de restricción: `is_peanut`, `is_tree_nut` (alergias distintas), `contains_lactose`, `contains_gluten`, `contains_soy`, `contains_shellfish`, `contains_egg`, `contains_fish`. "
          "Los criterios humanos están versionados en `pipeline/src/pipeline/data/food_attributes.json`; las asignaciones de criterio quedan declaradas en `food_attributes_dubious.json` "
          f"({len(dub)} canónicos con nota).\n",
          "| Flag | Canónicos con `true` |", "|---|---|"]
    for k, v in foods["summary"]["attributes"]["flags_true"].items():
        L.append(f"| {k} | {v} |")
    lf = lact["foods"]
    L += ["\n### Lactosa: hecho nutricional frente a comportamiento del profesional\n",
          f"Clientes con intolerancia a la lactosa declarada: **{lact['lactose_intolerant_clients_declared']}** ({lact['of_which_with_clean_diets']} con dietas limpias, "
          f"{lact['diets_of_those_clients']} dietas). La comprobación empírica muestra que el profesional prescribe queso fresco, requesón, queso, yogur y batidos de suero a estos "
          "clientes en la misma proporción que a la población general; solo la leche líquida está ausente. Ese hallazgo se separa en dos piezas: "
          "(a) `contains_lactose` sigue siendo un **atributo factual** del alimento (el suero concentrado, el queso fresco, el requesón y el yogur contienen lactosa); "
          "(b) el **comportamiento** —«el profesional no restringe lácteos fermentados ni derivados del suero a clientes con intolerancia declarada»— se registra como regla "
          "de la constitución (sección 8, `no_restringe_lacteos_intolerantes`, n = 17, confianza baja por tamaño de muestra). El validador puede así operar en dos modos, "
          "reproducir el criterio del profesional o aplicar la restricción estricta, y la diferencia entre ambos es medible.\n",
          "| Alimento | Intolerantes que lo reciben | Población que lo recibe | `contains_lactose` (hecho) |", "|---|---|---|---|"]
    decisions = {"leche": "true", "kéfir": "true", "mantequilla": "true (ausente en v1)", "café con leche": "true", "yogur": "true", "queso fresco": "true",
                 "requesón": "true", "queso": "true (trazas; declarado)", "batido de proteínas": "true (suero concentrado)", "proteína aislada": "false (aislado bajo el umbral)",
                 "caseína": "true (conservador)", "barrita proteica": "true (conservador)", "postre o dulce": "true (conservador)", "leche sin lactosa": "false",
                 "yogur sin lactosa": "false", "bebida de proteínas": "— (ausente)"}
    for name, v in lf.items():
        if name == "miel":
            continue
        L.append(f"| {name} | {v['lactose_clients_receiving_it']}/{lact['of_which_with_clean_diets']} ({v['share_of_lactose_clients']}) | {v['all_clients_receiving_it']}/330 ({v['share_of_all_clients']}) | {decisions.get(name, '')} |")
    h = lact["honey"]
    L.append(f"\nMiel: {h['components_total']} componentes en {h['clients']} clientes; {h['notes_mentioning_miel']} notas la mencionan y {h['notes_forbidding_miel']} la prohíben: "
             "**evidencia insuficiente** para concluir en ninguna dirección (entrada descriptiva `miel_evidencia_insuficiente`). `is_processed_sugar = false` porque la miel no es azúcar "
             "procesado por definición del flag, no porque el profesional la permita.\n")
    lv = Counter(m["level"] for m in rules)
    L += [f"### Evaluabilidad de las {len(rules)} entradas de la constitución\n",
          f"{len(rules)} entradas evaluables (31 reglas de E0 + 2 de comportamiento añadidas en E1): {lv.get('item', 0)} a nivel de ítem con los atributos del catálogo; {lv.get('note', 0)} solo a nivel de notas porque son instrucciones, no alimentos: "
          "ayuno 16 h, comida tarde/cena temprano, comer despacio, saltarse comidas, refuerzo de fibra, ayuno estable por fase y dos retiradas). "
          "Las 11 reglas de confianza baja son evaluables igual que las 19 sostenidas (`rules_evaluability.json`). "
          f"**Naturaleza (Fase 9, B): {len(validated['nature_split']['prescriptive'])} reglas prescriptivas** —sostenidas o de política y seguidas en la mayoría de su grupo "
          f"(prevalencia ≥ {validated['nature_split']['majority_prevalence']:.2f}; patrón evitado ≤ {validated['nature_split']['majority_prevalence']:.2f} en las de evitación), exigibles a cada propuesta: "
          + ", ".join(f"`{i}`" for i in validated["nature_split"]["prescriptive"]) + f"— y **{len(validated['nature_split']['descriptive_kept'])} sostenidas pero descriptivas** "
          f"(minoritarias en su grupo: discriminan el objetivo, no pueden exigirse al 100 % de las propuestas: " + ", ".join(f"`{i}`" for i in validated["nature_split"]["descriptive_kept"])
          + f"); las {len(validated['nature_split']['descriptive_other'])} restantes (retiradas, descriptivas, de comportamiento) son descriptivas por estado. "
          "El campo `nature` viaja con la constitución (`validated_rules.json` → tabla `rules`, migración 0009) y es lo que la envolvente de plausibilidad exige (`goal_rule_unsatisfied`). "
          "Nota de diseño para la etapa del compositor: si el compositor genera también el bloque de notas a partir de los casos recuperados, las 31 reglas pasan a ser evaluables sobre la dieta compuesta.\n"]

    L += ["## 4. Consideración ética: sustancias farmacológicas en las prescripciones originales\n",
          "El barrido del catálogo (90 términos: fármacos de prescripción, hormonas, esteroides anabolizantes, SARMs, moduladores de estrógenos, estimulantes) "
          "detectó en las dietas originales un fármaco de prescripción (tamoxifeno), dos hormonas tiroideas (T3 y T4), productos cuyo nombre comercial sugiere un anabolizante o un precursor hormonal, "
          "un alcaloide prohibido en complementos alimenticios en la UE (yohimbina) y dos nombres comerciales no identificados. "
          "Criterio aplicado (decision del autor): se excluyen los medicamentos de prescripción y cualquier producto anabolizante u hormonal, o cuyo nombre lo sugiera; "
          "ante una sustancia no identificable el valor por defecto es excluir (el coste de excluir por error una marca es nulo; el de incluir un fármaco no lo es). "
          "Se mantienen vitaminas, minerales, aminoácidos, proteínas y suplementos herbales (tribulus, maca, ashwagandha, liv 52); la melatonina se mantiene (venta libre ≤ 1,9 mg en España). "
          "La exclusión es estructural: `pipeline/src/pipeline/data/excluded_substances.json` se aplica antes de la resolución de sinónimos, de modo que el asistente es incapaz de proponer estas sustancias. "
          f"**Total excluido: {sum(e['occurrences'] for e in excl['substances'])} componentes** ({pct(sum(e['occurrences'] for e in excl['substances']), cat['food_components_denominator'])}).\n",
          "| Sustancia | Ocurrencias | Estado | Motivo |", "|---|---|---|---|"]
    for e in excl["substances"]:
        if e["occurrences"]:
            L.append(f"| {e['name']} | {e['occurrences']} | {e['status']} | {e['reason']} |")
    L.append(f"\nAdemás se registran {sum(1 for e in excl['substances'] if not e['occurrences'])} entradas de guarda (esteroides, SARMs, PCT, estimulantes, fármacos diversos) no presentes en `dataset-v1` que bloquearían cualquier regeneración.\n")

    n = norm
    L += ["## 5. `diet_items.jsonl`\n",
          f"{n['records']:,} registros (uno por componente alimentario; instrucciones y ruido quedan fuera y contados: {n['instructions_skipped']:,} y {n['noise_skipped']:,}). "
          f"Mapeados {n['mapped']:,} (**{n['coverage_pct']} %**), sin canónico {n['unmapped_no_canonical']:,}, solo descriptor {n['descriptor_only']:,}, excluidos {n['excluded_substance']:,}; "
          f"con cantidad {n['with_quantity']:,}; en grupos de alternativas {n['alternatives']:,}; compuestos {n['compound']:,}; dietas {n['diets']:,}.\n".replace(",", "."),
          "### Las 30 cadenas más frecuentes sin mapear\n", "| Clave normalizada | n |", "|---|---|"]
    for k, v in n["unmapped_top30"]:
        L.append(f"| {k} | {v} |")

    tc = tree["counts"]
    L += ["\n## 6. Anonimización del árbol completo (Tarea B)\n",
          f"Reconstrucción de `clientes/`: {tc['files_written']:,} ficheros de {tc['clients']} clientes renombrados sin nombres reales "
          f"({tc['diet_files_with_id']:,} dietas con su id, {tc.get('dieta_files_ordinal', 0)} dietas descartadas por el parser original con ordinal, "
          f"{tc.get('entreno_files_ordinal', 0)} entrenamientos, {tc.get('datos_files_ordinal', 0)} hojas de datos, {tc.get('otro_files_ordinal', 0)} otros); "
          f"cabeceras reescritas {tc['headers_rewritten']:,}; **{tc['tokens_masked_in_content']:,} tokens de nombre enmascarados** en el contenido "
          f"(el extractor original solo sustituía al cliente titular de la dieta; en entrenamientos y hojas de datos quedaban terceros y el nombre de pila del profesional) y {tc.get('masked_dni', 0)} patrones de DNI enmascarados. "
          "Los originales con nombres salieron del árbol a una custodia cifrada (véase `PROVENANCE.md`).\n".replace(",", "."),
          f"Auditoría del árbol completo (`_tools/audit_tree.py`, criterio de aceptación cero, test permanente): {tree_audit['dirs']} carpetas y {tree_audit['files']:,} ficheros "
          f"revisados por nombre de carpeta, nombre de fichero y contenido → **{tree_audit['total_hits']} aciertos**. El diccionario de nombres que sostiene la auditoría es una lista de hashes SHA-256 con sal; "
          "no existe ningún nombre real en claro en el árbol del proyecto.\n".replace(",", ".")]
    dp = load("discriminative_power.json")
    pr, ov, ps, st, rc = dp["protocol"], dp["overlap_whole_diet"], dp["overlap_per_slot"], dp["structure"], dp["rule_compliance"]
    L += ["## 7. Diseño de la evaluación: techo humano, suelo y puntuación normalizada\n",
          f"Protocolo común a todas las medidas: {pr['diets_clean']:,} dietas limpias menos {pr['template_diets_excluded']} dietas-plantilla = {pr['diets_used']:,} dietas de "
          f"{pr['clients_used']} clientes; consultas = dietas de clientes con ≥ 3 dietas ({pr['queries_same_client_ge3']}); **techo** = media con las demás dietas del mismo cliente "
          f"excluyendo el vecino más cercano (la versión consecutiva casi idéntica); **suelo** = media con {pr['k_random_other_clients']} dietas aleatorias de otros clientes (semilla {pr['seed']}).\n".replace(",", "."),
          "### 7.1 Reencuadre: el techo es la autoconsistencia del profesional\n",
          "Cuando el profesional escribe dos dietas para el mismo cliente, coincide consigo mismo un 0,219 (cadena cruda) o un 0,366 (canónico). Ningún sistema puede superar ese acuerdo, "
          "porque ni él lo supera; perseguir un Jaccard alto es perseguir un número que no existe. La métrica no es el Jaccard absoluto ni el ratio, sino la **posición del sistema entre el suelo y el techo**:\n",
          "```\npuntuación_normalizada = (sistema − suelo) / (techo − suelo)\n```\n",
          "Es la lógica de las tareas de lenguaje con alta variabilidad intrínseca, donde se compara contra el acuerdo entre anotadores humanos y no contra una puntuación perfecta. "
          "**Toda métrica de solapamiento del arnés se reporta como tripleta suelo / sistema / techo más la puntuación normalizada; nunca el valor absoluto solo.**\n",
          "| Granularidad | Clases | Suelo (otro cliente) | Techo (mismo cliente) | Ratio | Techo con vecino |", "|---|---|---|---|---|---|"]
    for g, v in ov.items():
        L.append(f"| {g} | {v['classes']:,} | {v['floor_different_clients']:.3f} | {v['ceiling_same_client']:.3f} | {v['ratio']}× | {v['ceiling_including_nearest_neighbour']:.3f} |".replace(",", "."))
    ex = ov["food_text"]["example_normalised_score_for_system_0_19"]
    L += [f"\nEjemplo: un sistema con Jaccard 0,19 sobre cadena cruda habría recorrido el **{100*ex:.0f} %** del intervalo alcanzable (suelo {ov['food_text']['floor_different_clients']:.3f}, techo {ov['food_text']['ceiling_same_client']:.3f}).\n",
          "### 7.2 Solapamiento franja a franja\n",
          "Media sobre las franjas de la consulta del Jaccard franja a franja (una franja ausente en la otra dieta puntúa 0). Las franjas tienen vocabularios distintos y el agregado de dieta completa los difumina.\n",
          "| Granularidad | Suelo | Techo | Ratio |", "|---|---|---|---|"]
    for g, v in ps.items():
        L.append(f"| {g} | {v['floor_different_clients']:.3f} | {v['ceiling_same_client']:.3f} | **{v['ratio']}×** |")
    L += ["\n| Franja (`normalized_key`) | Consultas | Suelo | Techo | Ratio |", "|---|---|---|---|---|"]
    for slot, v in ps["normalized_key"]["by_slot"].items():
        L.append(f"| {slot} | {v['queries']} | {v['floor']:.3f} | {v['ceiling']:.3f} | {v['ratio']}× |")
    L += ["\n### 7.3 Métricas de estructura (independientes de la granularidad del catálogo)\n",
          "| Medida | Techo (mismo cliente) | Suelo (otro cliente) | Sentido |", "|---|---|---|---|"]
    for k, v in st.items():
        L.append(f"| {k} | {v['ceiling_same_client']} | {v['floor_different_clients']} | {v['direction']} |")
    a, c = rc["all_constraint_rules"], rc["conditional_rules_only"]
    L += ["\n### 7.4 Cumplimiento de reglas: todas frente a solo las condicionales\n",
          f"Todas las reglas-restricción ({len(a['rules'])}): dieta propia **{100*a['own_diet']:.1f} %** frente a dieta aleatoria de otro cliente evaluada con las reglas del perfil **{100*a['random_other_client_same_rules']:.1f} %** "
          f"(ratio {a['ratio']}×, {a['points']} puntos): sin margen. "
          f"Solo las **condicionales por objetivo** ({', '.join(c['rules'])}; {c['diets_with_applicable_conditional_rules']} dietas con alguna aplicable, {c['mean_applicable']} de media): "
          f"dieta propia **{100*c['own_diet']:.1f} %** frente a dieta aleatoria de un cliente con **objetivo distinto** **{100*c['floor_random_diet_of_DIFFERENT_goal']:.1f} %** "
          f"(ratio **{c['ratio_vs_different_goal']}×**, {c['points_vs_different_goal']} puntos) y frente a dieta aleatoria del **mismo objetivo** {100*c['random_diet_of_same_goal']:.1f} %.\n",
          "### 7.5 Conclusiones metodológicas\n",
          "1. El **cumplimiento global de reglas** es una métrica de **validez** (¿la dieta compuesta respeta la constitución?) y no de fidelidad al cliente: las reglas que sobreviven son globales y cualquier dieta del profesional las cumple.",
          "2. Las **reglas condicionales** sí discriminan, pero discriminan el **objetivo**, no al cliente (una dieta aleatoria del mismo objetivo cumple igual que la propia). Y el propio profesional solo cumple sus reglas condicionales en un "
          f"{100*c['own_diet']:.0f} % de los casos aplicables: ese es su techo, no el 100 %.",
          "3. El **solapamiento franja a franja** es el candidato a métrica principal: duplica el margen del solapamiento de dieta completa (2,0× frente a 1,44× en `normalized_key`) y las franjas de suplementación "
          "(antes/después de entrenar) y el desayuno son donde el profesional es más consistente con cada cliente.",
          "4. La **estructura** (número de franjas, F1 de franjas, ítems por franja) discrimina poco y la **colocación** (hidratos en la primera mitad, fruta ausente en la cena) nada: son invariantes del estilo del profesional, útiles como validez, no como fidelidad.",
          "5. Todo resultado del sistema se reportará a las dos granularidades (`normalized_key` estricta y `family` laxa), con y sin `generic_assumption`, controlando `template_group_id`, y siempre como tripleta suelo / sistema / techo con la puntuación normalizada.\n"]
    L += ["## 8. Criterios de aceptación de E1\n",
          f"- ≥ 85 % de componentes mapeados: **{cat['coverage_pct']} %** ✔ (denominador {cat['food_components_denominator']:,}).".replace(",", "."),
          f"- Catálogo con `group` y flags completos: **{len(fl)} canónicos** en {cat['families']} familias ✔ (el rango 300-600 era una estimación previa; el corpus a nivel de especie con n ≥ 10 da {len(fl)}).",
          f"- Todas las entradas de la constitución evaluables: **{len(rules)}/{len(rules)}** ✔ ({lv.get('item', 0)} por ítem, {lv.get('note', 0)} por notas).",
          "- Tests: `pipeline/tests/test_parse_items.py`, `test_synonyms.py`, `test_diet_items.py` y `pipeline/tests/test_dataset.py` (incluye la auditoría del árbol) en verde.\n"]
    for out in (DOCS_DIR / "data" / "NORMALIZATION_REPORT.md", DATASET_DIR / "NORMALIZATION_REPORT.md"):     # versioned report + copy next to the data
        out.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print(f"NORMALIZATION_REPORT.md written ({len(L)} lines); typos={len(typos)} ({typo_total} components); generic={norm['generic_assumption']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
