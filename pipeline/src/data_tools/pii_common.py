# -*- coding: utf-8 -*-
"""
Shared helpers for the anonymisation / sanitisation scripts of the TFM corpus.

GOLDEN RULE: no function in this module prints or returns personal text for
dumping. Detectors return counts, lengths, or masked tokens (first letter +
asterisks). Data VALUES stay in Spanish exactly as they appear in the corpus;
only identifiers, field names and messages are in English.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator

# --------------------------------------------------------------------------- #
# File I/O                                                                     #
# --------------------------------------------------------------------------- #

def require_file(path: Path) -> Path:
    """Fail loudly if a required input file is missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    return path


def load_records(path: Path) -> list:
    """Load a .json (list or dict) or .jsonl (one record per line) file."""
    path = require_file(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        return [{"k": k, "v": v} for k, v in data.items()]
    return data


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
# Patrones de custodia                                                         #
# --------------------------------------------------------------------------- #
# EL DETECTOR NO PUEDE LLEVAR EL DATO DENTRO. Los patrones que nombran al profesional —su nombre y su marca
# comercial— estaban escritos aquí, en `sanitize.py` y en `test_dataset.py`, y eso significaba que cada vez que se
# publicaba el código se publicaba su nombre en texto plano: exactamente lo que este módulo existe para evitar.
# Ahora viven en la CUSTODIA, fuera del árbol, y se leen de:
#   1. `FPS_PII_PATTERNS`, que puede ser la ruta de un fichero o los propios patrones separados por «|»;
#   2. `$FPS_DATASET_DIR/_private/pii_patterns.json` (donde el titular los tiene).
# Si no hay ninguno, la lista está VACÍA y quien audita tiene que ABORTAR, no pasar en verde: una auditoría sin su
# diccionario no dice «limpio», dice «no he podido mirar». Eso lo impone `require_custody_patterns`.
CUSTODY_ENV = "FPS_PII_PATTERNS"


def custody_patterns() -> tuple[str, ...]:
    """Los patrones del profesional, o una tupla vacía. Nunca lanza: decidir qué hacer sin ellos es de quien llama."""
    raw = os.environ.get(CUSTODY_ENV, "").strip()
    if raw:
        # SI PARECE UNA RUTA, TIENE QUE EXISTIR. Antes, una ruta que no existía se interpretaba como «patrones en
        # línea» y el patrón resultante era la propia ruta: no casaba con nada y la comprobación pasaba EN VERDE
        # habiendo mirado nada. Pasó al probar esto con una ruta relativa mal resuelta, y es el fallo más peligroso
        # que puede tener un detector: el que dice que está limpio porque no ha buscado.
        parece_ruta = any(c in raw for c in "/\\") or raw.lower().endswith((".json", ".txt", ".lst"))
        if parece_ruta:
            candidato = Path(raw)
            if not candidato.exists():
                raise FileNotFoundError(
                    f"{CUSTODY_ENV} apunta a un fichero que no existe: {raw}. Si querías dar los patrones en línea, "
                    f"no uses barras ni una extensión de fichero; si querías el fichero de custodia, revisa la ruta. "
                    f"No se continúa: una auditoría sin patrones diría «limpio» sin haber mirado.")
            return _read_patterns(candidato)
        return tuple(t.strip() for t in raw.split("|") if t.strip())
    dataset = os.environ.get("FPS_DATASET_DIR", "").strip()
    if dataset:
        # `FPS_DATASET_DIR` en el `.env` es RELATIVA a la raíz del repositorio, y estos scripts se ejecutan desde
        # `backend/` tanto como desde la raíz. Resolverla aquí evita que la custodia «desaparezca» según el cwd, que
        # es la peor forma de fallar: los patrones quedarían vacíos y la auditoría creería que no hay nada que buscar.
        ruta = Path(dataset)
        if not ruta.is_absolute():
            ruta = (Path(__file__).resolve().parents[3] / ruta).resolve()
        fichero = ruta / "_private" / "pii_patterns.json"
        if fichero.exists():
            return _read_patterns(fichero)
    return ()


def _read_patterns(path: Path) -> tuple[str, ...]:
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("patterns", data) if isinstance(data, dict) else data
        return tuple(str(t).strip() for t in items if str(t).strip())
    return tuple(l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))


def custody_alternation() -> str:
    """Los patrones como alternancia de expresión regular, o cadena vacía."""
    return "|".join(custody_patterns())


