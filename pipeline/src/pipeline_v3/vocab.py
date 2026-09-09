"""F2 -- enumerate the vocabularies, then decide (principle 3), and send anything doubtful to UNMAPPED (principle 4).

Nothing here is a hand-written list of twelve prefixes. Every header, label, unit and goal string that occurs in the
corpus is collected with its frequency; a mapping decision is attached to each entry; and the artefacts are written
so the data owner can audit the decisions without re-running anything:

  ``slot_headers.json``          every line-initial header in a diet document -> canonical slot or UNMAPPED
  ``questionnaire_labels.json``  every labelled field in a questionnaire -> dataset field or extra_fields
  ``units.json``                 every quantity unit -> canonical unit or kept verbatim
  ``goal_strings.json``          every OBJETIVO value -> goal taxonomy entry

The v2 splitter recognised 12 slot headers and let everything else fall into whichever slot was open, which is where
its 4.863 misassigned components came from. This module finds **1.069 distinct header shapes**, so the fix is not a
longer list: it is that an unrecognised header now opens ``UNMAPPED_<literal>`` instead of silently extending the
previous slot.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import convert, paths
else:
    from . import convert, paths


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


# --------------------------------------------------------------------------------------------- header splitting

# The first colon that is not part of a clock time. "COMIDA (14:00):" must split after the parenthesis, not inside
# it -- splitting on the naive first colon invents headers like "COMIDA (14", which is how the exploratory pass
# first reported this vocabulary.
_HEADER_SPLIT = re.compile(r"^(?P<head>(?:[^:\n]|\d:\d)*?)\s*:(?!\d)\s*(?P<rest>.*)$")
# The professional also writes a header with ".-" instead of a colon ("Observaciones .-", "SUPLEMENTO.-",
# "CENA.-"). Reading only the colon form leaves those blocks inside whatever section was open: 27 of the
# unmatched goal strings are a goal followed by the whole "Observaciones" block, swallowed for want of this.
# The head may itself carry a clock time in parentheses -- "ANTES DEL DESAYUNO A ESTOMAGO VACIO(7:50).- 1 …" --
# so a colon inside the head must not stop it. Without this the block is read as part of whatever section was
# open, and an OBJETIVO ends up holding a whole diet (and with it, in two cases, an excluded substance that then
# rode into retrieval_text through the goal header).
_HEADER_SPLIT_DASH = re.compile(r"^(?P<head>(?:[^:\n]|\d\s*:\s*\d){1,70}?)\s*\.-\s*(?P<rest>.*)$")
_TIME_QUALIFIER = re.compile(r"\s*[({\[]?\s*\d{1,2}\s*[:.]\s*\d{2}\s*(?:H|HS|HORAS)?\s*[)}\]]?\s*$", re.I)
# Prefijos que CUALIFICAN el tratamiento en vez de nombrar una franja: «Durante 15 días», «Las 2 primeras
# semanas», «Solo los lunes». Se reconocen por su forma, no por una lista cerrada de literales.
_QUALIFIER_PREFIX = re.compile(r"^(DURANTE|LOS|LAS|SOLO|SOLAMENTE|EN|CADA|A PARTIR|HASTA|DESDE)\b", re.I)
_TRAILING_NUM = re.compile(r"\s*[-.]*\s*$")


def split_header(line: str) -> tuple[str, str] | None:
    """Split ``HEADER: rest`` or ``HEADER.- rest``. Returns None when the line is not header-shaped."""
    stripped = line.strip()
    match = _HEADER_SPLIT.match(stripped)
    dash = _HEADER_SPLIT_DASH.match(stripped)
    # Whichever separator comes first wins, so "CENA.- 200 gr" is not mis-split by a colon later in the line.
    if dash and (not match or len(dash.group("head")) < len(match.group("head"))):
        match = dash
    if not match:
        return None
    head = match.group("head").strip(" \t.-|·*—–")
    if not head or len(head) > 60:
        return None
    if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", head):
        return None
    rest = match.group("rest").strip()

    # Encabezado ANIDADO: «Durante 15 días: Recién levantado (30 min antes del desayuno): 1 Hierro».
    #
    # Partir por el primer «:» deja `head = "Durante 15 días"`, que no mapea, y la franja entera —con su contenido—
    # cae al cajón genérico. El prefijo es un CUALIFICADOR temporal del tratamiento, no un encabezado: lo que nombra
    # la franja viene detrás. Cuando la cabeza no se reconoce y el resto se parte a su vez en algo que SÍ se
    # reconoce, manda el de dentro. Se comprueba con `classify_header`, así que no hay lista de prefijos que
    # mantener: si mañana escribe «Las dos primeras semanas: CENA: …», funciona igual.
    if _QUALIFIER_PREFIX.match(head) and classify_header(normalise_header(head))[0] == "unmapped":
        anidado = _HEADER_SPLIT.match(rest)
        if anidado:
            head_2 = anidado.group("head").strip(" \t.-|·*—–")
            if head_2 and len(head_2) <= 60 and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", head_2) \
                    and classify_header(normalise_header(head_2))[0] != "unmapped":
                return head_2, anidado.group("rest").strip()
    return head, rest


def normalise_header(header: str) -> str:
    """Fold case and accents and drop the time qualifier, so ``Comida (14:00)`` and ``COMIDA`` are one entry.

    Applied repeatedly, because the corpus writes time *ranges*: ``COMIDA (14:30 - 15:00)`` needs two passes and
    then loses the orphan opening bracket, which a single pass leaves behind as the separate header ``COMIDA (14:30``.
    """
    text = fold(header)
    for _ in range(4):
        before = text
        text = _TIME_QUALIFIER.sub("", text)
        text = re.sub(r"\s*\(\s*(?:LO MAS \w+ QUE PUEDAS|A ESTOMAGO VACIO|OPCIONAL)\s*\)?\s*$", "", text)
        text = re.sub(r"\s+", " ", text).strip(" .-|·—–")
        text = re.sub(r"\s*[({\[]\s*$", "", text)          # orphan bracket left by a stripped range
        if text == before:
            break
    return _TRAILING_NUM.sub("", text)


# ------------------------------------------------------------------------------------- canonical slot decisions

# Canonical slots. The first twelve are the v2 set (kept so the schema does not move); the rest are slots this
# enumeration found that v2 had no name for and therefore silently merged into the slot above them.
# The generic bucket for a header no rule maps with confidence. The domain has exactly one such member; the
# header's own words survive in raw_slot_label rather than becoming 528 enum values.
GENERIC_SLOT = "OTHER"

CANONICAL_SLOTS = [
    "DESAYUNO", "MEDIA MAÑANA", "ALMUERZO", "COMIDA", "MERIENDA", "MEDIA TARDE", "CENA", "RECENA",
    "ANTES DE ENTRENAR", "MITAD DE ENTRENAMIENTO", "DESPUES DE ENTRENAR", "BATIDO",
    # new in v3
    "RECIEN LEVANTADO", "ANTES DE DORMIR", "SUPLEMENTOS",
    # «AGUA» salió de aquí a propósito: es una sección de NOTAS, no una franja de comida. Como franja se
    # tragaba el bloque de observaciones que él escribe detrás (1.173 líneas en 301 dietas, de las que solo
    # 378 hablaban de agua), y de ahí venía la pérdida de notas del v3. El enum del dominio conserva el
    # miembro WATER porque hay dietas cargadas que lo usan; el vocabulario ya no lo produce.
]

# Rules are ordered: the first whose pattern matches the NORMALISED header wins. Each rule is
# (canonical slot, pattern). Written as patterns over observed variants, not as an enumeration of literals,
# and every rule below is backed by entries in slot_headers.json.
_SLOT_RULES: list[tuple[str, re.Pattern]] = [
    ("RECIEN LEVANTADO", re.compile(r"^(RECIEN LEVANTAD[OA]|AL LEVANTARSE|NADA MAS LEVANTARTE|EN AYUNAS|"
                                    r"ANTES DEL DESAYUNO.*|AYUNAS)$")),
    ("DESAYUNO", re.compile(r"^DESAYUNOS?\s*\d*$|^PRIMERA COMIDA$|^DESAYUNA$")),
    ("MEDIA MAÑANA", re.compile(r"^MEDIA ?MANANA\s*\d*$|^A MEDIA MANANA$|^ALMUERZO MANANA$")),
    ("ALMUERZO", re.compile(r"^ALMUERZOS?\s*\d*$")),
    ("MITAD DE ENTRENAMIENTO", re.compile(r"^(MITAD DE ENTRENAMIENTO|DURANTE EL ENTRENAMIENTO|"
                                          r"INTRA ?ENTRENO|DURANTE ENTRENO|EN EL ENTRENAMIENTO)$")),
    ("ANTES DE ENTRENAR", re.compile(r"^(ANTES DE ENTRENAR|ANTES DEL ENTRENAMIENTO|PRE ?ENTRENO|"
                                     r"PRE ?ENTRENAMIENTO|ANTES ENTRENAR|\d+ ?MIN.* ANTES DE ENTRENAR)$")),
    ("DESPUES DE ENTRENAR", re.compile(r"^(DESPUES DE ENTRENAR|DESPUES ENTRENAR|DESPUES DEL ENTRENAMIENTO|"
                                       r"POST ?ENTRENO|POST ?ENTRENAMIENTO|\d+ ?MIN\.? DESPUES DE ENTRENAR|"
                                       r"AL TERMINAR DE ENTRENAR|NADA MAS ENTRENAR)$")),
    ("COMIDA", re.compile(r"^COMIDAS?\s*\d*$|^ALMUERZO COMIDA$")),
    ("MERIENDA", re.compile(r"^MERIENDAS?\s*\d*$")),
    ("MEDIA TARDE", re.compile(r"^MEDIA ?TARDE\s*\d*$|^A MEDIA TARDE$")),
    ("CENA", re.compile(r"^CENAS?\s*\d*$|^ULTIMA COMIDA$")),
    ("RECENA", re.compile(r"^RE ?CENAS?\s*\d*$|^POST ?CENA$|^PRE-?CENA$")),
    ("ANTES DE DORMIR", re.compile(r"^(ANTES DE DORMIR|ANTES DE ACOSTARTE|ANTES DE IRTE A LA CAMA|"
                                   r"AL ACOSTARSE|ANTES DE ACOSTARSE|SI TARDAS EN IRTE A LA CAMA)$")),
    ("BATIDO", re.compile(r"^BATIDOS?( \d+)?$")),
    ("SUPLEMENTOS", re.compile(r"^SUPLEMENTOS?$|^SUPLEMENTACION$|^AMINOACIDOS$")),
]

# Headers that are document SECTIONS, not meal slots. They must be recognised so their content is routed to the
# right place instead of becoming food items -- v2 discarded 713 note blocks for want of exactly this.
_SECTION_RULES: list[tuple[str, re.Pattern]] = [
    ("goal", re.compile(r"^OBJETIVOS?$|^META$|^FINALIDAD$")),
    # La hidratación es una INSTRUCCIÓN, no una franja de comida, y tratarla como franja fue un error de modelo con
    # consecuencias medidas: al reconocer «AGUA» como franja, su cabecera abría una sección y se tragaba el bloque de
    # observaciones que el profesional escribe detrás. 301 dietas (24,9 %) tenían franja AGUA con 1.173 líneas dentro,
    # de las que solo 378 mencionaban agua; el resto eran notas suyas («HAY QUE BEBER AUNQUE NO SE TENGA SED», «Evitar
    # bebidas carbonatadas», «Tomar 1 Berberina antes de las 3 comidas principales»). De ahí salían la caída de la
    # mediana de notas de 4 a 2 y la de la nota de hidratación del 61,6 % al 33,2 %.
    ("notes", re.compile(r"^NOTAS?$|^OBSERVACIONES?$|^RECOMENDACIONES?$|^CONSEJOS?$|^IMPORTANTE$|"
                         r"^A TENER EN CUENTA$|^ACLARACIONES$|^INDICACIONES$|"
                         r"^AGUA$|^CONTROLAR LA INGESTA DE AGUA$|^HIDRATACION$|"
                         r"^IMPORTANTISIMO$|^RECOMENDACION$|^NOTAS IMPORTANTES$|^NOTAS? [A-Z]+$|"
                         r"^PARA EVITAR EL EFECTO CATABOLICO$")),
    ("contact", re.compile(r"^TEL(EFONO)?S?$|^CORREOS? ?(MAIL|ELECTRONICO)?S?$|^E?-?MAILS?$|^WEB$|"
                           r"^\[EMAIL\].*|^\[TEL\].*|^CONTACTO$")),
    ("conditional", re.compile(r"^SI (HACES|ENTRENAS|NO |TIENES|TE |VAS|SALES|TARDAS|QUIERES).*")),
    ("date", re.compile(r"^FECHA$|^DIA$")),
    # Day-type variants. The professional splits a diet into alternative days -- training vs rest ("CARGA" /
    # "DESCARGA"), or two interchangeable menus ("TIPO 1" / "TIPO 2", "OPCION 1" / "OPCION 2"). These are not meal
    # slots and not notes: they partition the meals that follow. v2 had no name for them, so their content was read
    # as more items of whatever slot was open, which quietly doubled some slots and mixed two menus into one.
    ("variant", re.compile(r"^(TIPO|OPCION|ALTERNATIVA|VARIANTE|MENU|DIA)\s*\d*$|"
                           r"^(CARGA|DESCARGA|RECARGA)$|^FASE (FINAL|INICIAL|\d+)$|^OPCIONAL$|"
                           r"^DIAS? DE (ENTRENAMIENTO|DESCANSO|CARDIO|PESAS)$|^ENTRENAMIENTO$|^DESCANSO$")),
]


# Second stage, applied only when no exact rule matched. A header that *begins* with a slot phrase and continues
# with a qualifier ("DESPUES DE ENTRENAR(30 MIN. DESPUES DEL CARDIO)", "ANTES DE ENTRENAR PESAS") names that slot
# and adds a condition; mapping it is not a guess. A time offset in front of the phrase counts the same way
# ("30 MIN. DESPUES ENTRENAR"). Anything whose slot phrase is not at the edge stays UNMAPPED.
_SLOT_PREFIX_RULES: list[tuple[str, re.Pattern]] = [
    ("DESPUES DE ENTRENAR", re.compile(r"^(?:\d+\s*(?:MIN|MINUTOS|H|HORAS?)\.?\s*)?DESPUES\s*(?:DE|DEL)?\s*"
                                       r"(?:ENTRENAR|ENTRENO|ENTRENAMIENTO)\b")),
    ("ANTES DE ENTRENAR", re.compile(r"^(?:\d+\s*(?:MIN|MINUTOS|H|HORAS?)\.?\s*)?ANTES\s*(?:DE|DEL)?\s*"
                                     r"(?:ENTRENAR|ENTRENO|ENTRENAMIENTO|CARDIO|PESAS)\b")),
    ("MITAD DE ENTRENAMIENTO", re.compile(r"^MITAD\s*(?:DE)?\s*(?:ENTRENAMIENTO|ENTRENO)\b")),
    ("RECIEN LEVANTADO", re.compile(r"^(?:RECIEN LEVANTAD[OA]|AL LEVANTAR(?:SE|TE)|EN AYUNAS)\b")),
    ("ANTES DE DORMIR", re.compile(r"^(?:SI TARDAS EN IRTE A LA CAMA|ANTES DE (?:IRTE A LA CAMA|DORMIR|ACOSTAR))")),
    ("DESAYUNO", re.compile(r"^DESAYUNO\b")),
    ("MEDIA MAÑANA", re.compile(r"^MEDIA ?MANANA\b")),
    ("MEDIA TARDE", re.compile(r"^MEDIA ?TARDE\b")),
    ("MERIENDA", re.compile(r"^MERIENDA\b")),
    ("COMIDA", re.compile(r"^COMIDA\b")),
    ("CENA", re.compile(r"^CENA\b")),
    ("RECENA", re.compile(r"^RE ?CENA\b")),
    ("SUPLEMENTOS", re.compile(r"^SUPLEMENTOS?\b")),
]

# Questionnaire labels that also turn up inside diet documents. They are profile data, not a meal slot, and must
# not become food items.
_PROFILE_IN_DIET = re.compile(
    r"^(ALERGIAS?|INTOLERANCIAS?|OPERACIONES|LESIONES.*|PESO( INICIAL| ACTUAL)?|ALTURA|EDAD|SEXO|"
    r"CINTURA|MUNECA|CUELLO|CADERA|IMC|GUSTOS (POSITIVOS|NEGATIVOS)|VICIOS ALIMENTICIOS|"
    r"NOMBRE|APELLIDOS|FECHA NACIMIENTO|TELEFONO|USUARIO|CONTRASENA)$"
)


# Formas en las que la franja NO está al principio del encabezado. Son franjas suyas de pleno derecho —«UNA HORA
# DESPUES DE ENTRENAR», «JUSTO DESPUES DE ENTRENAR (NO PERDER NI UN MINUTO)», «DE MEDIA HORA A UNA HORA DESPUES DE
# ENTRENAR TOMAR»— y caían al cajón genérico por no empezar por la palabra clave: 84 apariciones de post-entreno en
# 21 formas distintas. Con ellas fuera, las dietas de un cliente perdían la franja entera y la rotación heredaba la
# carencia, que es como una dieta de volumen acabó sin el batido de después de entrenar.
_SLOT_CONTAINS_RULES: list[tuple[str, re.Pattern]] = [
    ("DESPUES DE ENTRENAR", re.compile(r"DESPUES\s*(?:DE|DEL)?\s*(?:ENTRENAR|ENTRENOS?|ENTRENAMIENTO|CARDIO)\b")),
    ("ANTES DE ENTRENAR", re.compile(r"ANTES\s*(?:DE|DEL)?\s*(?:ENTRENAR|ENTRENOS?|ENTRENAMIENTO)\b")),
    ("ANTES DE DORMIR", re.compile(r"(?:IRTE?|IR)\s+A\s+LA\s+CAMA|ANTES\s+DE\s+DORMIR|AL\s+ACOSTARSE")),
]


def classify_header(normalised: str) -> tuple[str, str, str]:
    """Return ``(kind, target, reason)``.

    ``kind`` is ``slot`` | ``section`` | ``unmapped``. An ``unmapped`` header is NOT dropped and NOT merged into the
    slot above it: the extractor opens ``UNMAPPED_<literal>`` for it, so its content stays attributed to the text
    that introduced it and gets counted.
    """
    for slot, pattern in _SLOT_RULES:
        if pattern.match(normalised):
            return "slot", slot, f"matches the {slot} rule"
    for section, pattern in _SECTION_RULES:
        if section == "conditional":
            continue                       # se decide más abajo: una condicional que nombra una franja ES esa franja
        if pattern.match(normalised):
            return "section", section, f"matches the {section} section rule"
    if _PROFILE_IN_DIET.match(normalised):
        return "section", "profile_field", "a questionnaire label appearing inside a diet document"
    for slot, pattern in _SLOT_PREFIX_RULES:
        if pattern.match(normalised):
            return "slot", slot, f"begins with the {slot} phrase and continues with a qualifier"
    # «SI TARDAS EN IRTE A LA CAMA (+30 MIN)» y «SI HACES CARDIO» son condicionales, sí, pero lo que introducen es
    # una franja de comida suya. Probar la condicional primero las mandaba al cajón: 71 y 55 apariciones.
    for slot, pattern in _SLOT_CONTAINS_RULES:
        if pattern.search(normalised):
            return "slot", slot, f"names the {slot} phrase inside a longer header"
    for section, pattern in _SECTION_RULES:
        if section == "conditional" and pattern.match(normalised):
            return "section", section, "matches the conditional section rule"
    return "unmapped", GENERIC_SLOT, "no rule matched with confidence; the literal is kept in raw_slot_label"


# ------------------------------------------------------------------------------------------------------- units

_QUANTITY = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>gr?s?\b|gramos?\b|kg\b|kilos?\b|ml\b|cl\b|l\b|litros?\b|"
    r"cucharad(?:a|ita)s?\b|cazos?\b|lonchas?\b|latas?\b|dientes?\b|capsulas?\b|comprimidos?\b|"
    r"unidades?\b|uds?\b|piezas?\b|rodajas?\b|punados?\b|chorritos?\b|vasos?\b|tazas?\b|"
    r"paquetes?\b|sobres?\b|barritas?\b|onzas?\b|ramas?\b|hojas?\b|porciones?\b|dosis\b|"
    r"scoops?\b|medidas?\b|tarrinas?\b|botes?\b|filetes?\b|rebanadas?\b|bolsas?\b)?",
    re.I,
)

UNIT_CANONICAL = {
    "g": ("g", ("g", "gr", "grs", "gramo", "gramos")),
    "kg": ("kg", ("kg", "kilo", "kilos")),
    "ml": ("ml", ("ml",)),
    "cl": ("cl", ("cl",)),
    "l": ("l", ("l", "litro", "litros")),
    "cucharada": ("cucharada", ("cucharada", "cucharadas")),
    "cucharadita": ("cucharadita", ("cucharadita", "cucharaditas")),
    "cazo": ("cazo", ("cazo", "cazos")),
    "loncha": ("loncha", ("loncha", "lonchas")),
    "lata": ("lata", ("lata", "latas")),
    "diente": ("diente", ("diente", "dientes")),
    "cápsula": ("cápsula", ("capsula", "capsulas", "comprimido", "comprimidos")),
    "unidad": ("unidad", ("unidad", "unidades", "ud", "uds", "pieza", "piezas")),
    "rodaja": ("rodaja", ("rodaja", "rodajas")),
    "puñado": ("puñado", ("punado", "punados")),
    "chorrito": ("chorrito", ("chorrito", "chorritos")),
    "vaso": ("vaso", ("vaso", "vasos")),
    "taza": ("taza", ("taza", "tazas")),
    "paquete": ("paquete", ("paquete", "paquetes")),
    "sobre": ("sobre", ("sobre", "sobres")),
    "barrita": ("barrita", ("barrita", "barritas")),
    "onza": ("onza", ("onza", "onzas")),
    "rama": ("rama", ("rama", "ramas")),
    "hoja": ("hoja", ("hoja", "hojas")),
    "porcion": ("porcion", ("porcion", "porciones")),
    "dosis": ("dosis", ("dosis",)),
    "scoop": ("scoop", ("scoop", "scoops", "medida", "medidas")),
    "tarrina": ("tarrina", ("tarrina", "tarrinas")),
    "bote": ("bote", ("bote", "botes")),
    "filete": ("filete", ("filete", "filetes")),
    "rebanada": ("rebanada", ("rebanada", "rebanadas")),
    "bolsa": ("bolsa", ("bolsa", "bolsas")),
}
_UNIT_LOOKUP = {variant: canonical for canonical, (_out, variants) in UNIT_CANONICAL.items() for variant in variants}


def canonical_unit(raw: str | None) -> tuple[str | None, bool]:
    """Return ``(canonical unit, was_known)``. An unknown unit is KEPT VERBATIM, never dropped (principle 4)."""
    if not raw:
        return None, True
    key = fold(raw).lower().strip(". ")
    if key in _UNIT_LOOKUP:
        return _UNIT_LOOKUP[key], True
    return raw.strip(), False


# ------------------------------------------------------------------------------------------------- enumeration

def enumerate_all(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    manifest = out_dir / "manifest.jsonl"
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]

    headers: collections.Counter = collections.Counter()
    header_examples: dict[str, str] = {}
    labels: collections.Counter = collections.Counter()
    goals: collections.Counter = collections.Counter()
    units: collections.Counter = collections.Counter()

    for row in rows:
        if row.get("status") != "ok":
            continue
        text = convert.cached_text(row["sha1"])
        label = row.get("label")
        for line in text.split("\n"):
            parsed = split_header(line)
            if parsed is None:
                continue
            head, rest = parsed
            normalised = normalise_header(head)
            if not normalised:
                continue
            if label == "diet":
                headers[normalised] += 1
                header_examples.setdefault(normalised, head)
                kind, target, _ = classify_header(normalised)
                if kind == "section" and target == "goal" and rest:
                    goals[rest.strip()[:120]] += 1
                if kind == "slot" or kind == "unmapped":
                    for match in _QUANTITY.finditer(rest):
                        unit = match.group("unit")
                        units[fold(unit).lower() if unit else "<none>"] += 1
            elif label == "questionnaire":
                labels[normalised] += 1

    def header_entry(name: str, count: int) -> dict:
        kind, target, reason = classify_header(name)
        entry = {"header": name, "example_as_written": header_examples.get(name, name),
                 "count": count, "kind": kind, "maps_to": target, "reason": reason}
        if kind == "unmapped":
            entry["review"] = True
        return entry

    header_entries = [header_entry(h, n) for h, n in headers.most_common()]
    unmapped = [e for e in header_entries if e["kind"] == "unmapped"]

    unit_entries = []
    for raw, count in units.most_common():
        if raw == "<none>":
            unit_entries.append({"unit": None, "count": count, "maps_to": "unidad",
                                 "reason": "a bare number: the corpus writes countable items without a unit"})
            continue
        canonical, known = canonical_unit(raw)
        unit_entries.append({"unit": raw, "count": count, "maps_to": canonical,
                             "known": known,
                             "reason": "canonical" if known else "unknown unit, kept verbatim (principle 4)"})

    artefacts = {
        "slot_headers.json": {
            "distinct": len(header_entries),
            "occurrences": sum(headers.values()),
            "canonical_slots": CANONICAL_SLOTS,
            "mapped_to_slot": sum(e["count"] for e in header_entries if e["kind"] == "slot"),
            "mapped_to_section": sum(e["count"] for e in header_entries if e["kind"] == "section"),
            "unmapped_occurrences": sum(e["count"] for e in unmapped),
            "unmapped_distinct": len(unmapped),
            "entries": header_entries,
        },
        "questionnaire_labels.json": {
            "distinct": len(labels),
            "occurrences": sum(labels.values()),
            "entries": [{"label": name, "count": count} for name, count in labels.most_common()],
        },
        "units.json": {
            "distinct": len(unit_entries),
            "occurrences": sum(units.values()),
            "unknown_distinct": sum(1 for e in unit_entries if e.get("known") is False),
            "entries": unit_entries,
        },
        "goal_strings.json": {
            "distinct": len(goals),
            "occurrences": sum(goals.values()),
            "entries": [{"goal_text": text, "count": count} for text, count in goals.most_common()],
        },
    }
    for name, payload in artefacts.items():
        (out_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                    encoding="utf-8", newline="\n")

    return {name: {k: v for k, v in payload.items() if k != "entries"} for name, payload in artefacts.items()}


def main() -> None:
    argparse.ArgumentParser(description="F2: enumerate the corpus vocabularies").parse_args()
    print(json.dumps(enumerate_all(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
