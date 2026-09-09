# -*- coding: utf-8 -*-
"""
E1.3 — Enrich the canonical food catalogue with the attributes that make rules and restrictions executable.

Attributes (identifiers English, see domain.FoodGroup / domain.FoodFlags):
  group / secondary_group   PROTEIN CARB FAT VEGETABLE FRUIT DAIRY SUPPLEMENT BEVERAGE CONDIMENT OTHER
  flags   is_processed_sugar is_soft_drink is_salt is_fasting_compatible is_alcohol is_stimulant
          is_peanut is_tree_nut contains_lactose contains_gluten contains_soy contains_shellfish contains_egg contains_fish

Two sources, in priority order:
  1. pipeline/data/food_attributes.json   reviewed overrides by canonical name (human criterion, versioned; includes
                                           the decisions taken from the empirical lactose validation)
  2. rules in this module                  family default group + keyword rules; every judgement call is recorded
                                           as `dubious` for the data owner

Modes:
  --propose   write _dataset/food_attributes_proposal.json and print the dubious list + rule evaluability matrix
  --apply     write the enriched _dataset/foods.json in place (adds group, secondary_group, flags, attribute_source)
              and _dataset/rules_evaluability.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR, REPO_ROOT, DATA_DIR  # noqa: E402
from finalprosports.domain.model import FoodFlags, FoodGroup  # noqa: E402

ATTRIBUTES_PATH = DATA_DIR / "food_attributes.json"

FAMILY_GROUP = {
    "carne": FoodGroup.PROTEIN, "ave": FoodGroup.PROTEIN, "embutido": FoodGroup.PROTEIN, "pescado_blanco": FoodGroup.PROTEIN,
    "pescado_azul": FoodGroup.PROTEIN, "marisco": FoodGroup.PROTEIN, "huevo": FoodGroup.PROTEIN,
    "lacteo": FoodGroup.DAIRY, "bebida_vegetal": FoodGroup.BEVERAGE,
    "cereal": FoodGroup.CARB, "pan": FoodGroup.CARB, "arroz": FoodGroup.CARB, "pasta": FoodGroup.CARB, "tuberculo": FoodGroup.CARB,
    "legumbre": FoodGroup.CARB, "verdura": FoodGroup.VEGETABLE, "fruta": FoodGroup.FRUIT,
    "fruto_seco": FoodGroup.FAT, "semilla": FoodGroup.FAT, "grasa": FoodGroup.FAT,
    "suplemento_proteina": FoodGroup.SUPPLEMENT, "suplemento_carbohidrato": FoodGroup.SUPPLEMENT, "aminoacidos": FoodGroup.SUPPLEMENT,
    "vitamina": FoodGroup.SUPPLEMENT, "mineral": FoodGroup.SUPPLEMENT, "suplemento_otro": FoodGroup.SUPPLEMENT,
    "bebida": FoodGroup.BEVERAGE, "condimento": FoodGroup.CONDIMENT, "dulce": FoodGroup.OTHER, "plato_preparado": FoodGroup.OTHER,
}
# canonical-level group (and secondary group) exceptions: name -> (group, secondary, reason)
GROUP_OVERRIDES = {
    "tofu": (FoodGroup.PROTEIN, None, "soy protein, eaten as protein source"),
    "seitán": (FoodGroup.PROTEIN, None, "wheat protein, eaten as protein source"),
    "soja texturizada": (FoodGroup.PROTEIN, None, "soy protein, eaten as protein source"),
    "edamame": (FoodGroup.PROTEIN, None, "young soy beans, protein source"),
    "hamburguesa vegetal": (FoodGroup.PROTEIN, FoodGroup.CARB, "legume/soy patty"),
    "pasta de legumbres": (FoodGroup.CARB, FoodGroup.PROTEIN, "legume pasta"),
    "aguacate": (FoodGroup.FAT, FoodGroup.FRUIT, "botanically a fruit, nutritionally a fat"),
    "guacamole": (FoodGroup.FAT, FoodGroup.FRUIT, "avocado-based"),
    "aceitunas": (FoodGroup.FAT, FoodGroup.FRUIT, "botanically a fruit, nutritionally a fat"),
    "cacahuetes": (FoodGroup.FAT, FoodGroup.PROTEIN, "peanuts: fat and protein"),
    "crema de cacahuete": (FoodGroup.FAT, FoodGroup.PROTEIN, "peanut butter"),
    "leche de coco": (FoodGroup.FAT, FoodGroup.BEVERAGE, "coconut drink: fat profile"),
    "mantequilla": (FoodGroup.FAT, FoodGroup.DAIRY, "dairy fat"),
    "chocolate negro": (FoodGroup.FAT, None, "85-99 % cocoa: mainly fat; the anxiety rule allows it"),
    "cacao puro": (FoodGroup.CONDIMENT, None, "cocoa powder used as flavouring"),
    "hamburguesa": (FoodGroup.PROTEIN, None, "meat/poultry patty"),
    "sushi": (FoodGroup.CARB, FoodGroup.PROTEIN, "rice-based dish with fish"),
    "pizza": (FoodGroup.CARB, None, "dough-based dish"),
    "gel energético": (FoodGroup.SUPPLEMENT, None, "sport carbohydrate gel"),
    "postre o dulce": (FoodGroup.OTHER, None, "sweets: processed sugar"),
    "gelatina": (FoodGroup.OTHER, None, "sugar-free gelatine allowed by the anxiety rule"),
    "grasas": (FoodGroup.FAT, None, "generic 'grasas' item"),
    "yogur vegetal": (FoodGroup.BEVERAGE, None, "plant yogurt, no lactose"),
    "café con leche": (FoodGroup.BEVERAGE, FoodGroup.DAIRY, "milk coffee"),
    "puré de patata": (FoodGroup.CARB, None, "tuber purée"),
    "harina de almendra": (FoodGroup.FAT, FoodGroup.CARB, "nut flour"),
}
LEGUME_SECONDARY = {"legumbres", "lentejas", "garbanzos", "alubias", "guisantes"}   # CARB primary, PROTEIN secondary

# flag keyword rules: flag -> (set of canonical names, dubious notes {name: reason})
FLAG_RULES: dict[str, tuple[set[str], dict[str, str]]] = {
    "is_processed_sugar": ({"zumo", "postre o dulce", "galletas", "bebida energética", "gel energético", "pan blanco"},
                           {"gel energético": "sport supplement made of sugars; flagged so the sugar rule sees it",
                            "galletas": "integral/avena variants exist; treated as processed sweet",
                            "pan blanco": "'harinas blancas' are forbidden by the same rule",
                            "miel": "NOT flagged: the trainer prescribes honey (3 items, 2 clients) and never forbids it in notes (empirical check)"}),
    "is_soft_drink": ({"refresco light", "bebida energética", "zumo"},
                      {"refresco light": "sugar-free but 'bebida con gas / con sabor', forbidden by the same clause", "zumo": "flavoured drink"}),
    "is_salt": ({"sal", "sal del himalaya"}, {}),
    "is_fasting_compatible": ({"café", "té", "infusión", "agua"}, {"infusión": "herbal infusions do not break the fast", "café con leche": "NOT flagged: milk breaks the fast"}),
    "is_alcohol": ({"cerveza", "vino"}, {"cerveza": "'sin alcohol / 0,0' variants merged; flagged conservatively (n=0 in dataset-v1)"}),
    "is_stimulant": ({"cafeína", "sinefrina", "café", "té", "pre-entreno", "bebida energética", "quemagrasa"},
                     {"quemagrasa": "most thermogenics contain caffeine/synephrine; conservative", "pre-entreno": "usually caffeinated; conservative",
                      "té": "contains caffeine (theine)"}),
    "is_peanut": ({"cacahuetes", "crema de cacahuete"}, {}),
    "is_tree_nut": ({"nueces", "nuez de brasil", "nuez de macadamia", "almendras", "anacardos", "avellanas", "pistachos", "frutos secos",
                     "crema de almendras", "harina de almendra", "bebida de almendras"},
                    {"bebida de almendras": "almond drink: tree-nut allergen", "frutos secos": "generic mixed nuts"}),
    # lactose is a nutritional FACT of the food. How the trainer treats declared-intolerant clients is a BEHAVIOUR,
    # recorded as a rule in validated_rules.json (section 8) from validate_lactose.py — never encoded in the food.
    "contains_lactose": ({"leche", "yogur", "queso fresco", "requesón", "queso", "kéfir", "mantequilla", "café con leche",
                          "batido de proteínas", "caseína", "barrita proteica", "postre o dulce"},
                         {"queso": "cured cheeses keep only trace lactose; True by fact, declared",
                          "batido de proteínas": "whey concentrate contains lactose (fact); the trainer nevertheless gives it to 10/17 intolerant clients -> behaviour rule",
                          "proteína aislada": "NOT flagged: whey isolate is below the lactose threshold (fact)",
                          "caseína": "residual lactose -> conservative True", "barrita proteica": "milk-protein based -> conservative True",
                          "postre o dulce": "natillas/flan -> conservative True",
                          "leche sin lactosa": "NOT flagged by definition", "yogur sin lactosa": "NOT flagged by definition"}),
    "contains_gluten": ({"pan integral", "pan blanco", "sándwich", "pasta integral", "pasta al huevo", "cereales integrales", "muesli", "centeno",
                         "avena", "harina de avena", "harina de trigo", "galletas", "tortitas de avena", "seitán", "cerveza", "pizza",
                         "postre o dulce", "barrita proteica", "embutido"},
                        {"avena": "conservative True: cross-contamination and avenin reactivity (explicit decision)",
                         "harina de avena": "idem avena", "tortitas de avena": "oat pancakes", "cereales integrales": "mixed cereals, mostly wheat",
                         "embutido": "conservative True: some contain gluten as filler (consistent with avena)",
                         "seitán": "wheat gluten itself", "postre o dulce": "pastry variants", "barrita proteica": "most contain cereals"}),
    "contains_soy": ({"bebida de soja", "salsa de soja", "tofu", "edamame", "soja texturizada", "proteína vegetal", "hamburguesa vegetal"},
                     {"proteína vegetal": "soy/pea blends: conservative True", "hamburguesa vegetal": "often soy-based: conservative True",
                      "batido de proteínas": "NOT flagged: whey"}),
    "contains_shellfish": ({"marisco", "sushi"}, {"sushi": "may contain shellfish; conservative"}),
    "contains_egg": ({"huevo", "clara de huevo", "yema de huevo", "tortilla", "huevos revueltos", "tortitas de avena", "pasta al huevo", "galletas",
                      "postre o dulce", "hamburguesa"},
                     {"tortitas de avena": "made with egg whites in this corpus", "galletas": "conservative", "postre o dulce": "flan/natillas", "hamburguesa": "binder; conservative"}),
    "contains_fish": ({"pescado blanco", "merluza", "panga", "bacalao", "pescado azul", "salmón", "caballa", "sardinas", "bonito", "atún", "omega 3", "sushi"},
                      {"omega 3": "fish oil capsules", "sushi": "conservative"}),
}

# rule id (validated_rules.json) -> (level, how it is evaluated with the catalogue)
RULE_EVALUATION = {
    "agua_2.5L": ("item", "canonical == 'agua' with quantity, or note text"),
    "prohibido_azucar_procesados": ("item", "flags is_processed_sugar OR is_soft_drink"),
    "comer_despacio": ("note", "text of notes"),
    "cafe_te_permitidos": ("item", "flag is_fasting_compatible"),
    "ayuno_16h": ("note", "text of notes / meal slots present"),
    "comida_tarde_cena_temprano": ("note", "text of notes"),
    "sustituir_pescado_por_pollo": ("item", "contains_fish -> family ave in CENA"),
    "sal_himalaya": ("item", "canonical 'sal del himalaya' vs 'sal' (both is_salt)"),
    "sin_hidratos_cena": ("item", "group CARB absent in CENA"),
    "grasas_base": ("item", "group FAT share of items"),
    "hidratos_en_cena": ("item", "group CARB present in CENA"),
    "suplementacion_pre_post": ("item", "group SUPPLEMENT / families aminoacidos, suplemento_proteina in ANTES/DESPUES DE ENTRENAR"),
    "refuerzo_fibra": ("note", "text (label is circular)"),
    "saltarse_comidas_fibra": ("note", "text of notes"),
    "hidratos_primera_mitad_dia": ("item", "group CARB by meal slot"),
    "fruta_no_en_cena": ("item", "group FRUIT absent in CENA"),
    "cena_proteina_grasa_verdura": ("item", "groups PROTEIN + FAT + VEGETABLE in CENA"),
    "desayuno_avena_cereales": ("item", "canonical avena / family cereal in DESAYUNO"),
    "saltarse_comidas_fases_tempranas": ("note", "text of notes"),
    "ayuno_estable_por_fase": ("note", "text of notes"),
    "alta_fibra_fases_tempranas": ("note", "text (retired)"),
    "pescado_pollo_v1": ("item", "contains_fish / family ave (retired)"),
    "suplementacion_v5": ("item", "group SUPPLEMENT (retired)"),
    "mujeres_prohibicion_azucar": ("item", "flags is_processed_sugar / is_soft_drink + profile sex"),
    "mujeres_sal_himalaya": ("item", "canonical sal del himalaya + profile sex"),
    "mujeres_chocolate_gelatina": ("item", "canonical chocolate negro / gelatina + profile sex"),
    "mujeres_alta_fibra": ("note", "text (retired)"),
    "hombres_suplementacion": ("item", "group SUPPLEMENT + profile sex"),
    "ansiedad_chocolate_o_gelatina": ("item", "canonical chocolate negro / gelatina by goal"),
    "soja_prohibida": ("item", "flag contains_soy"),
    "respetar_intolerancias_alergias": ("item", "contains_* / is_peanut / is_tree_nut vs profile has_allergies / has_intolerances"),
    "no_restringe_lacteos_intolerantes": ("item", "behaviour mode: contains_lactose items allowed for has_intolerances profiles (strict mode: vetoed)"),
    "miel_evidencia_insuficiente": ("item", "canonical 'miel' (descriptive; evidence insufficient)"),
}


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def enrich(foods: list[dict], overrides: dict) -> tuple[list[dict], list[dict]]:
    dubious, out = [], []
    flag_names = list(FoodFlags().__dict__)
    for f in foods:
        name = f["canonical_name"]
        notes: list[str] = []
        ov = overrides.get(name, {})
        secondary = None
        if "group" in ov:
            group, source = FoodGroup(ov["group"]), "override"
            secondary = FoodGroup(ov["secondary_group"]) if ov.get("secondary_group") else None
        elif name in GROUP_OVERRIDES:
            group, secondary, why = GROUP_OVERRIDES[name]
            source = "rule"
            if why:
                notes.append(f"group {group.value}" + (f"+{secondary.value}" if secondary else "") + f": {why}")
        elif f.get("family") in FAMILY_GROUP:
            group, source = FAMILY_GROUP[f["family"]], "family"
            if name in LEGUME_SECONDARY:
                secondary = FoodGroup.PROTEIN
                notes.append("group CARB + PROTEIN secondary: legumes are both; CARB primary because the trainer's dinner rule treats them as hidratos")
        else:
            group, source = FoodGroup.OTHER, "default"
            notes.append("no family: group OTHER by default")
        if "secondary_group" in ov and "group" not in ov:
            secondary = FoodGroup(ov["secondary_group"]) if ov["secondary_group"] else None
        flags = {}
        for flag in flag_names:
            names, dubious_notes = FLAG_RULES.get(flag, (set(), {}))
            if "flags" in ov and flag in ov["flags"]:
                flags[flag] = bool(ov["flags"][flag])
                if name in dubious_notes:
                    notes.append(f"{flag}={flags[flag]} (override): {dubious_notes[name]}")
                continue
            flags[flag] = name in names
            if name in dubious_notes:
                notes.append(f"{flag}={flags[flag]}: {dubious_notes[name]}")
        rec = {**f, "group": group.value, "secondary_group": secondary.value if secondary else None, "flags": flags, "attribute_source": source}
        out.append(rec)
        if notes:
            dubious.append({"canonical_name": name, "family": f.get("family"), "frequency": f["frequency"], "group": group.value,
                            "secondary_group": rec["secondary_group"], "notes": notes})
    return out, dubious


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--foods", type=Path, default=DATASET_DIR / "foods.json")
    ap.add_argument("--attributes", type=Path, default=ATTRIBUTES_PATH)
    ap.add_argument("--rules", type=Path, default=DATASET_DIR / "validated_rules.json")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--propose", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    catalog = load_json(args.foods)
    overrides = load_json(args.attributes)["foods"] if args.attributes.exists() else {}
    enriched, dubious = enrich(catalog["foods"], overrides)
    rules = load_json(args.rules)["rules"]
    matrix = []
    for r in rules:
        how = RULE_EVALUATION.get(r["id"])
        matrix.append({"id": r["id"], "status": r["status"], "confidence": r["confidence"], "evaluable": how is not None,
                       "level": how[0] if how else None, "attributes": how[1] if how else None})
    summary = {"foods": len(enriched), "groups": dict(Counter(f["group"] for f in enriched).most_common()),
               "secondary_groups": dict(Counter(f["secondary_group"] for f in enriched if f["secondary_group"]).most_common()),
               "flags_true": {k: sum(1 for f in enriched if f["flags"][k]) for k in FoodFlags().__dict__},
               "dubious": len(dubious), "rules_total": len(rules),
               "rules_item_level": sum(1 for m in matrix if m["level"] == "item"), "rules_note_level": sum(1 for m in matrix if m["level"] == "note"),
               "rules_not_evaluable": sum(1 for m in matrix if not m["evaluable"]),
               "overrides_applied": sum(1 for f in enriched if f["attribute_source"] == "override")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.propose:
        proposal = {"summary": summary, "foods": [{k: f[k] for k in ("id", "canonical_name", "family", "frequency", "group", "secondary_group", "flags", "attribute_source")} for f in enriched],
                    "dubious": dubious, "rules_matrix": matrix}
        (DATASET_DIR / "food_attributes_proposal.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        for d in sorted(dubious, key=lambda x: -x["frequency"]):
            print(f"  {d['frequency']:5d} {d['canonical_name']:28s} [{d['family']}] {d['group']:10s} | " + " ; ".join(d["notes"]))
        return 0
    catalog["foods"] = enriched
    catalog["summary"]["attributes"] = summary
    args.foods.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (DATASET_DIR / "rules_evaluability.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (DATASET_DIR / "food_attributes_dubious.json").write_text(json.dumps(dubious, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"foods.json enriched: {len(enriched)} foods; rules item-level {summary['rules_item_level']}, note-level {summary['rules_note_level']}, not evaluable {summary['rules_not_evaluable']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