def custody_regex() -> "re.Pattern[str]":
    """Regex de los patrones; si no hay custodia, una que NO CASA NUNCA (`(?!)`), no una que casa con todo."""
    alt = custody_alternation()
    return re.compile(alt, re.I) if alt else re.compile(r"(?!)")


def require_custody_patterns(quien: str) -> tuple[str, ...]:
    """Los patrones, o un error con el motivo escrito. Para el código que sanea o audita el corpus REAL."""
    pats = custody_patterns()
    if not pats:
        raise FileNotFoundError(
            f"{quien}: no hay patrones de custodia. Se leen de {CUSTODY_ENV} (ruta o patrones separados por «|») o de "
            f"$FPS_DATASET_DIR/_private/pii_patterns.json. Sin ellos la auditoría NO puede decir que el árbol está "
            f"limpio: puede decir que no ha podido mirar, y eso no es lo mismo.")
    return pats


# --------------------------------------------------------------------------- #
# Normalisation                                                                #
# --------------------------------------------------------------------------- #

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{3,}")


def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm_token(s: str) -> str:
    return strip_accents(s).upper()


def mask(token: str) -> str:
    """'Apellido' -> 'A*******'. Used to show findings without revealing them."""
    if not token:
        return token
    return token[0] + "*" * (len(token) - 1)


def mask_text(s: str, tokens: set[str]) -> str:
    """Mask every word of `s` whose normalised form is in `tokens`."""
    def rep(m):
        t = m.group(0)
        return mask(t) if norm_token(t) in tokens else t
    return WORD_RE.sub(rep, s)


# --------------------------------------------------------------------------- #
# Field naming convention (Spanish source field -> English dataset field)      #
# Values are NOT translated.                                                   #
# --------------------------------------------------------------------------- #

FIELD_RENAME = {
    "cliente": "client_code", "code": "client_code",
    "sexo": "sex", "edad": "age", "edad_bucket": "age_bucket",
    "nivel_actividad": "activity_level", "altura_cm": "height_cm", "atleta": "is_athlete",
    "objetivo": "goal", "objetivos": "goals", "objetivos_clf": "classified_goals",
    "intolerancias": "intolerances", "alergias": "allergies",
    "operaciones": "surgeries", "lesiones": "injuries",
    "version_dieta": "diet_version", "n_dietas": "diet_count",
    "comidas": "meals", "notas": "notes", "deporte": "sport",
    "gustos_pos": "liked_foods", "gustos_neg": "disliked_foods",
}

# --------------------------------------------------------------------------- #
# Name dictionary (loaded in memory; NEVER printed)                            #
# --------------------------------------------------------------------------- #

