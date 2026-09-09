"""DocumentTemplatePolicy (S6, closed against two ORIGINAL documents of 2026): the professional's diet document, as he writes it,
from a proposal.

Measured first over the 991 reconstructed documents (la memoria (plantilla del documento del profesional)) and then contrasted, line by line, with two of his
current documents (custody, not versioned): first line «DIETA <cliente>  DD / MM / AA»; «Objetivo: …» with the CLIENT'S OWN goal words when the
record has them; the «Recién levantado (…): …» line before breakfast when the diet has one; slot labels in upper case followed by a colon (with
the fasting / keto parenthetical hints); item lines «cantidad gr Alimento / alternativa» (his unit token is «gr»); the three training lines with
upper-case labels («ANTES DE ENTRENAR: Nada», «MITAD DE ENTRENAMIENTO: Agua en cantidad …», «DESPUES DE ENTRENAR: …»); a «Notas:» block whose
notes are plain sentences (no bullets in the 2026 documents; «-» in the older corpus); and the contact line «correo / Tel: teléfono» as the last
paragraph of the text, not a page footer. This policy produces that TEXT document as typed lines; the PDF exporter only lays it out. Pure function.
"""
from __future__ import annotations

from dataclasses import replace, dataclass
from datetime import date

from finalprosports.domain.model import DietProposal, Goal, MealSlot, ProposedItem, Unit

GOAL_TEXT = {Goal.VOLUME: "Ganar masa muscular", Goal.FAT_LOSS: "Definición y pérdida de grasa manteniendo la masa muscular",
             Goal.INTERMITTENT_FASTING: "Ayuno intermitente con bajo nivel de hidratos para provocar autofagia y mejorar la oxidación de grasas como fuente de energía principal",
             Goal.CARB_CYCLING: "Descarga y carga de hidratos", Goal.KETO: "Cetosis para provocar autofagia, bajar inflamación y perder grasa",
             Goal.HYPOCALORIC: "Dieta hipocalórica", Goal.HIGH_FIBRE: "Dieta alta en fibra", Goal.MAINTENANCE: "Mantenimiento", Goal.UNCLASSIFIED: "Plan nutricional personalizado"}
# `sin_clasificar` llevaba la CADENA VACIA, y `render_document` solo emite la linea cuando hay texto: 52 de sus 815
# dietas (6,4 %) salian sin la linea «Objetivo:», que el escribe SIEMPRE (`19_objetivo_vacio`). No es un defecto del
# motor sino de la plantilla, y la correccion es esta entrada. El texto es deliberadamente neutro: `sin_clasificar`
# agrupa propositos heterogeneos que el si nombra en el documento (depurativa, detox, pre-competicion, «restablecer
# parametros»), y elegir uno de ellos como etiqueta comun seria imprimir un objetivo FALSO en las otras. Cuando esas
# palabras suyas existen -- `goal_text` del expediente, o de la dieta -- siguen teniendo prioridad sobre esta entrada.
# Each slot prints under its own name now. Until dataset-v3 the model had no MEDIA TARDE and no RECIEN LEVANTADO,
# so this table carried the workaround: MERIENDA was printed as "MEDIA TARDE" and the generic OTHER as
# "Recién levantado (…)". With both slots in the enum the relabelling would print the wrong header on a real
# MERIENDA, so it is removed. His document gains the headers he actually writes; nothing else about it changes.
SLOT_LABEL = {MealSlot.ON_WAKING: "Recién levantado (30 min antes del desayuno)",
              MealSlot.BREAKFAST: "DESAYUNO", MealSlot.MID_MORNING: "MEDIA MAÑANA", MealSlot.BRUNCH: "ALMUERZO",
              MealSlot.LUNCH: "COMIDA", MealSlot.SNACK: "MERIENDA", MealSlot.MID_AFTERNOON: "MEDIA TARDE",
              MealSlot.DINNER: "CENA", MealSlot.LATE_SNACK: "RECENA", MealSlot.BEFORE_BED: "ANTES DE DORMIR",
              MealSlot.PRE_WORKOUT: "ANTES DE ENTRENAR",
              MealSlot.INTRA_WORKOUT: "MITAD DE ENTRENAMIENTO", MealSlot.POST_WORKOUT: "DESPUES DE ENTRENAR",
              MealSlot.SHAKE: "BATIDO", MealSlot.SUPPLEMENTS: "SUPLEMENTOS", MealSlot.WATER: "AGUA",
              MealSlot.OTHER: "OTROS"}
