# -*- coding: utf-8 -*-
"""
E1.1 — Parse free-text meal items into structured components.

    "150 gr Pollo / 160 gr Pavo / 180 gr Lomo"      -> 3 components, same alternative_group
    "1 cucharada sopera de aceite de oliva virgen extra"
                                                    -> quantity 1, unit TABLESPOON, food "aceite de oliva virgen extra"
    "250 ml leche Almendras o Yogurt batido Natural" -> alternatives split on " o " as well as "/"
    "2 claras de huevo y 2 yemas con 1 lata de atún" -> 3 components, same compound_group
    "NADA DURANTE 1 HORA"                            -> is_instruction, no food
    "1 kiwi"                                         -> quantity 1, unit PIECE, food "kiwi"

Design rules (the bugs of the legacy vocabulary are NOT repeated):
  * the food name is never truncated;
  * the preposition that follows a unit ("cucharada sopera DE aceite") is consumed with the unit;
  * units map to the closed `domain.Unit` set; a unit word outside the set (cazo, vaso, taza...)
    is kept in `raw_unit`, counted and reported — never invented into the enum;
  * three cases are distinguished: food with quantity, food without quantity (value None),
    instruction without food (`is_instruction=True`, `food_text=None`).

CLI:  python pipeline/src/pipeline/parse_items.py --diets $FPS_DATASET_DIR/diets.jsonl \
          --out $FPS_DATASET_DIR/parsed_items.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR  # noqa: E402,F401  (also puts the repo root on sys.path)
from pipeline.parsed_item import ParsedItem  # noqa: E402
from finalprosports.domain.model import Quantity, Unit  # noqa: E402

# --------------------------------------------------------------------------- #
# Normalisation helpers                                                        #
# --------------------------------------------------------------------------- #

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(s).lower()).strip()


def clean_spaces(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" .;,:-–—|*\"'“”«»")


# --------------------------------------------------------------------------- #
# Lexicons                                                                     #
# --------------------------------------------------------------------------- #

UNIT_LEXICON: dict[str, Unit] = {
    "g": Unit.GRAM, "gr": Unit.GRAM, "grs": Unit.GRAM, "gramo": Unit.GRAM, "gramos": Unit.GRAM, "gram": Unit.GRAM, "grm": Unit.GRAM,
    "kg": Unit.GRAM, "kilo": Unit.GRAM, "kilos": Unit.GRAM,
    "ml": Unit.MILLILITER, "mililitro": Unit.MILLILITER, "mililitros": Unit.MILLILITER, "cl": Unit.MILLILITER,
    "l": Unit.MILLILITER, "litro": Unit.MILLILITER, "litros": Unit.MILLILITER,
    "cucharada": Unit.TABLESPOON, "cucharadas": Unit.TABLESPOON, "cda": Unit.TABLESPOON, "cdas": Unit.TABLESPOON,
    "cucharon": Unit.TABLESPOON, "cucharones": Unit.TABLESPOON, "cucharada.": Unit.TABLESPOON, "cuharada": Unit.TABLESPOON,
    "cuharadas": Unit.TABLESPOON, "cuchara": Unit.TABLESPOON, "cucharda": Unit.TABLESPOON, "cucharadas.": Unit.TABLESPOON,
    "cucharadita": Unit.TEASPOON, "cucharaditas": Unit.TEASPOON, "cdta": Unit.TEASPOON, "cdtas": Unit.TEASPOON,
    "cucharilla": Unit.TEASPOON, "cucharillas": Unit.TEASPOON,
    "lata": Unit.CAN, "latas": Unit.CAN, "latita": Unit.CAN, "latitas": Unit.CAN,
    "loncha": Unit.SLICE, "lonchas": Unit.SLICE, "lonja": Unit.SLICE, "lonjas": Unit.SLICE, "rodaja": Unit.SLICE,
    "rodajas": Unit.SLICE, "rebanada": Unit.SLICE, "rebanadas": Unit.SLICE, "tajada": Unit.SLICE, "tajadas": Unit.SLICE,
    "filete": Unit.SLICE, "filetes": Unit.SLICE,
    "punado": Unit.HANDFUL, "punados": Unit.HANDFUL, "punadito": Unit.HANDFUL, "punaditos": Unit.HANDFUL,
    "diente": Unit.CLOVE, "dientes": Unit.CLOVE,
    "chorrito": Unit.DASH, "chorritos": Unit.DASH, "chorro": Unit.DASH, "chorreon": Unit.DASH, "pizca": Unit.DASH,
    "pizcas": Unit.DASH, "poquito": Unit.DASH, "poco": Unit.DASH,
    "pieza": Unit.PIECE, "piezas": Unit.PIECE, "unidad": Unit.PIECE, "unidades": Unit.PIECE, "ud": Unit.PIECE,
    "uds": Unit.PIECE, "u": Unit.PIECE,
    "cazo": Unit.SCOOP, "cazos": Unit.SCOOP, "cazito": Unit.SCOOP, "cazitos": Unit.SCOOP, "scoop": Unit.SCOOP, "scoops": Unit.SCOOP,
    "medida": Unit.SCOOP, "medidas": Unit.SCOOP,
    "capsula": Unit.CAPSULE, "capsulas": Unit.CAPSULE, "caps": Unit.CAPSULE, "perla": Unit.CAPSULE, "perlas": Unit.CAPSULE,
    "tableta": Unit.CAPSULE, "tabletas": Unit.CAPSULE, "pastilla": Unit.CAPSULE, "pastillas": Unit.CAPSULE,
    "comprimido": Unit.CAPSULE, "comprimidos": Unit.CAPSULE, "gragea": Unit.CAPSULE, "grageas": Unit.CAPSULE,
}
UNIT_MULTIPLIER = {"kg": 1000.0, "kilo": 1000.0, "kilos": 1000.0, "cl": 10.0, "l": 1000.0, "litro": 1000.0, "litros": 1000.0}
# unit-like words that are NOT in the closed set: quantity kept, unit NONE, raw_unit recorded
UNCOVERED_UNITS = {
    "dosis",
    "vaso", "vasos", "vasito", "vasitos", "taza", "tazas", "tazon", "tazones", "bol", "cuenco", "plato", "platos",
    "racion", "raciones",
    "sobre", "sobres", "bote", "botes", "botella", "botellas", "tarrina", "tarrinas", "tarro", "tarros",
    "paquete", "paquetes", "bolsa", "bolsas", "gota", "gotas", "ampolla", "ampollas", "porcion", "porciones",
    "trozo", "trozos", "hoja", "hojas", "ramita", "ramitas", "rama", "ramas", "brick", "bricks", "tetrabrick",
    "copa", "copas", "chupito", "chupitos", "onza", "onzas", "barra", "barras", "bola", "bolas",
    "vial", "viales", "chorreoncito", "pellizco", "puntita", "punta", "cucharon",
}
TABLESPOON_QUALIFIERS = {"sopera", "soperas", "grande", "grandes", "colmada", "colmadas", "rasa", "rasas", "llena", "llenas", "generosa", "generosas"}
TEASPOON_QUALIFIERS = {"pequena", "pequenas", "postre", "cafe", "te", "moka", "pequenita", "pequenitas", "chica", "chicas"}
PREPOSITIONS = ("de la ", "de las ", "de los ", "del ", "de ", "d ")

WORD_NUMBERS = {"un": 1.0, "uno": 1.0, "una": 1.0, "dos": 2.0, "tres": 3.0, "cuatro": 4.0, "cinco": 5.0, "seis": 6.0,
                "medio": 0.5, "media": 0.5, "1/2": 0.5, "½": 0.5, "¼": 0.25, "¾": 0.75}
NUM_TOKEN = r"(?:\d+⁄\d+|\d+\s*(?:½|1⁄2)|\d+(?:[.,]\d+)?|½|¼|¾)"   # longest forms first (fractions before plain ints)
NUM_RE = re.compile(rf"^\s*(?P<num>{NUM_TOKEN})\s*(?P<rest>.*)$", re.S)
NUM_RE_WORD = re.compile(r"^\s*(?P<num>un|uno|una|dos|tres|cuatro|cinco|seis|medio|media)\s+(?P<rest>.+)$", re.I)
FRACTION_RE = re.compile(r"(?<!\d)([1-9])/([2-9])(?!\d)")   # 1/2, 1/4, 3/4 -> fraction, not an alternative

# right-hand side words after " o " that describe the SAME food (do not split)
ADJECTIVE_GUARD = {
    "natural", "griego", "griega", "integral", "integrales", "blanco", "blanca", "desnatado", "desnatada", "semidesnatado",
    "semidesnatada", "fresco", "fresca", "congelado", "congelada", "cocido", "cocida", "cocidos", "cocidas", "crudo", "cruda",
    "plancha", "horno", "vapor", "hervido", "hervida", "asado", "asada", "entero", "entera", "light", "normal", "virgen",
    "ecologico", "ecologica", "verde", "verdes", "rojo", "roja", "negro", "negra", "dulce", "salado", "salada", "liquido",
    "liquida", "caliente", "frio", "fria", "tostado", "tostada", "molido", "molida", "rallado", "rallada", "triturado",
    "triturada", "batido", "batida", "picado", "picada", "troceado", "troceada", "sin", "con", "bajo", "baja", "light",
    "grande", "pequeno", "pequena", "mediano", "mediana", "maduro", "madura", "seco", "seca", "secos", "secas", "similar",
    "parecido", "parecida", "equivalente", "igual", "menos", "mas", "vegetal", "animal", "desnatados", "enteros",
    "azul", "amarillo", "morado", "oscuro", "claro", "extra", "suave", "fuerte", "curado", "curada", "tierno", "tierna",
    "no", "gas", "hielo", "limon", "leche", "asados", "asadas", "hervidos", "hervidas", "crudos", "crudas", "salteado",
    "salteada", "salteados", "salteadas", "cocinado", "cocinada", "cocinados", "cocinadas", "guisado", "guisada", "vaporizado",
    "crudas", "tostadas", "hervido", "hervida", "escurrido", "escurrida", "lavado", "lavada", "lavadas", "picados", "picadas",
    "troceados", "troceadas", "pelado", "pelada", "peladas", "pelados", "descongelado", "descongelada", "templado", "templada",
    "rallados", "ralladas", "revuelto", "revuelta", "revueltos", "revueltas", "duro", "dura", "duros", "duras", "pasado", "pasada",
    "cocidas", "cocidos", "asado", "asada", "escalfado", "escalfados", "pochado", "pochados", "salteado",
}
# fixed expressions where "con" / "y" do NOT separate two foods
FIXED_EXPRESSIONS = (
    "cafe con leche", "arroz con leche", "leche con cacao", "leche con cafe", "te con leche", "agua con gas",
    "agua con limon", "agua con hielo", "pan con tomate", "tortilla francesa con", "yogur con", "yogurt con",
    "sin lactosa y sin azucar", "sin azucar y sin lactosa", "macarrones con", "espaguetis con", "arroz con",
    "pollo con curry", "cafe con hielo", "te con limon", "zumo con",
)
COMPOUND_SPLIT_RE = re.compile(r"\s+(?:y|e|con|\+|junto con|acompanado de|acompanada de)\s+|\s*\+\s*", re.I)
ALT_WORD_RE = re.compile(r"\s+(?:o|ó|u|o bien)\s+", re.I)
PAREN_RE = re.compile(r"\(([^()]*)\)")

INSTRUCTION_START = re.compile(
    r"^(?:nada\b|no\b|ninguno|ninguna|tomar\b|toma\b|tomarlo|tomarla|beber\b|bebe\b|comer\b|come\b|esperar|espera\b|durante\b|"
    r"antes de|despues de|al levantar|al acostar|al terminar|al acabar|si\b|cuando\b|solo\b|opcional|importante|nota\b|"
    r"recuerda|evita\b|evitar|maximo|minimo|cada\b|entre\b|lo mas|libre\b|a elegir|ayuno|hasta\b|ir\b|hacer\b|haz\b|"
    r"usar\b|puedes|se puede|sustituir|alternar|repetir|igual que|lo mismo|mismo\b|misma\b|ver\b|elegir|opcion\b|"
    r"dia\b|dias\b|cardio|entreno|entrenar|descanso|observaciones|obs\b|suplementos?:?$|batido de la|mitad de|"
    r"en ayunas$|a media|por la|por las|justo|inmediatamente|siempre|nunca|intentar|intenta\b|procura|preferible|"
    r"recomend|es mejor|mejor\b|tras\b|una vez|dos veces|a la hora|a las\b|antes\b|despues\b|luego\b|primero\b|"
    r"esto\b|esta comida|este\b|esa\b|ese\b|libre|comida libre|cena libre|desayuno libre|merienda libre|"
    r"controlar|controla\b|beber\b|hidrat|ingesta|respetar|cumplir|seguir\b|mantener|no olvid|acordarse|"
    r"pero\b|hay que|entre comidas|dormir|descansar|consejos?\b|posar\b|andar\b|caminar|correr|debe\b|deben\b|"
    r"deberia|tel\b|telefono|email|e mail|correos?\b|mail\b|web\b|www|http|hoja\b|pagina\b|fin de semana|"
    r"el fin de semana|los fines|de momento|momento\b|toma a|tomalo|tomala|litros contando|litros?\b|de media hora|"
    r"media hora|una hora|\d+ ?min\b|reduce\b|reducir|aumenta\b|aumentar|sube\b|subir\b|baja\b|bajar\b|quita\b|"
    r"quitar|anade\b|anadir|mete\b|meter\b|echa\b|echar\b|exprimir|exprime|masticar|comer despacio|despacio|"
    r"lo mejor|es importante|obligatorio|obligatoriamente|preferentemente|a gusto|al gusto|a demanda|libre eleccion|"
    r"a eleccion|elegir|elige\b|escoge|escoger|alterna\b|alternando|rotar|rota\b|vari[ae]\b|variar|"
    r"algunos?\b|algunas?\b|total\b|toma\b|tomas\b|exprimir|echarle|meterle|ponerle|anadirle|casi\b|"
    r"tipo \d|menos de|mas de|aprox|alrededor|unos \d|.*:$|"
    r"importantisimo|contando|mas tarde|en todas|en cada|en las comidas|mezcla de|mezclar|hyperlink|lunes|martes|"
    r"miercoles|jueves|viernes|sabado|domingo|dieta \d|semana \d|fase \d|"
    r"(?:tarde|manana|noche|mediodia|media tarde|media manana|desayuno|comida|cena|merienda|almuerzo|recena|"
    r"entrenamiento|entreno|mitad entreno|pre cena|post cena|suplementos?|suplementacion|alimentos|ejercicios?)$|"
    r"tener en cuenta|ojo\b|cuidado|atencion|prohibido|permitido|solo si|unicamente|en caso de|depende)"
)
TIME_ONLY = re.compile(r"^[\d\s.,:-]*(?:min|mins|minutos|minuto|h|hora|horas|seg|segundos)\b[\s\w.,:-]*$")
FOOD_HINT = re.compile(r"\b(gr|g|ml|cucharad|lata|pollo|pavo|arroz|avena|huevo|clara|pan|atun|leche|yogur|fruta|verdura|"
                       r"ensalada|pescado|carne|batido|proteina|queso|aceite|nueces|almendras|platano|manzana|kiwi|patata|"
                       r"boniato|pasta|legumbre|tortilla|jamon|cafe|te\b|agua|zumo|creatina|glutamina|bcaa)", re.I)


# --------------------------------------------------------------------------- #
# Core parsing                                                                 #
# --------------------------------------------------------------------------- #

HEADER_LABELS = re.compile(
    r"^(?:mitad (?:de(?:l)? )?entren\w*|entrenamiento|entreno|pre[ -]?cena|post[ -]?cena|pre[ -]?comida|post[ -]?comida|"
    r"[^:]{0,60}?(?:entren\w*|cardio|levant\w*|acost\w*|dormir|ayunas|minutos|min|horas?|manana|tarde|noche|mediodia|"
    r"desayun\w*|comida|cena|merienda|opcion \w+|alternativa|dia \d+|dias? \w+)\s*[^:\d]{0,20}|"
    r"antes de entrenar|despues de entrenar|antes del entrenamiento|despues del entrenamiento|merienda tarde|"
    r"media tarde[^:]*|media manana[^:]*|desayuno[^:]*|comida[^:]{0,25}|cena[^:]{0,25}|si haces cardio|si (?:no )?entrenas?(?: hoy)?|si tardas[^:]*|si te levantas[^:]*|"
    r"opcion \d|opci?on [a-d]|observaciones|recomendaciones|suplementos?|suplementacion|antes de dormir|al levantar\w*|"
    r"en ayunas|post ?entreno|pre ?entreno|durante el entren\w*|despues del? entren\w*|antes del? entren\w*|"
    r"al acostar\w*|media manana|media tarde|nota|importante|dias? de entreno|dias? de descanso|dias? sin entreno|"
    r"desayuno|comida|cena|merienda|almuerzo|recena|snack|intra ?entreno|cardio|pesas|fin de semana|entre horas|"
    r"tarde|manana|noche|mediodia|medio dia|madrugada|alternativa|alternativas|sustituto|sustitucion|extra|"
    r"la comida|la cena|el desayuno|la merienda|"
    r"[\d:.\-–\s]*(?:h|horas?)?|a las [\d:.\-–\s]*(?:h|horas?)?)\s*:\s*(?P<rest>.*)$", re.I)
SUPPLEMENT_PREFIX = re.compile(r"^\s*(?:suplementos?|suplementacion)\s*[.:\-–]+\s*", re.I)   # "SUPLEMENTO.- 1 Omega 3"
TIME_PREFIX = re.compile(r"^\s*[\d:.,/\-–\s]*\)\s*[:\-–]?\s*")
QTY_PAREN = re.compile(r"(\d[\d.,]*\s*(?:gr|grs|g|ml|latas?|cucharadas?|unidades?)\s*)\(([^()]+)\)", re.I)
MULTI_QTY = re.compile(r"(?<!\d)(\d+)(?:\s*,\s*\d+){1,}\s*(?=(?:gr|grs|g|ml)\b)", re.I)
NUM_RANGE = re.compile(r"(?<![\d,.])(\d+(?:[.,]\d+)?)\s*(?:o|u|a|-|–|/)\s*(\d+(?:[.,]\d+)?)\s*(?=[A-Za-zÁÉÍÓÚÑáéíóúñ½])")


def _mean(a: str, b: str) -> str:
    x, y = float(a.replace(",", ".")), float(b.replace(",", "."))
    m = (x + y) / 2
    return str(int(m)) if m == int(m) else f"{m:g}"


def preprocess_layout(text: str) -> str:
    """Stage 1 (before note extraction): supplement prefix, broken time prefixes, quantity + (alternatives)."""
    t = SUPPLEMENT_PREFIX.sub("", text)
    if re.match(r"^\s*[\d:.,/\-–\s]*\)", t):
        t = TIME_PREFIX.sub("", t)                       # "45): 1 batido" -> "1 batido"
    t = re.sub(r"(?<=[A-Za-zÁÉÍÓÚÑáéíóúñ])(?=\d+(?:[.,]\d+)?\s*(?:gr|grs|g|ml|cucharad|cuharad|lata|unidad|rodaja|loncha)\w*\b)",
               " + ", t)                                   # "Pescado Azul20 gr Nueces" -> "Pescado Azul + 20 gr Nueces"
    return QTY_PAREN.sub(lambda mm: f"{mm.group(1)} {mm.group(2)}", t)   # "200 gr (atun o pollo)" -> "200 gr atun o pollo"


def preprocess(text: str) -> tuple[str, list[str]]:
    """Stage 2 (after note extraction): header labels, multi-quantities, fractions, ranges. Returns (text, extra_notes)."""
    notes: list[str] = []
    t = text
    m = HEADER_LABELS.match(norm(t)) if ":" in t else None
    if m:
        # keep the text after the label, taken from the ORIGINAL string (same length after norm)
        idx = t.index(":")
        t = t[idx + 1:].strip()
    if MULTI_QTY.search(t):
        t = MULTI_QTY.sub(lambda mm: mm.group(1) + " ", t)            # "320, 300, 350 gr" -> first value
        notes.append("cantidades múltiples: se toma la primera")
    t = protect_fractions(t)                                          # "1/2 aguacate" is a fraction, not a range
    if NUM_RANGE.search(t):
        t = NUM_RANGE.sub(lambda mm: _mean(mm.group(1), mm.group(2)) + " ", t)   # "1 o 2 latas" -> "1.5 latas"
        notes.append("rango de cantidad: se toma la media")
    return t.strip(), notes


def extract_notes(text: str) -> tuple[str, str | None]:
    """Move parenthetical text to a note; keep the rest."""
    notes = [m.group(1).strip() for m in PAREN_RE.finditer(text) if m.group(1).strip()]
    stripped = PAREN_RE.sub(" ", text)
    stripped = re.sub(r"[()]", " ", stripped)          # unbalanced leftovers
    return clean_spaces(stripped), (" | ".join(notes) if notes else None)


NOISE_WORDS = {"tel", "tlf", "tfno", "telefono", "correo", "correos", "mail", "email", "e", "web", "www", "hyperlink", "kcal", "http", "https"}


def is_noise(text: str) -> bool:
    """Layout residue left by the signature block of the source documents (`("`, `tel`, `correos/mail:`...):
    no letters at all, or only signature labels once punctuation is removed."""
    words = re.findall(r"[a-z0-9ñ]+", norm(text))
    return not words or all(w in NOISE_WORDS for w in words)


def is_instruction(text: str) -> bool:
    n = norm(text)
    if not re.search(r"[a-z]", n):
        return True
    if TIME_ONLY.match(n):
        return True
    if INSTRUCTION_START.match(n) and not re.match(r"^(?:no|nada)\s+(?:de\s+)?(?:gr|g|ml|\d)", n):
        # instructions starting with a verb/adverb; a quantity+food after "no/nada" would be food
        return True
    return False


def parse_number(tok: str) -> float | None:
    t = tok.strip().lower().replace(",", ".").replace("⁄", "/")
    if t in WORD_NUMBERS:
        return WORD_NUMBERS[t]
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(½|1/2)", t)
    if m:
        return float(m.group(1)) + 0.5
    m = re.fullmatch(r"(\d+)/(\d+)", t)
    if m and int(m.group(2)):
        return int(m.group(1)) / int(m.group(2))
    try:
        return float(t)
    except ValueError:
        return None


def strip_preposition(text: str) -> str:
    n = norm(text)
    for p in PREPOSITIONS:
        if n.startswith(p):
            return clean_spaces(text[len(p):])
    return clean_spaces(text)


def parse_quantity(text: str) -> tuple[Quantity, str]:
    """Return (quantity, remaining food text)."""
    m = NUM_RE.match(text) or NUM_RE_WORD.match(text)
    if not m:
        toks0 = text.split()
        first0 = norm(toks0[0]).rstrip(".") if toks0 else ""
        if first0 in UNIT_LEXICON and len(toks0) > 1 and first0 not in ("u", "l", "g"):
            unit0 = UNIT_LEXICON[first0]
            rest0 = strip_preposition(" ".join(toks0[1:]))
            if unit0 is Unit.TABLESPOON and toks0[1:] and norm(toks0[1]) in TABLESPOON_QUALIFIERS | TEASPOON_QUALIFIERS:
                unit0 = Unit.TEASPOON if norm(toks0[1]) in TEASPOON_QUALIFIERS else unit0
                rest0 = strip_preposition(" ".join(toks0[2:]))
            if re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", rest0):
                return Quantity(None, unit0), clean_spaces(rest0)
        return Quantity(None), clean_spaces(text)
    value = parse_number(m.group("num"))
    rest = m.group("rest").strip()
    if value is None:
        return Quantity(None), clean_spaces(text)
    # unit token(s)
    toks = rest.split()
    if not toks:
        return Quantity(value, Unit.NONE), ""
    first = norm(toks[0]).rstrip(".")
    unit, raw_unit, consumed = Unit.NONE, None, 0
    if first in UNIT_LEXICON:
        unit, consumed = UNIT_LEXICON[first], 1
        if first in UNIT_MULTIPLIER:
            value = value * UNIT_MULTIPLIER[first]
        if unit is Unit.TABLESPOON and len(toks) > 1:
            q = norm(toks[1])
            if q in TEASPOON_QUALIFIERS or (q == "de" and len(toks) > 2 and norm(toks[2]) in TEASPOON_QUALIFIERS):
                unit = Unit.TEASPOON
                consumed = 2 if q != "de" else 3
            elif q in TABLESPOON_QUALIFIERS:
                consumed = 2
    elif first in UNCOVERED_UNITS:
        singular = first[:-1] if first.endswith("s") and first[:-1] in UNCOVERED_UNITS else first
        unit, raw_unit, consumed = Unit.NONE, singular, 1
        if len(toks) > 1 and norm(toks[1]) in TABLESPOON_QUALIFIERS | TEASPOON_QUALIFIERS:
            consumed = 2
    else:
        unit = Unit.PIECE                     # "1 kiwi", "2 claras": implicit piece
    food = " ".join(toks[consumed:])
    if consumed:
        food = strip_preposition(food)
    if consumed and not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", food):
        # "2 filetes", "1 lata": the unit word is the only food information
        return Quantity(value, Unit.PIECE, raw_unit), clean_spaces(" ".join(toks[:consumed]))
    return Quantity(value, unit, raw_unit), clean_spaces(food)


def protect_fractions(text: str) -> str:
    return FRACTION_RE.sub(lambda m: f"{m.group(1)}⁄{m.group(2)}", text)


def split_alternatives(text: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"\s*/\s*", protect_fractions(text)):
        chunk = chunk.strip()
        if not chunk:
            continue
        sub = ALT_WORD_RE.split(chunk)
        if len(sub) == 1:
            parts.append(chunk)
            continue
        merged = [sub[0]]
        for piece in sub[1:]:
            piece = piece.strip()
            words = norm(piece).split()
            left_last = norm(merged[-1]).split()[-1] if norm(merged[-1]).split() else ""
            same_food = _descriptor_only(piece)
            if same_food:
                merged[-1] = merged[-1] + " o " + piece
            else:
                merged.append(piece)
        parts.extend(p.strip() for p in merged if p.strip())
    # a comma list combined with " o " is an alternative list too
    if len(parts) > 1 or " o " in norm(text):
        out = []
        for p in parts:
            out.extend(x.strip() for x in p.split(",") if x.strip())
        parts = out
    glued: list[str] = []
    for piece in parts:
        if glued and _descriptor_only(piece):
            glued[-1] = glued[-1] + " o " + piece         # "crudas o tostadas sin sal": same food, other preparation
        else:
            glued.append(piece)
    return _glue_numeric(glued)


DESCRIPTOR_FILLERS = {"sin", "con", "sal", "azucar", "o", "y", "u", "e", "a", "la", "al", "de", "del", "en", "poco", "poca",
                      "muy", "bien", "mas", "menos", "tambien", "pero", "preferiblemente", "preferentemente"}


def _descriptor_only(piece: str) -> bool:
    words = norm(piece).split()
    return bool(words) and all(w in ADJECTIVE_GUARD or w in DESCRIPTOR_FILLERS for w in words)


def _glue_numeric(pieces: list[str]) -> list[str]:
    """Pieces without letters ("6", "9" from "omega 3, 6, 9") are not foods: glue them to the previous piece."""
    merged: list[str] = []
    for p in pieces:
        if merged and not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", p):
            merged[-1] = merged[-1] + ", " + p
        else:
            merged.append(p)
    return merged


# stand-alone food/supplement heads that never modify another food: two of them side by side without a
# preposition or conjunction are two items glued together ("aceite de oliva virgen extra tomate", "ZMA tribulus")
ATOMIC_HEADS = {
    "zma": "sup", "maca": "sup", "tribulus": "sup", "tribulu": "sup", "t90": "sup", "omnivit": "sup", "potasio": "sup", "magnesio": "sup",
    "calcio": "sup", "zinc": "sup", "hierro": "sup", "glutamina": "sup", "creatina": "sup", "carnitina": "sup", "bcaa": "sup", "bcaas": "sup",
    "eaa": "sup", "omega": "sup", "onagra": "sup", "cafeina": "sup", "taurina": "sup", "arginina": "sup", "aminoacidos": "sup",
    "l-carnitina": "sup", "glutamina": "sup",
    "tomate": "veg", "pepino": "veg", "cebolla": "veg", "lechuga": "veg", "espinacas": "veg", "brocoli": "veg", "zanahoria": "veg",
    "aguacate": "fat", "aceite": "fat", "nueces": "fat", "almendras": "fat",
    "huevo": "prot", "huevos": "prot", "pollo": "prot", "pavo": "prot", "atun": "prot", "salmon": "prot", "merluza": "prot", "ternera": "prot",
    "pescado": "prot",
    "patata": "carb", "boniato": "carb", "quinoa": "carb", "arroz": "carb", "avena": "carb", "pasta": "carb", "pan": "carb",
    "kiwi": "fruit", "manzana": "fruit", "platano": "fruit", "naranja": "fruit",
    # dairy heads (leche, queso, yogur) are deliberately absent: they take glued modifiers ("leche almendras", "yogur griego")
}
JOINERS = {"de", "del", "con", "y", "e", "o", "u", "al", "a", "la", "el", "en", "sin", "para", "por", "+", "/", "ni", "las", "los"}
QTY_BOUNDARY = re.compile(r"\s+(?:en|con|y|mas|más)\s+(?=\d+(?:[.,]\d+)?\s*(?:gr|grs|g|ml|cucharad|lata|unidad|cazo|capsula|perla)\w*\b)", re.I)


def split_juxtaposed(text: str) -> tuple[list[str], str]:
    """Return (pieces, mode). mode 'compound' when heads of different families are glued, 'alternatives' when
    two heads of the same family are glued ("pollo pavo"), 'single' otherwise."""
    words = text.split()
    normw = [norm(w).strip(".,;:()") for w in words]
    cut_positions, kinds = [], []
    last_head_idx = None
    for i, w in enumerate(normw):
        if w in ATOMIC_HEADS:
            if last_head_idx is not None:
                j = i - 1
                while j > last_head_idx and (normw[j].isdigit() or normw[j] in UNIT_LEXICON or normw[j] in UNCOVERED_UNITS):
                    j -= 1
                prev = normw[j] if j > last_head_idx else None      # None: heads are adjacent
                if prev is None or prev not in JOINERS:
                    cut_positions.append(j + 1)                       # digits/units travel with the second head ("ZMA 1 MACA")
                    kinds.append((ATOMIC_HEADS[w], ATOMIC_HEADS[normw[last_head_idx]]))
            last_head_idx = i
    if not cut_positions:
        return [text], "single"
    pieces, start = [], 0
    for cut in cut_positions:
        pieces.append(" ".join(words[start:cut]))
        start = cut
    pieces.append(" ".join(words[start:]))
    # two proteins / two carbs side by side are alternatives ("pollo pavo"); anything else is eaten together
    mode = "alternatives" if all(a == b and a in ("prot", "carb") for a, b in kinds) else "compound"
    return [p for p in pieces if p.strip()], mode


def split_compound(text: str) -> list[str]:
    n = norm(text)
    if any(expr in n for expr in FIXED_EXPRESSIONS):
        return [text]
    text = QTY_BOUNDARY.sub(" + ", text)                 # "Avena en 275 ml de leche de soja" -> two foods
    pieces = [p.strip() for p in COMPOUND_SPLIT_RE.split(text) if p and p.strip()]
    # comma lists without alternatives are things eaten together
    out = []
    for p in pieces:
        out.extend(x.strip() for x in p.split(",") if x.strip())
    # descriptors ("sin lactosa", "al vapor") are not foods: glue them back to the previous piece
    merged: list[str] = []
    for p in _glue_numeric(out):
        if MEAL_REFERENCE.match(norm(p)):
            continue                                   # "con la comida", "en cada comida": timing, not a food
        if merged and _descriptor_only(p):
            merged[-1] = merged[-1] + " " + p          # "..., sin sal": descriptor of the previous food
            continue
        if merged and re.match(r"^(sin|con|al|a la|a las|en|para|de|del|bajo|baja|light|o)\b", norm(p)):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged or [text]


MEAL_REFERENCE = re.compile(r"^(?:la|las|el|los|cada|todas?|todos?|una|un)\s+(?:comidas?|cenas?|desayunos?|meriendas?|"
                            r"entrenos?|entrenamientos?|cardio|dias?|tomas?|batidos? de las horas)\b|^(?:despues|antes|durante)\b")


def parse_item(raw: str, group_prefix: str) -> list[ParsedItem]:
    """Parse one raw meal item into components. `group_prefix` (diet::slot::position) makes group ids unique."""
    if is_noise(raw):
        return [ParsedItem(raw_text=raw, food_text=None, quantity=Quantity(None), is_instruction=False, is_noise=True)]
    stage1, note = extract_notes(preprocess_layout(raw))
    text, extra = preprocess(stage1)
    if extra:
        note = " | ".join(([note] if note else []) + extra)
    if not text or is_instruction(text):
        # «No ingerir nada durante 1 hora después de entrenar EN AYUNAS **o** 1 Batido de 40gr proteínas con 30 gr
        # Amilopeptinas + 2 Sales minerales» es una instrucción Y un alimento: la condición y su alternativa. Juzgada
        # entera se descartaba, y con ella el post-entreno completo de esas dietas. Se rescatan las ramas que empiezan
        # por CANTIDAD, que es el mismo criterio que el bucle de abajo aplica un nivel más adentro (`is_instruction(comp)
        # and not NUM_RE.match(comp)`): una rama con número y unidad delante es una ración, no una indicación.
        # Sin el número el rescate mete basura -- medido sobre el corpus: 203 líneas con «alguna rama no-instrucción»
        # frente a 37 con «alguna rama con cantidad», y de las 203 la mayoría son jirones de prosa («camina en ayunas»,
        # «integral y sin azúcares añadidos»). Las 37 son batidos, café, agua y suplementos.
        # …salvo la pauta de hidratación. «4 litros de Agua al día a tragos pequeños» tiene número y unidad y pasa el
        # filtro de arriba, pero no es la ración de esa franja: es la indicación diaria, escrita donde cayó. Rescatarla
        # metía agua como componente en 11 de las 37 líneas y en un dorado llegó a DESPLAZAR al batido del post-entreno
        # («40 gr Batido de proteínas» -> «3000 ml Agua»). El litro es su unidad de pauta, nunca de ración: de los 68
        # componentes que escribe en litros, 56 son agua y los 12 restantes no resuelven a ningún alimento.
        rescued = [b for b in split_alternatives(text)
                   if not is_instruction(b) and NUM_RE.match(b) and not _LITRE.search(b)] if text else []
        if not rescued:
            return [ParsedItem(raw_text=raw, food_text=None, quantity=Quantity(None), is_instruction=True, note=note)]
        text = " / ".join(rescued)
    alternatives = split_alternatives(text)
    alt_group = f"{group_prefix}#alt" if len(alternatives) > 1 else None
    out: list[ParsedItem] = []
    first_qty: Quantity | None = None
    expanded: list[str] = []
    for alt in alternatives:
        jux, mode = split_juxtaposed(alt)
        if mode == "alternatives":
            expanded.extend(jux)                          # "pollo pavo" -> two alternatives
            alt_group = alt_group or f"{group_prefix}#alt"
        else:
            expanded.append(" + ".join(jux) if mode == "compound" else alt)   # glued different foods -> compound
    alternatives = expanded
    for a_idx, alt in enumerate(alternatives):
        components = split_compound(alt)
        comp_group = f"{group_prefix}#alt{a_idx}#comp" if len(components) > 1 else None
        for c_idx, comp in enumerate(components):
            if is_instruction(comp) and not NUM_RE.match(comp):
                # "..., y no tomar los batidos si no entrenas": a note glued to a food item
                out.append(ParsedItem(raw_text=raw, food_text=None, quantity=Quantity(None), is_instruction=True,
                                      alternative_group=alt_group, compound_group=comp_group, note=note))
                continue
            qty, food = parse_quantity(comp)
            if food and qty.has_amount and INSTRUCTION_START.match(norm(food)) and not FOOD_HINT.search(food):
                # "1 Exprimir un limón", "1 TOMA A MITAD DE ENTRENO": a dosage/instruction, not a food
                out.append(ParsedItem(raw_text=raw, food_text=None, quantity=Quantity(None), is_instruction=True,
                                      alternative_group=alt_group, compound_group=comp_group, note=note))
                continue
            if a_idx == 0 and c_idx == 0:
                first_qty = qty
            elif (alt_group and c_idx == 0 and not qty.has_amount and first_qty is not None and first_qty.has_amount
                  and len(components) == 1):
                # "200 gr atún, pollo o pavo": the quantity of the first alternative applies to the others
                qty = Quantity(first_qty.value, first_qty.unit, first_qty.raw_unit)
            if not food or not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", food):
                food_text = None
            else:
                food_text = food
            qty, food_text = promote_embedded_quantity(qty, food_text)
            out.append(ParsedItem(raw_text=raw, food_text=food_text, quantity=qty, is_instruction=False,
                                  alternative_group=alt_group, compound_group=comp_group, note=note))
    return out


# Una cantidad de masa o volumen ESCONDIDA dentro del nombre: «1 batido 48 gr Proteínas», «1 Batido de 60gr proteínas».
# El «1» de delante cuenta batidos, no gramos, y al canonicalizar a «batido de proteínas» los 48 gr desaparecían: la
# propuesta imprimía «1 unidad batido de proteínas» y el preparador señaló exactamente eso («el batido y la caseína,
# con sus gramos»). Medido sobre el corpus: 733 componentes traen la cantidad dentro del nombre, 631 de ellos batidos.
_LITRE = re.compile(r"\blitros?\b", re.I)
_EMBEDDED = re.compile(r"(?<![\w,.])(\d+(?:[.,]\d+)?)\s*(gr|grs|g|ml|mg|kg|l)\b(?![\w])", re.I)
_EMBEDDED_UNITS = {"gr": Unit.GRAM, "grs": Unit.GRAM, "g": Unit.GRAM, "kg": Unit.GRAM,
                   "ml": Unit.MILLILITER, "l": Unit.MILLILITER, "mg": Unit.GRAM}
_EMBEDDED_SCALE = {"kg": 1000.0, "l": 1000.0, "mg": 0.001}


def promote_embedded_quantity(qty: Quantity, food_text: str | None) -> tuple[Quantity, str | None]:
    """Sube al componente la cantidad que estaba dentro del nombre, y solo cuando no hay nada que decidir.

    Condiciones, deliberadamente estrechas: la cantidad leída es exactamente **1 unidad** (un multiplicador de 1 no
    aporta información, así que sustituirlo no pierde nada) y el nombre contiene **una sola** cantidad de masa o
    volumen. Con multiplicador distinto de 1 no se toca: «2 latas de atún de 80 gr» necesitaría decidir si el
    resultado son 80 g o 160, y eso sería inventar. Sobre el corpus: 655 componentes se promueven, 69 con
    multiplicador distinto de 1 y 9 con varias cantidades se quedan como están.
    """
    if food_text is None or qty.unit is not Unit.PIECE or qty.value != 1.0:
        return qty, food_text
    matches = _EMBEDDED.findall(food_text)
    if len(matches) != 1:
        return qty, food_text
    number, raw_unit = matches[0]
    value = float(number.replace(",", ".")) * _EMBEDDED_SCALE.get(raw_unit.lower(), 1.0)
    if value <= 0:
        return qty, food_text
    limpio = clean_spaces(_EMBEDDED.sub(" ", food_text)).strip(" .,-/")
    limpio = clean_spaces(re.sub(r"\b(?:de|del)\b\s*$", "", limpio, flags=re.I)).strip(" .,-/")
    if not limpio or not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", limpio):
        return qty, food_text                       # sin el número no queda nombre: mejor dejarlo entero
    return Quantity(value, _EMBEDDED_UNITS[raw_unit.lower()], raw_unit.lower()), limpio


def record(diet_id: str, slot: str, position: int, item: ParsedItem) -> dict:
    return {
        "diet_id": diet_id, "meal_slot": slot, "position": position,
        "raw_text": item.raw_text, "food_text": item.food_text,
        "quantity": item.quantity.value, "unit": item.quantity.unit.value, "raw_unit": item.quantity.raw_unit,
        "is_instruction": item.is_instruction, "is_noise": item.is_noise, "alternative_group": item.alternative_group,
        "compound_group": item.compound_group, "compound_item": item.compound_item, "note": item.note,
    }


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diets", type=Path, default=DATASET_DIR / "diets.jsonl")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "parsed_items.jsonl")
    ap.add_argument("--log", type=Path, default=DATASET_DIR / "parse_items_log.json")
    args = ap.parse_args()
    if not args.diets.exists():
        raise FileNotFoundError(f"Required input file not found: {args.diets}")
    diets = [json.loads(l) for l in args.diets.read_text(encoding="utf-8").splitlines() if l.strip()]

    stats = Counter()
    units, raw_units, instructions, no_food = Counter(), Counter(), Counter(), Counter()
    n_out = 0
    with args.out.open("w", encoding="utf-8", newline="\n") as fh:
        for d in diets:
            for slot, items in d["meals"].items():
                for pos, raw in enumerate(items):
                    stats["items"] += 1
                    comps = parse_item(raw, f"{d['id']}::{slot}::{pos}")
                    if len(comps) == 1 and comps[0].is_noise:
                        stats["noise"] += 1
                        stats["components"] += 1
                        fh.write(json.dumps(record(d["id"], slot, pos, comps[0]), ensure_ascii=False) + "\n")
                        n_out += 1
                        continue
                    if len(comps) == 1 and comps[0].is_instruction:
                        stats["instructions"] += 1
                        instructions[norm(raw)[:60]] += 1
                    if any(c.alternative_group for c in comps):
                        stats["items_with_alternatives"] += 1
                    if any(c.compound_group for c in comps):
                        stats["items_compound"] += 1
                    for c in comps:
                        stats["components"] += 1
                        if not c.is_instruction:
                            if c.quantity.has_amount:
                                stats["components_with_quantity"] += 1
                                units[c.quantity.unit.name] += 1
                                if c.quantity.raw_unit:
                                    raw_units[c.quantity.raw_unit] += 1
                            else:
                                stats["components_without_quantity"] += 1
                            if c.food_text is None:
                                stats["components_without_food_text"] += 1
                                no_food[norm(raw)[:60]] += 1
                        fh.write(json.dumps(record(d["id"], slot, pos, c), ensure_ascii=False) + "\n")
                        n_out += 1
    stats["records_written"] = n_out
    food_comps = stats["components"] - stats["instructions"] - stats["noise"]
    log = {"counts": dict(stats),
           "pct_items_with_quantity_component": round(100 * stats["components_with_quantity"] / max(1, food_comps), 1),
           "units": dict(units.most_common()), "uncovered_units": dict(raw_units.most_common(40)),
           "top_instructions": instructions.most_common(40), "top_components_without_food_text": no_food.most_common(25)}
    args.log.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in log.items() if k not in ("top_instructions", "top_components_without_food_text")}, ensure_ascii=False, indent=1))
    print("top instructions:", instructions.most_common(40))
    print("top components without food text:", no_food.most_common(25))
    return 0


if __name__ == "__main__":
    sys.exit(main())