# Words that coincide with surnames/first names in the name map but are food
# vocabulary or ordinary diet lexicon. Superset of FOODSTOP in extractor.py.
STOPWORDS = {
    # FOODSTOP from extractor.py
    "OLIVA", "OLIVAS", "MORA", "MORAS", "ROMERO", "SERRANO", "SERRANA", "BLANCO", "BLANCA",
    "MORENO", "MORENA", "RUBIO", "RUBIA", "PRIETO", "REY", "REYES", "LEON", "FLORES", "FLOR",
    "CAMPO", "CAMPOS", "RIOS", "RIO", "MAR", "NIETO", "BRAVO", "CALVO", "REDONDO", "GORDO",
    "MANZANO", "MANZANA", "NARANJO", "NARANJA", "LIMON", "PARRA", "SOL", "ROSA", "PERA",
    "PERAL", "SALINAS", "VEGA", "VERDE", "PIMIENTA", "SAL", "AJO", "HABA", "PESCADO", "CANO",
    "PRADO", "MONTE", "SIERRA", "VALLE", "PINO", "ROBLE", "LOBO", "GATO", "TORO", "CABRERA",
    "PLATA", "CASTANO", "CASTANA", "AVELLANO", "AVELLANA", "PALOMO", "PALOMA", "CONEJO",
    "PEREJIL", "ROMERA", "HIGUERA", "HIGO", "MELON", "CEREZO", "CEREZA", "ACEITUNO",
    "DEL", "DE", "LA", "LAS", "LOS", "Y", "SAN", "SANTA", "MARIA",
    # section headers and structural lexicon of the corpus
    "DIETA", "DIETAS", "CLIENTE", "OBJETIVO", "NOTAS", "COMIDA", "CENA", "DESAYUNO", "MERIENDA",
    "ALMUERZO", "ANTES", "ENTRENAR", "DESPUES", "MEDIA", "MANANA", "BATIDO", "POST", "PRE",
    "ENTRENO", "RECENA", "PARA", "CON", "SIN", "UNA", "UNO", "QUE", "POR", "MAS", "MENOS",
    "TODO", "TODA", "TODOS", "NADA", "ALGO", "BIEN", "MAL", "DIA", "DIAS", "SEMANA", "HORA",
    "HORAS", "AYUNO", "VOLUMEN", "DEFINICION", "MANTENIMIENTO", "CARGA", "DESCARGA", "FIBRA",
    "GRASA", "MASA", "MUSCULAR", "PESO", "ALTURA", "EDAD", "SEXO", "HOMBRE", "MUJER",
    "ELECTROLITOS", "CONTROLADA", "CONTROLADO", "SALUD", "REGLA", "REGLAS",
    # food and cooking
    "AGUA", "LECHE", "PAN", "ARROZ", "PASTA", "CARNE", "POLLO", "PAVO", "ATUN",
    "HUEVO", "HUEVOS", "CLARA", "CLARAS", "QUESO", "FRUTA", "VERDURA", "VERDURAS", "ENSALADA",
    "ACEITE", "VIRGEN", "EXTRA", "TOMATE", "LECHUGA", "CEBOLLA", "PATATA", "BONIATO", "AVENA",
    "NUECES", "ALMENDRAS", "PLATANO", "KIWI", "FRESAS", "YOGUR", "NATURAL", "PROTEINA",
    "PROTEINAS", "SUERO", "CREATINA", "GLUTAMINA", "BCAA", "BCAAS", "CAFE", "INFUSION",
    "SOPERA", "SOPERAS", "CUCHARADA", "CUCHARADAS", "GRAMOS", "UNIDAD", "UNIDADES",
    "GRANDE", "PEQUENO", "PEQUENA", "MEDIANO", "MEDIANA", "COCIDO", "COCIDA", "PLANCHA",
    "HORNO", "VAPOR", "CRUDO", "CRUDA", "FRESCO", "FRESCA", "LIGHT", "INTEGRAL", "DESNATADO",
    "DESNATADA", "SEMI", "NEGRO", "NEGRA", "ROJO", "ROJA", "AMARILLO", "AZUL",
    "SALMON", "MERLUZA", "TERNERA", "CERDO", "CORDERO", "JAMON", "LOMO", "SOLOMILLO",
    "PECHUGA", "FILETE", "FILETES", "LATA", "LATAS", "TARRINA", "VASO", "TAZA", "PUNADO",
    "MIEL", "CANELA", "VAINILLA", "COCO", "CACAO", "CHOCOLATE", "AZUCAR", "SACARINA", "STEVIA",
    "DULCE", "AMARGO", "PICANTE", "SUAVE", "FUERTE", "SALADO", "SALADA", "DORADO", "DORADA",
    "IBERICO", "IBERICA", "MANCHEGO", "MANCHEGA", "GALLEGA", "FRANCESA", "GRIEGA", "ITALIANA",
    "ROMANA", "ANDALUZ", "CATALANA", "NAVARRA", "ASTURIANA", "GRANADA", "GRANADAS", "CORAL",
    # false positives confirmed during the Phase 2 masked sweep (reviewed with the data owner)
    "ALIMENTOS", "ALIMENTO", "VINAGRE", "DURA", "DURO", "GYM", "PEZ", "LAVADO", "LAVADA",
    "LAVADOS", "LAVADAS", "MARIANO", "AGUACATE", "AGUACATES",
    # common words that coincide with name tokens, found by the whole-tree audit (Task B)
    "NUEVA", "NUEVO", "NUEVAS", "NUEVOS", "LISTA", "LISTO", "LISTAS", "ENTRENOS", "CARPETA", "CHORRO", "CHICA", "CHICAS", "CHICO",
    "GUISADO", "GUISADA", "PRESA", "PAPA", "PAPAS", "TOMILLO", "CORDERO", "PAPILLOTE", "PARRILLA", "BRASA", "CADENA", "CADENAS",
    "DELGADO", "DELGADA",  # adjective in profile goals ("extremamente delgada"), also a surname
    # calendar
    "DOMINGO", "LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO",
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE",
    "OCTUBRE", "NOVIEMBRE", "DICIEMBRE", "GRACIAS", "SALUDOS",
}