TIMING_HINTS = {MealSlot.LUNCH: "lo más tarde que puedas", MealSlot.DINNER: "Lo más temprano que puedas"}     # his hints for fasting / keto
TIMING_GOALS = {Goal.INTERMITTENT_FASTING, Goal.KETO}
TRAINING = (MealSlot.PRE_WORKOUT, MealSlot.INTRA_WORKOUT, MealSlot.POST_WORKOUT)
MID_TRAINING = "MITAD DE ENTRENAMIENTO: Agua en cantidad (sin sobrepasar la cantidad total que se indica en dieta)"
TRAINING_EMPTY = {MealSlot.PRE_WORKOUT: "Nada", MealSlot.INTRA_WORKOUT: None, MealSlot.POST_WORKOUT: "Nada"}   # intra-workout falls back to his fixed water line
OMIT_WHEN_EMPTY = {MealSlot.POST_WORKOUT}
"""Ojo con lo que este conjunto significa y con lo que NO significa.

Dice qué hacer cuando la franja llega VACÍA, y la medida que lo respalda (58,4 % de omisión) se tomó sobre las
dietas de volumen en las que el post-entreno acabó vacío. Lo que NO dice es que la franja deba llegar vacía:
medido sobre las 482 dietas de volumen del corpus, **385 (79,9 %) tienen post-entreno CON CONTENIDO**, y ahí él
escribe una instrucción larga («1 Batido de 60 gr proteínas con 30 gr Amilopeptinas + 1 ZMA + 1 Sales minerales»).
Omitir una franja que debería llevar contenido no es lo mismo que omitir una vacía: lo primero es perder una
cuarta parte del documento. `check_post_workout_present` vigila esa tasa."""
"""Slots he leaves out of the document altogether when they have nothing in them, rather than printing «Nada».

Measured over his volume diets: when the post-workout slot ends up empty he OMITS the label 58,4 % of the time and prints it
41,6 %. Printing «Nada» is his minority behaviour, and it is the line the professional called an erratum. The pre-workout slot
goes the other way — he prints it 60,9 % of the time when empty — so it stays."""

INLINE_SLOTS = {MealSlot.ON_WAKING, MealSlot.WATER, MealSlot.OTHER}   # written as one line «Etiqueta: ítems», like the training lines
UNIT_TEXT = {Unit.GRAM: "gr", Unit.MILLILITER: "ml", Unit.PIECE: "", Unit.TABLESPOON: "cucharada de", Unit.TEASPOON: "cucharadita de", Unit.CAN: "lata de",
             Unit.SLICE: "loncha de", Unit.HANDFUL: "puñado de", Unit.CLOVE: "diente de", Unit.DASH: "chorrito de", Unit.SCOOP: "cazo de", Unit.CAPSULE: "cápsula de", Unit.NONE: ""}
PLURAL = {"cucharada de": "cucharadas de", "cucharadita de": "cucharaditas de", "lata de": "latas de", "loncha de": "lonchas de", "puñado de": "puñados de",
          "diente de": "dientes de", "cazo de": "cazos de", "cápsula de": "cápsulas de"}


@dataclass(frozen=True)
class DocLine:
    kind: str          # header | objetivo | inline | slot | item | training | notes_title | note | footer | blank
    text: str


