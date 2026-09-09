# -*- coding: utf-8 -*-
"""
E1.2 — Canonical food catalogue built from scratch out of the parsed items (two levels).

Levels:
  family          coarse grouping used by the trainer's rules (pescado_blanco, cereal, aminoacidos, ...)
  canonical_name  species / product level (merluza, panga, muesli, bcaa, eaa ...)

Sources of human criterion (versioned in pipeline/data/, reviewed by the data owner):
  food_synonyms.json        family -> canonical -> normalised keys
  excluded_substances.json  prescription drugs / anabolic-hormonal products: never enter the catalogue

Resolution of a normalised key: excluded substance -> exact synonym key -> shorter prefix (Spanish head noun
first) -> own canonical when the key has >= --min-own occurrences (family unknown, assigned in E1.3) -> unmapped.

Coverage is reported with an explicit denominator: all food components (instructions and signature noise are
NOT food components and are counted apart); components of excluded substances stay in the denominator as
"excluded", never as mapped.

Normalisation of a raw food string: NFKD without accents, lower case, punctuation removed, negated descriptors
("sin azúcar", "bajo en sal") removed, protected multi-word names kept as one token, stop words and DESCRIPTORS
(cooking method, size, fat content, freshness, layout words) removed, digits removed, tokens singularised.
Nothing is ever sliced to a fixed length; the parser already removed quantity, unit and the preposition that
follows the unit (the two bugs of the legacy vocabulary).

CLI:
  --propose   write _dataset/food_catalog_proposal.json + review summary (no catalogue written)
  --apply     write _dataset/foods.json, _dataset/excluded_substances.json, _dataset/food_catalog_unmapped.json,
              _dataset/build_food_catalog_log.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR, REPO_ROOT  # noqa: E402

from pipeline import DATA_DIR  # noqa: E402
SYNONYMS_PATH = DATA_DIR / "food_synonyms.json"
EXCLUDED_PATH = DATA_DIR / "excluded_substances.json"
BRAND_MAP_PATH = DATA_DIR / "brand_map.json"

STOPWORDS = {"de", "del", "la", "el", "los", "las", "con", "sin", "y", "o", "u", "e", "en", "al", "a", "un", "una",
             "unos", "unas", "para", "por", "que", "se", "lo", "su", "mi", "es", "muy", "mas", "menos", "tipo", "estilo",
             "cualquier", "cualquiera", "alguna", "algun", "otro", "otra", "otros", "otras", "todo", "toda", "cada"}
DESCRIPTORS = {
    # cooking method / preparation
    "plancha", "horno", "vapor", "cocido", "cocida", "cocidos", "cocidas", "hervido", "hervida", "hervidos", "asado", "asada",
    "asados", "asadas", "frito", "frita", "salteado", "salteada", "salteados", "salteadas", "guisado", "guisada", "estofado",
    "rehogado", "rehogada", "crudo", "cruda", "crudos", "crudas", "picado", "picada", "picados", "rallado", "rallada", "troceado",
    "troceada", "triturado", "triturada", "batida", "molido", "molida",
    "revuelto", "revueltos", "escalfado", "escalfados", "pochado", "microondas", "papillote", "brasa", "parrilla", "wok", "sarten",
    "preparado", "preparada", "cocinado", "cocinada", "aliñado", "alinado", "alinada", "macerado", "marinado", "escurrido",
    "escurrida", "lavado", "lavada", "lavados", "lavadas", "pelado", "pelada", "cortado", "cortada", "laminado", "laminada",
    "deshuesado", "deshuesada", "descongelado", "congelado", "congelada", "congelados", "congeladas", "hecho", "hecha",
    "vaporizado", "vaporizada", "enjuagado", "enjuagada", "previamente", "lavar",
    # size / amount / quality
    "grande", "grandes", "pequeno", "pequena", "pequenos", "pequenas", "mediano", "mediana", "medianos", "medianas", "gordo",
    "gorda", "fino", "fina", "finos", "finas", "grueso", "gruesa", "generoso", "generosa", "abundante", "poco", "poca",
    "colmada", "rasa", "extra", "buena", "bueno", "calidad", "primera", "aprox", "aproximadamente", "unos", "aproximado",
    # freshness / state
    "fresco", "fresca", "frescos", "frescas", "natural", "naturales", "maduro", "madura", "maduros", "verde", "verdes",
    "seco", "seca", "secos", "secas", "crujiente", "tierno", "tierna", "caliente", "frio", "fria", "templado", "templada",
    "casero", "casera", "caseros", "caseras", "ecologico", "ecologica", "ecologicos", "bio", "organico", "organica",
    # fat descriptors (the flags are decided per canonical food)
    "desnatado", "desnatada", "desnatados", "desnatadas", "semidesnatado", "semidesnatada", "semi", "entero", "entera",
    "enteros", "enteras", "light", "ligero", "ligera", "anadido", "anadida", "anadidos", "anadidas", "añadido", "añadida",
    "bajo", "baja", "contenido", "reducido", "reducida", "cero", "piel", "hueso", "espina", "espinas",
    # layout / instruction residue
    "elegir", "eleccion", "gusto", "posible", "ser", "puede", "pueden", "si", "no", "tu", "tus", "ha", "has", "han", "hay",
    "ant", "antes", "despues", "solo", "sola", "libre", "opcion", "opciones", "elige", "elija", "elijas", "cosa", "cosas", "resto",
    "principalmente", "obligatoriamente", "debe", "deben", "caso", "necesidad", "excepcional", "salvo", "meter",
    "opcional", "preferiblemente", "preferentemente", "mejor", "recomendado", "recomendable", "normal", "corriente",
    "marca", "variado", "variada", "variados", "variadas", "mezcla", "mezclado", "mezclada", "surtido", "suplemento",
    "suplementos", "suplementacion", "producto", "productos", "toma", "tomas", "dosis",
    "vez", "veces", "semana", "dia", "dias", "gr", "g", "ml", "cc", "kcal", "min", "minutos", "hora", "horas",
    # unit words (class 3 of the synonym audit): "atun en lata", "pavo en lonchas", "cazo de proteina" -> the food only
    "cucharada", "cucharadas", "cuharada", "cucharadita", "cucharaditas", "cazo", "cazos", "cazito", "scoop", "scoops", "lata", "latas",
    "loncha", "lonchas", "punado", "punados", "diente", "dientes", "rebanada", "rebanadas", "chorrito", "taza", "tazas", "capsula",
    "capsulas", "caps", "perla", "perlas", "pastilla", "pastillas", "tableta", "tabletas", "dosis", "medida", "medidas", "rodaja",
    "rodajas", "onza", "onzas", "vaso", "vasos", "copa", "copas", "pieza", "piezas", "unidad", "unidades", "filete", "filetes",
    "tarrina", "tarrinas", "bote", "botes", "paquete", "sobre", "sobres", "racion", "raciones", "porcion", "porciones", "trozo", "trozos",
    "vara", "varas", "bara", "baras", "rama", "ramas", "hoja", "hojas",
}
NO_SINGULAR = {"gas", "mas", "menos", "tres", "dos", "seis", "pais", "anis", "arroz", "maiz", "pez", "nuez", "bcaas", "bcaa",
               "omegas", "espagueti", "chips", "cornflakes", "krispies", "eaas", "caps", "aminos", "sarms"}
PLURAL_TO_SINGULAR = {"nueces": "nuez", "lentejas": "lenteja", "garbanzos": "garbanzo", "judias": "judia", "guisantes": "guisante",
                      "alubias": "alubia", "habas": "haba", "espinacas": "espinaca", "acelgas": "acelga", "champinones": "champinon",
                      "setas": "seta", "esparragos": "esparrago", "fresas": "fresa", "arandanos": "arandano", "frambuesas": "frambuesa",
                      "moras": "mora", "uvas": "uva", "cerezas": "cereza", "pasas": "pasa", "almendras": "almendra", "avellanas": "avellana",
                      "anacardos": "anacardo", "pistachos": "pistacho", "cacahuetes": "cacahuete", "semillas": "semilla", "pipas": "pipa",
                      "copos": "copo", "tortitas": "tortita", "galletas": "galleta", "verduras": "verdura", "hortalizas": "hortaliza",
                      "legumbres": "legumbre", "mariscos": "marisco", "gambas": "gamba", "langostinos": "langostino", "mejillones": "mejillon",
                      "almejas": "almeja", "berberechos": "berberecho", "sardinas": "sardina", "boquerones": "boqueron", "anchoas": "anchoa",
                      "aceitunas": "aceituna", "pepinillos": "pepinillo", "brotes": "brote", "claras": "clara", "yemas": "yema",
                      "huevos": "huevo", "vitaminas": "vitamina", "frutas": "fruta", "tortillas": "tortilla", "cereales": "cereal",
                      "frutos": "fruto", "secos": "seco", "macarrones": "macarron", "espaguetis": "espagueti", "hierbas": "hierba",
                      "especias": "especia", "aminoacidos": "aminoacido", "electrolitos": "electrolito", "minerales": "mineral",
                      "dulces": "dulce", "encurtidos": "encurtido", "germinados": "germinado", "probioticos": "probiotico",
                      "esenciales": "esencial", "cazos": "cazo", "factores": "factor", "algas": "alga"}
PROTECTED_PHRASES = ("queso fresco", "queso batido", "yogur batido", "yogurt batido", "huevos revueltos", "huevo revuelto",
                     "jamon cocido", "jamon york", "cafe con leche", "cafe cortado", "pan tostado", "almendras tostadas",
                     "revuelto de claras", "revuelto claras", "vitamina c", "vitamina d", "vitamina e", "vitamina k", "vitamina b",
                     "diente de leon", "diente leon", "cardo mariano", "leche de coco", "leche coco", "pescado blanco", "pescado azul", "frutos secos", "fruto seco",
                     "carne roja", "sal del himalaya", "sal himalaya", "sal rosa", "sal marina", "chocolate negro",
                     "leche entera", "leche desnatada", "leche semidesnatada", "pan blanco", "arroz blanco", "vino blanco",
                     "te verde", "te rojo", "te negro", "te limon", "te matcha", "te blanco", "te fucu", "judias verdes",
                     "pimiento verde", "pimiento rojo", "cafe solo", "agua con gas", "sin lactosa", "sin gluten", "0 0", "zero", "light")
NEGATED = re.compile(r"\b(?:sin|bajo en|baja en|bajos en|bajas en|0 ?%(?: de)?|cero|libre de)\s+"
                     r"(?:azucar(?:es)?|azucares anadidos|sal|sales minerales|grasa(?:s)?|edulcorante(?:s)?|sodio|aditivos?|conservantes?)\b")
DESCRIPTOR_ONLY = {"sin_lactosa", "sin_gluten", "light", "zero", "0_0", "sin_lactosa sin_gluten", "sin_gluten sin_lactosa",
                   "lactosa", "gluten", "alimentos", "alimento", "blanca", "mezclada roja", "mezclada roja blanca", "roja blanca", "mezcla dos", "catabolico",
                   "pin pon", "entrenamiento", "tarde", "cena", "comida", "dieta 2", "dieta"}


# --------------------------------------------------------------------------- #
# Normalisation                                                                #
# --------------------------------------------------------------------------- #

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def singularize(tok: str) -> str:
    if tok in PLURAL_TO_SINGULAR:
        return PLURAL_TO_SINGULAR[tok]
    if tok in NO_SINGULAR or len(tok) <= 3:
        return tok
    if tok.endswith("ces"):
        return tok[:-3] + "z"
    if tok.endswith("es") and len(tok) > 4 and tok[-3] not in "aeiou":
        return tok[:-2]
    if tok.endswith("s") and tok[-2] in "aeiou":
        return tok[:-1]
    return tok


def normalize_key(text: str, drop_descriptors: bool = True) -> str:
    """Normalised grouping key of a raw food string."""
    s = strip_accents(text).lower()
    s = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", s)
    s = re.sub(r"[^a-z0-9ñ\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = NEGATED.sub(" ", s)
    for phrase in PROTECTED_PHRASES:
        if phrase in s:
            s = s.replace(phrase, phrase.replace(" ", "_"))
    toks = []
    for t in s.split():
        if "_" in t:
            toks.append(t)
            continue
        if t.isdigit() or t in STOPWORDS:
            continue
        if drop_descriptors and t in DESCRIPTORS:
            continue
        toks.append(singularize(t))
    return " ".join(toks)


# --------------------------------------------------------------------------- #
# Dictionaries                                                                 #
# --------------------------------------------------------------------------- #

def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_components(path: Path) -> tuple[list[dict], dict]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    counts = {"components_total": len(rows),
              "noise": sum(1 for r in rows if r.get("is_noise")),
              "instructions": sum(1 for r in rows if r["is_instruction"] and not r.get("is_noise")),
              "food_without_text": sum(1 for r in rows if not r["is_instruction"] and not r.get("is_noise") and not r["food_text"])}
    food = [r for r in rows if not r["is_instruction"] and not r.get("is_noise") and r["food_text"]]
    counts["food_components"] = len(food)
    return food, counts


def merge_brands(families: dict, brand_map: dict) -> dict:
    """Brand keys live only in brand_map.json; here they become synonyms of their GENERIC canonical (never a canonical themselves)."""
    for b in brand_map["brands"]:
        canon = families.setdefault(b["family"], {}).setdefault(b["generic"], [])
        for k in b["keys"]:
            if k not in canon:
                canon.append(k)
    return families


def key_index(families: dict) -> tuple[dict[str, str], dict[str, str]]:
    """normalised key -> canonical name; canonical name -> family."""
    idx: dict[str, str] = {}
    fam: dict[str, str] = {}
    for family, canon_map in families.items():
        for canon, keys in canon_map.items():
            fam[canon] = family
            for k in [normalize_key(canon)] + [normalize_key(x) for x in keys]:
                if k and k not in idx:
                    idx[k] = canon
    idx.pop("", None)
    return idx, fam


def excluded_index(excluded: dict) -> dict[str, str]:
    """normalised key -> excluded substance name (excluded and pending_review alike are kept out)."""
    idx = {}
    for e in excluded["substances"]:
        for k in [e["name"]] + e["keys"]:
            nk = normalize_key(k)
            if nk:
                idx[nk] = e["name"]
    return idx


def resolve(key: str, idx: dict[str, str]) -> str | None:
    if key in idx:
        return idx[key]
    toks = key.split()
    for n in range(len(toks) - 1, 0, -1):
        cand = " ".join(toks[:n])
        if cand in idx:
            return idx[cand]
    return None


def resolve_excluded(key: str, ex_idx: dict[str, str]) -> str | None:
    """A component is excluded when the whole key, or its head token (Spanish head noun first), names an
    excluded substance. A mention deeper in the key ("cromo picolinato ... insulina") is not a prescription."""
    if key in ex_idx:
        return ex_idx[key]
    toks = key.split()
    if toks and toks[0] in ex_idx:
        return ex_idx[toks[0]]
    if len(toks) > 1 and " ".join(toks[:2]) in ex_idx:
        return ex_idx[" ".join(toks[:2])]
    # a distinctive substance name (>= 5 chars) anywhere in the key still excludes ("batido mezcla viggro");
    # short codes (t3, gh, k) only count as whole key or head to avoid false positives
    for t in toks[1:]:
        if len(t) >= 5 and t in ex_idx and t not in ("insulina",):     # "cromo ... absorcion insulina" is a description
            return ex_idx[t]
    return None


# --------------------------------------------------------------------------- #
# Build                                                                        #
# --------------------------------------------------------------------------- #

# A key frequent enough to become its own canonical food still has to LOOK like a food name. Frequency alone is
# not evidence of foodness: once the AGUA slot is read (dataset-v3), instruction text repeats often enough to pass
# any threshold, and the catalogue acquired canonicals called "a tragos pequeños durante todo el día contando el
# agua de los batidos" and an embedded image's file name. Raising min_own does not fix that -- the junk is more
# frequent than several real foods (bicarbonato appears 102 times, mantequilla once) -- so the guard is structural:
# a food name in this corpus is a short noun phrase, never a sentence, a file name or a single letter.
_NOT_A_FOOD_NAME = re.compile(
    r"^\W*$"                                             # punctuation only
    r"|^\w$"                                             # a single character
    r"|\.(png|jpe?g|gif|bmp|pdf|docx?|odt|rtf|xlsx?)$"    # a file name
    r"|[0-9a-f]{8}-[0-9a-f-]{8,}"                        # a UUID, which is what an embedded image is called
    r"|^(a|en|con|de|del|por|para|sin|contando|mejorar|evitar|tomar|beber|comer|hacer|durante|antes|despu[eé]s)\b"
    r"|\d+\s*(gr?s?|gramos?|ml|cl|kg|litros?|unidades?)\b"   # carries a quantity: that is an item, not a food name
    r"|\.\-",                                                # a header separator that leaked into the key
    re.I,
)
MAX_CANONICAL_WORDS = 6
MAX_CANONICAL_CHARS = 40


def looks_like_a_food_name(raw: str) -> bool:
    """Whether a frequent unmapped key may be promoted to its own canonical food."""
    name = (raw or "").strip()
    if not name or len(name) > MAX_CANONICAL_CHARS or len(name.split()) > MAX_CANONICAL_WORDS:
        return False
    return not _NOT_A_FOOD_NAME.search(name)


def build(components: list[dict], families: dict, excluded: dict, min_own: int):
    idx, fam_of = key_index(families)
    ex_idx = excluded_index(excluded)
    key_freq = Counter(normalize_key(c["food_text"]) for c in components)
    raw_examples: dict[str, Counter] = defaultdict(Counter)
    for c in components:
        raw_examples[normalize_key(c["food_text"])][c["food_text"]] += 1
    total = sum(key_freq.values())

    canon_freq: Counter = Counter()
    canon_keys: dict[str, Counter] = defaultdict(Counter)
    unmapped: Counter = Counter()
    excluded_hits: dict[str, Counter] = defaultdict(Counter)
    by = Counter()
    own_canonicals: set[str] = set()
    for k, n in key_freq.most_common():
        if not k or k in DESCRIPTOR_ONLY:
            unmapped["<descriptor-only>"] += n
            by["descriptor_only"] += n
            continue
        ex = resolve_excluded(k, ex_idx)
        if ex:
            excluded_hits[ex][k] += n
            by["excluded"] += n
            continue
        canon = resolve(k, idx)
        if canon is None and n >= min_own and looks_like_a_food_name(raw_examples[k].most_common(1)[0][0]):
            canon = raw_examples[k].most_common(1)[0][0].lower()
            own_canonicals.add(canon)
            by["own_canonical"] += n
        elif canon is None:
            unmapped[k] += n
            by["unmapped"] += n
            continue
        else:
            by["synonym" if k in idx else "prefix"] += n
        canon_freq[canon] += n
        canon_keys[canon][k] += n
    mapped = sum(canon_freq.values())
    return {
        "total": total, "distinct_keys": len(key_freq), "mapped": mapped,
        "unmapped": sum(v for k, v in unmapped.items() if k != "<descriptor-only>"),
        "descriptor_only": unmapped.get("<descriptor-only>", 0),
        "excluded": sum(sum(c.values()) for c in excluded_hits.values()),
        "canon_freq": canon_freq, "canon_keys": canon_keys, "fam_of": fam_of, "own": own_canonicals,
        "unmapped_keys": unmapped, "excluded_hits": excluded_hits, "raw_examples": raw_examples, "resolved_by": by,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parsed", type=Path, default=DATASET_DIR / "parsed_items.jsonl")
    ap.add_argument("--synonyms", type=Path, default=SYNONYMS_PATH)
    ap.add_argument("--excluded", type=Path, default=EXCLUDED_PATH)
    ap.add_argument("--brands", type=Path, default=BRAND_MAP_PATH)
    ap.add_argument("--min-own", type=int, default=10, help="occurrences for a key without synonym to become its own canonical food")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--propose", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "foods.json")
    args = ap.parse_args()

    comps, counts = load_components(args.parsed)
    families = load_json(args.synonyms)["families"]
    families = merge_brands(families, load_json(args.brands))
    excluded = load_json(args.excluded)
    r = build(comps, families, excluded, args.min_own)
    denominator = r["total"]                      # every food component, excluded substances included
    coverage = r["mapped"] / denominator
    summary = {
        "components_total": counts["components_total"], "noise_components": counts["noise"],
        "instruction_components": counts["instructions"], "food_components_without_text": counts["food_without_text"],
        "food_components_denominator": denominator, "distinct_keys": r["distinct_keys"],
        "mapped": r["mapped"], "unmapped": r["unmapped"], "descriptor_only": r["descriptor_only"], "excluded_substances": r["excluded"],
        "coverage_pct": round(100 * coverage, 2),
        "coverage_pct_excluding_excluded_from_denominator": round(100 * r["mapped"] / max(1, denominator - r["excluded"]), 2),
        "canonical_foods": len(r["canon_freq"]), "own_canonicals_without_family": len(r["own"]),
        "families": len(families), "resolved_by": dict(r["resolved_by"]), "min_own": args.min_own,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    excluded_out = [{"name": e["name"], "status": e["status"], "reason": e["reason"],
                     "occurrences": sum(r["excluded_hits"].get(e["name"], Counter()).values()),
                     "keys_found": dict(r["excluded_hits"].get(e["name"], Counter()).most_common())}
                    for e in excluded["substances"]]

    if args.propose:
        proposal = {"summary": summary,
                    "canonical": [{"canonical_name": c, "family": r["fam_of"].get(c), "frequency": n,
                                   "keys": [{"key": k, "n": kn, "raw_examples": [x for x, _ in r["raw_examples"][k].most_common(3)]}
                                            for k, kn in r["canon_keys"][c].most_common()]}
                                  for c, n in r["canon_freq"].most_common()],
                    "own_canonicals_without_family": sorted(r["own"]),
                    "excluded": excluded_out,
                    "unmapped_top": [{"key": k, "n": n, "raw_examples": [x for x, _ in r["raw_examples"][k].most_common(3)]}
                                     for k, n in r["unmapped_keys"].most_common(150) if k != "<descriptor-only>"]}
        out = DATASET_DIR / "food_catalog_proposal.json"
        out.write_text(json.dumps(proposal, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(f"proposal written to {out}")
        print("\n== own canonicals without family (review) ==")
        for c in sorted(r["own"], key=lambda x: -r["canon_freq"][x]):
            print(f"  {r['canon_freq'][c]:5d}  {c}")
        print("\n== excluded substances found ==")
        for e in excluded_out:
            if e["occurrences"]:
                print(f"  {e['occurrences']:4d}  {e['name']:28s} [{e['status']}] {e['keys_found']}")
        return 0

    foods = []
    for fid, (c, n) in enumerate(r["canon_freq"].most_common(), start=1):
        keys = [k for k, _ in r["canon_keys"][c].most_common()]
        foods.append({"id": fid, "canonical_name": c, "family": r["fam_of"].get(c), "frequency": n,
                      "synonyms": sorted({x for k in keys for x, _ in r["raw_examples"][k].most_common(5)} - {c}),
                      "keys": keys})
    args.out.write_text(json.dumps({"summary": summary, "foods": foods}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (DATASET_DIR / "excluded_substances.json").write_text(
        json.dumps({"criterion": excluded["_doc"], "substances": excluded_out}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (DATASET_DIR / "food_catalog_unmapped.json").write_text(
        json.dumps([{"key": k, "n": n, "raw_examples": [x for x, _ in r["raw_examples"][k].most_common(3)]}
                    for k, n in r["unmapped_keys"].most_common() if k != "<descriptor-only>"], ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    (DATASET_DIR / "build_food_catalog_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"foods.json written: {len(foods)} canonical foods, coverage {100*coverage:.2f} % of {denominator} food components")
    return 0


if __name__ == "__main__":
    sys.exit(main())