# Tokens allowed inside identifiers: id prefixes plus meal slots (meal chunks
# use `<diet_id>::<SLOT>`), both truncated (source) and expanded forms.
ID_ALLOWED = {"CLIENTE", "DIETA", "MD", "V", "S",
              "DESAYUNO", "MEDIA", "MANANA", "TARDE", "ALMUERZO", "COMIDA", "MERIENDA", "CENA", "RECENA",
              "ANTES", "MITAD", "ENTRENAMIENTO", "ENTRENAR", "DESPU", "DESPUES", "POST", "PRE", "ENTRENO", "BATIDO", "OTHER",
              # slots the v3 rebuild recognises that v2 collapsed into others (domain/model/meal_slot.py)
              "RECIEN", "LEVANTADO", "DORMIR", "AGUA", "SUPLEMENTOS"}


def load_name_tokens(name_map_path: Path, min_len: int = 3) -> set[str]:
    """
    Return the set of normalised tokens (no accents, upper case) found in the
    real names of the name map. Used as a detection dictionary. The content of
    the map is NEVER written to stdout.
    """
    nm = json.loads(require_file(name_map_path).read_text(encoding="utf-8"))
    toks: set[str] = set()
    for v in nm.values():
        for t in WORD_RE.findall(v):
            t = norm_token(t)
            if len(t) >= min_len:
                toks.add(t)
    return toks


class HashedNameSet:
    """Set-like view over the salted-SHA-256 dictionary (_private/name_tokens_hashed.json).
    `token in hashed_set` hashes the normalised token; no plaintext name is ever stored in the tree."""

    def __init__(self, path: Path):
        import hashlib
        data = json.loads(require_file(path).read_text(encoding="utf-8"))
        self._salt = data["salt"]
        self._hashes = set(data["name_tokens"])
        self.false_positives = frozenset(data.get("reviewed_false_positives", []))
        self.substituted = frozenset(data.get("substituted_tokens", []))
        self._h = lambda t: hashlib.sha256((self._salt + t).encode("utf-8")).hexdigest()
        self._cache: dict[str, str] = {}

    def digest(self, token: str) -> str:
        d = self._cache.get(token)
        if d is None:
            d = self._cache[token] = self._h(token)
        return d

    def __contains__(self, token: str) -> bool:
        return self.digest(token) in self._hashes

    def __len__(self) -> int:
        return len(self._hashes)

    def is_false_positive(self, token: str) -> bool:
        return self.digest(token) in self.false_positives


def load_name_set(name_map: Path | None = None, hashed: Path | None = None):
    """Plaintext dictionary when the name map is available (custody), hashed dictionary otherwise."""
    if name_map is not None and Path(name_map).exists():
        return load_name_tokens(name_map)
    if hashed is not None and Path(hashed).exists():
        return HashedNameSet(hashed)
    raise FileNotFoundError("Neither the plaintext name map nor the hashed dictionary is available")


def load_reviewed_false_positives(path: Path | None) -> set[str]:
    """
    Optional private list (JSON array of tokens) of dictionary hits reviewed by
    the data owner and declared non-personal (e.g. a supplement brand that
    coincides with a token of the name map). Kept out of the repository so the
    literal never appears in code or logs.
    """
    if path is None or not Path(path).exists():
        return set()
    return {norm_token(t) for t in json.loads(Path(path).read_text(encoding="utf-8")) if isinstance(t, str)}


def name_tokens_in(s: str, name_set: set[str], min_len: int = 3, use_stop: bool = True,
                   extra_stop: set[str] | None = None) -> list[str]:
    """Normalised tokens of `s` that belong to the name dictionary."""
    out = []
    hashed_fp = getattr(name_set, "is_false_positive", None)
    for t in WORD_RE.findall(s or ""):
        n = norm_token(t)
        if len(n) < min_len or n not in name_set:
            continue
        if use_stop and (n in STOPWORDS or (extra_stop and n in extra_stop) or (hashed_fp and hashed_fp(n))):
            continue
        out.append(n)
    return out


def alpha_tokens_not_allowed(s: str) -> list[str]:
    """Alphabetic tokens (>=3 chars) of an identifier that are not allowed lexicon."""
    return [norm_token(t) for t in WORD_RE.findall(s or "") if norm_token(t) not in ID_ALLOWED]


# --------------------------------------------------------------------------- #
# Regex PII detectors                                                          #
# --------------------------------------------------------------------------- #