@dataclass(frozen=True)
class DietDocument:
    lines: tuple[DocLine, ...]

    def of(self, kind: str) -> tuple[str, ...]:
        return tuple(l.text for l in self.lines if l.kind == kind)

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)


def _num(v: float) -> str:
    # El medio lo escribe como FRACCION: «1/2 Aguacate», no «0,5 Aguacate». Medido sobre sus dietas: de las 255 veces
    # que prescribe medio de algo, 165 (64,7 %) lo escribe «1/2». Es el unico valor fraccionario con mayoria clara y
    # con n suficiente -- 1,5 va 28 a 23 y 2,5 al reves -- asi que los demas se quedan con coma decimal.
    if float(v) == 0.5:
        return "1/2"
    return f"{int(v)}" if float(v).is_integer() else f"{v:g}".replace(".", ",")


# Plural nouns that name a food which, counted, must read in the singular: «1 pasas» is wrong, «1 pasa» is right. Only the
# ones the catalogue actually holds in the plural; a general de-pluraliser would mangle «espárragos» or «frutos rojos», which
# he never counts one of anyway (§6a of the expert review: this is the exporter's business, not the engine's).
SINGULAR = {"pasas": "pasa", "almendras": "almendra", "nueces": "nuez", "aceitunas": "aceituna", "galletas": "galleta",
            "tortitas de arroz": "tortita de arroz", "lonchas": "loncha", "rebanadas": "rebanada", "hamburguesas": "hamburguesa",
            "sardinas": "sardina", "gambas": "gamba", "pipas de calabaza": "pipa de calabaza", "arándanos": "arándano",
            "fresas": "fresa", "cerezas": "cereza", "dátiles": "dátil", "tostadas": "tostada", "claras de huevo": "clara de huevo"}


def _agree(name: str, value: float | None, unit: Unit) -> str:
    """Number agreement: a count of one takes the singular. Only applies when the count IS the unit («1 pasa»), never when
    the quantity is a weight or a measure («1 cucharada de nueces» keeps the plural)."""
    if value is None or unit is not Unit.PIECE or abs(value - 1) > 1e-9:
        return name
    return SINGULAR.get(name.strip().lower(), name)


def item_text(o: ProposedItem) -> str:
    name = (o.item.display_name or o.item.canonical_name or o.item.normalized_key or o.item.raw_text or "").strip()
    name = _agree(name, o.item.quantity.value, o.item.quantity.unit)
    # his own capitalisation: first letter up, and a stand-alone single letter is an initial («vitamina d» -> «Vitamina D»)
    name = " ".join(w.upper() if len(w) == 1 and w.isalpha() else w for w in name.split())
    name = name[:1].upper() + name[1:]
    q = o.item.quantity
    if q.value is None:
        return name
    unit = UNIT_TEXT.get(q.unit, q.unit.value)
    if unit and q.value != 1 and unit in PLURAL:
        unit = PLURAL[unit]
    return " ".join(x for x in (_num(q.value), unit, name) if x)


def _groups_text(m) -> str:
    return "  ·  ".join(_line_text(g) for g in _lines_of(m))


def _lines_of(m) -> list:
    """Los grupos de la franja, con los COMPUESTOS reunidos en una sola linea.

    El «/» de este documento significa alternativa: es como el escribe «280 gr Pollo / 240 gr Lomo». Un compuesto es
    lo contrario -- «1 vitamina con minerales», «1 Batido de 60gr proteinas con 30 gr Amilopeptinas + 1 ZMA» son cosas
    que se toman JUNTAS -- y el las escribe en una linea unidas por «con» o «+», nunca en lineas sueltas. Separarlos en
    grupos distintos evita el error grave (imprimir un compuesto como si fuera una eleccion) pero deja huerfano el
    miembro que no lleva cantidad: asi aparecio un «minerales» solo, debajo del multivitaminico del que depende.

    Se reunen aqui, al imprimir, y no antes: la composicion necesita los miembros por separado para poder rotar o
    sustituir cada uno; el documento los necesita juntos para parecerse a los suyos.
    """
    salida, por_compuesto = [], {}
    for g in m.groups:
        clave = next((o.item.compound_group for o in g.options if getattr(o.item, "compound_group", None)), None)
        if clave is not None and clave in por_compuesto:
            anterior = por_compuesto[clave]
            salida[anterior] = replace(salida[anterior], options=salida[anterior].options + g.options)
            continue
        if clave is not None:
            por_compuesto[clave] = len(salida)
        salida.append(g)
    return salida


def _line_text(g) -> str:
    """Alternativas con «/» (elegir una); compuesto con «+» (tomar todo), que es su propia notacion."""
    compuestos = {o.item.compound_group for o in g.options if getattr(o.item, "compound_group", None)}
    separador = " + " if len(compuestos) == 1 and len(g.options) > 1 else " / "
    return separador.join(item_text(o) for o in g.options)


def render_document(proposal: DietProposal, client_name: str | None, today: date, contact_lines: tuple[str, ...] = (), goal_text: str | None = None) -> DietDocument:
    p = proposal.profile
    goal = p.goal or Goal.UNCLASSIFIED
    who = f" {client_name.strip()}" if client_name and client_name.strip() else ""      # S9: the header carries the client's NAME; never the internal key
    lines: list[DocLine] = [DocLine("header", f"DIETA{who}  {today.day:02d} / {today.month:02d} / {today.year % 100:02d}")]
    obj = (goal_text or "").strip() or GOAL_TEXT.get(goal, "")
    if obj:
        obj = obj[:1].upper() + obj[1:]
        lines.append(DocLine("objetivo", f"Objetivo: {obj}"))
    by_slot = {m.slot: m for m in proposal.meals}
    first_slot = True
    for m in proposal.meals:
        if m.slot in TRAINING:
            continue
        if m.slot in INLINE_SLOTS:
            if m.groups:
                lines.append(DocLine("inline", f"{SLOT_LABEL[m.slot]}: {_groups_text(m)}"))
            continue
        # He separates his blocks with an EMPTY PARAGRAPH, not with paragraph spacing: none of the paragraph styles in his
        # documents carries a margin, they all inherit the default style. The first block («Recién levantado» / «DESAYUNO:»)
        # runs on from the objective without a blank; every later slot gets one.
        if not first_slot:
            lines.append(DocLine("blank", ""))
        first_slot = False
        hint = f" ({TIMING_HINTS[m.slot]})" if goal in TIMING_GOALS and m.slot in TIMING_HINTS else ""
        lines.append(DocLine("slot", f"{SLOT_LABEL.get(m.slot, m.slot.value)}{hint}:"))
        for g in _lines_of(m):
            lines.append(DocLine("item", _line_text(g)))
    lines.append(DocLine("blank", ""))                       # his blank paragraph before the three training lines
    for slot in TRAINING:
        m = by_slot.get(slot)
        if m and m.groups:
            lines.append(DocLine("training", f"{SLOT_LABEL[slot]}: {_groups_text(m)}"))
        elif slot in OMIT_WHEN_EMPTY:
            continue                                     # he leaves the label out rather than writing «Nada»
        elif TRAINING_EMPTY[slot] is not None:
            lines.append(DocLine("training", f"{SLOT_LABEL[slot]}: {TRAINING_EMPTY[slot]}"))
        else:
            lines.append(DocLine("training", MID_TRAINING))
    if proposal.notes:
        lines.append(DocLine("blank", ""))                   # ... and before «Notas:»
        lines.append(DocLine("notes_title", "Notas:"))
        for n in proposal.notes:
            n = n.strip()
            if n:
                lines.append(DocLine("note", n))
    contact = " / ".join(c.strip() for c in contact_lines if c.strip())
    if contact:
        lines.append(DocLine("footer", contact))
    return DietDocument(tuple(lines))