DETECTORS: dict[str, re.Pattern] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    # Spanish mobile/landline; hex-letter lookarounds keep sha1/sha256 digests from matching
    "phone": re.compile(r"(?<![\dA-Fa-f])(?:\+?34[\s.-]?)?[6-9]\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}(?![\dA-Fa-f])"),
    "dni": re.compile(r"(?<![A-Za-z0-9])\d{8}[\s-]?[A-Za-z](?![A-Za-z0-9])"),
    "nie": re.compile(r"(?<![A-Za-z0-9])[XYZxyz][\s-]?\d{7}[\s-]?[A-Za-z](?![A-Za-z0-9])"),
    "iban": re.compile(r"(?<![A-Za-z0-9])ES\s?\d{2}(?:\s?\d{4}){5}(?![0-9])", re.I),
    "full_date": re.compile(r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-](?:19|20)\d{2}(?!\d)"),
    "birth_year": re.compile(r"(?<!\d)(?:19[3-9]\d|200\d)(?!\d)"),
    "url_or_domain": re.compile(r"https?://\S+|www\.\S+|\b[a-z0-9-]{3,}\.(?:es|com|net|org|info)\b|mailto:", re.I),
    "professional_domain": custody_regex(),      # de la CUSTODIA, nunca del código: ver custody_patterns()
    "marker_email": re.compile(r"\[EMAIL\]"),
    "marker_phone": re.compile(r"\[TEL\]"),
    "marker_name": re.compile(r"\[NOMBRE\]"),
    "marker_redacted": re.compile(r"\[REDACTADO\]"),
    "rtf_residue": re.compile(r"\{\\|\\par\b|\\fldrslt|\\[a-z]{2,}\d*\b|\\'[0-9a-fA-F]{2}"),
    "form_line": re.compile(r"_{4,}"),
    "raw_regex_label": re.compile(r"\[[a-záéíóú]{2,}\]"),
}

MEDICAL_RE = re.compile(
    r"cesar|di[aá]stasis|fractur|vertebr|hipotiroid|hipertiroid|tiroid|pr[oó]tesis|"
    r"antidepres|ansiol|tensi[oó]n|medicaci|medicament|pastilla|diabet|celiac|hernia|"
    r"cirug|operad|operaci|ansiedad|depresi|colon|artrosis|artritis|lumbalg|escolios|"
    r"asma|anemia|colesterol|hipertens|epileps|fibromialg|ovario|endometr|menopaus|"
    r"embaraz|lactosa|gluten|fructos|alerg|intoleran|rotura|ligamento|menisco|tendin|"
    r"rodilla|hombro|espalda|cervical|lumbar|s[ií]ndrome|enfermedad|tratamiento|"
    r"quimio|tumor|c[aá]ncer|renal|ri[nñ][oó]n|h[ií]gado|hep[aá]t|card[ií]a|infarto|"
    r"marcapasos|apendic|ves[ií]cula|amigdal|ligadura|vasectom|mastect|biopsia|"
    r"psoriasis|dermatitis|migra[nñ]a|gastritis|reflujo|hemorroid|varices|osteopor",
    re.I,
)

# Profile fields holding health data (GDPR art. 9), Spanish (source) and English (dataset)
HEALTH_FIELDS_ES = ("operaciones", "lesiones", "alergias", "intolerancias")
HEALTH_FIELDS_EN = ("surgeries", "injuries", "allergies", "intolerances")
PROFILE_FREE_TEXT_ES = HEALTH_FIELDS_ES + ("objetivos", "gustos_pos", "gustos_neg", "deporte")
PROFILE_FREE_TEXT_EN = HEALTH_FIELDS_EN + ("goals", "liked_foods", "disliked_foods", "sport")
PROFILE_FREE_TEXT = set(PROFILE_FREE_TEXT_ES) | set(PROFILE_FREE_TEXT_EN)

# --------------------------------------------------------------------------- #
# Generic record traversal                                                     #
# --------------------------------------------------------------------------- #

def iter_strings(obj, prefix: str = "") -> Iterator[tuple[str, str]]:
    """Yield (field_path, string) for every string inside a record.
    Lists collapse to `field[]`; meal dicts collapse to `meals.<key>` / `meals.<items>`."""
    if isinstance(obj, str):
        yield prefix or "$", obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            if k in ("comidas", "meals") and isinstance(v, dict):
                for mk, mv in v.items():
                    yield f"{p}.<key>", mk
                    for s in (mv if isinstance(mv, list) else [mv]):
                        if isinstance(s, str):
                            yield f"{p}.<items>", s
                continue
            yield from iter_strings(v, p)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_strings(v, f"{prefix}[]")
