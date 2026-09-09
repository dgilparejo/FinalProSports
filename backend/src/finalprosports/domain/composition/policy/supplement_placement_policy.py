"""Los suplementos van DONDE HAY QUE TOMARLOS, no en una lista al final.

El sistema componía un bloque «SUPLEMENTOS» con todo lo que los casos tenían ahí, y el cliente leía al final del
documento una lista de cuatro líneas sin saber cuándo tomarse cada cosa. El profesional, cuando los distribuye, los
escribe **dentro de la comida**: la creatina en el desayuno, el potasio en la comida, el ZMA y la vitamina D en la
cena.

**Lo que dice el corpus, entero, porque matiza la decisión y no la contradice.** El bloque no es un invento del
sistema: él lo usa en **589 de sus 1.203 dietas (49,0 %)**, y el 34,1 % de sus ítems de suplemento viven ahí.
Distribuirlos siempre no es «hacer lo que él hace»: es hacer **lo que hace la otra mitad de las veces**, y se hace
porque un documento que dice cuándo tomar cada cosa es mejor para el cliente. Es una decisión de producto tomada con
el dato delante, no un hallazgo.

**Cómo se decide dónde va cada uno**, en este orden y con esta preferencia:

1. **Lo que hacen los CASOS RECUPERADOS de ese cliente, cuando hay CONSENSO.** Es el principio del sistema — decide
   la mayoría, no una regla global — y resuelve el **74,8 %** de los suplementos que aparecen en el bloque. Con un
   suelo: la franja ganadora necesita al menos dos casos y un margen de al menos dos votos sobre la segunda. Un 2-1
   sobre veinte casos no es un consenso, y lo puso un caso real: el potasio salía a «Recién levantado» por dos votos
   contra uno cuando el corpus lo pone en la cena con 377 observaciones y él lo escribía en la comida en esa misma
   dieta.
2. **La tabla minada del corpus entero** (`supplement_slots.json`), para el 25,2 % restante. Es respaldo: 47
   suplementos con al menos diez observaciones fuera del bloque, y **solo 16 tienen una franja modal por encima del
   50 %**. La concentración viaja con el dato para que quien lo lea sepa cuánto vale.
3. **Nada.** Un suplemento que ni los casos ni el corpus saben colocar **se queda en el bloque**. No se inventa una
   franja: quedarse en la lista final es peor que la alternativa, pero mucho mejor que ponerlo en una comida en la que
   él nunca lo escribió.

Lo que esta política **no** hace: no añade suplementos, no los quita y no cambia sus cantidades. Solo los mueve de
franja, y solo desde el bloque genérico. Un suplemento que el consenso ya había colocado en una comida no se toca.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace

from finalprosports.domain.composition.policy.composition_policy import MIN_CASE_SUPPORT
from finalprosports.domain.model import FoodGroup, MealSlot, ProposedMeal

# Las dos franjas que no son un momento de ingesta: el bloque genérico y el cajón del extractor. Son de donde se sale.
GENERIC_SLOTS = frozenset({MealSlot.SUPPLEMENTS, MealSlot.OTHER})


def _slot_by_food_from_cases(cases, catalog) -> dict[int, MealSlot]:
    """Para cada suplemento, la franja REAL en que más lo ponen los casos recuperados, **si hay consenso**.

    El suelo no es decorativo y lo puso un caso concreto. El potasio de un cliente real salía a «Recién levantado»
    con **dos votos contra uno** entre veinte casos, cuando el corpus entero lo pone en la cena con 377 observaciones
    y el propio profesional lo escribía en la comida en esa misma dieta. Una diferencia de un voto sobre veinte no es
    un consenso: es ruido con forma de mayoría, y es exactamente el error que `MIN_CASE_SUPPORT` existe para evitar
    en el resto del compositor.

    Dos condiciones, las dos necesarias:
      * la franja ganadora necesita al menos `MIN_CASE_SUPPORT` casos;
      * y tiene que ganar a la segunda por un margen de **al menos dos votos** — un 2-1 y un 3-2 devuelven la
        decisión al respaldo del corpus, que tiene cientos de observaciones detrás. El corte es el MARGEN, no el
        número absoluto: lo que invalida un 3-2 es lo mismo que invalida un 2-1.
    """
    votes: dict[int, Counter] = defaultdict(Counter)
    for case in cases:
        for meal in case.diet.meals:
            if meal.slot in GENERIC_SLOTS:
                continue
            for item in meal.items:
                food = catalog.get(item.food_id) if item.food_id is not None else None
                if food is not None and food.group is FoodGroup.SUPPLEMENT:
                    votes[item.food_id][meal.slot] += 1
    out: dict[int, MealSlot] = {}
    for fid, counter in votes.items():
        # El desempate por NOMBRE de franja, y no por orden de inserción, hace la salida reproducible: el orden de
        # inserción depende de en qué caso apareció primero, y por tanto del orden de los candidatos.
        orden = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].value))
        mejor, n = orden[0]
        segundo = orden[1][1] if len(orden) > 1 else 0
        if n >= MIN_CASE_SUPPORT and n - segundo > 1:
            out[fid] = mejor
    return out


def place(meals: list[ProposedMeal], cases, catalog, corpus_slots: dict[int, str] | None = None) -> list[ProposedMeal]:
    """Saca del bloque genérico los suplementos que se sepa colocar y los mete en su franja.

    Devuelve la lista de franjas nueva. El bloque desaparece si se queda vacío; si algo no se sabe colocar, sigue ahí.
    """
    bloque = next((m for m in meals if m.slot is MealSlot.SUPPLEMENTS), None)
    if bloque is None or not bloque.groups:
        return meals

    de_casos = _slot_by_food_from_cases(cases, catalog)
    respaldo = {}
    for fid, nombre in (corpus_slots or {}).items():
        try:
            respaldo[fid] = MealSlot(nombre)
        except ValueError:                       # una franja del artefacto que el modelo ya no tiene: se ignora
            continue

    destino: dict[int, list] = defaultdict(list)
    se_quedan = []
    for grupo in bloque.groups:
        lider = grupo.options[0].item.food_id if grupo.options else None
        # El grupo entero se mueve con su líder: partirlo separaría alternativas que él escribió juntas.
        slot = de_casos.get(lider) or respaldo.get(lider)
        if slot is None or slot in GENERIC_SLOTS:
            se_quedan.append(grupo)
        else:
            destino[slot].append(grupo)
    if not destino:
        return meals

    salida: list[ProposedMeal] = []
    colocados: set[MealSlot] = set()
    for m in meals:
        if m.slot is MealSlot.SUPPLEMENTS:
            if se_quedan:
                salida.append(replace(m, groups=tuple(se_quedan)))
            continue
        extra = destino.get(m.slot)
        if extra:
            colocados.add(m.slot)
            # Los suplementos van AL FINAL de la franja, que es donde él los escribe: primero la comida, después lo
            # que se toma con ella. Las posiciones se renumeran para que el documento no herede huecos.
            grupos = tuple(replace(g, position=i) for i, g in enumerate(tuple(m.groups) + tuple(extra)))
            salida.append(replace(m, groups=grupos))
        else:
            salida.append(m)

    # Un suplemento cuyo destino no existe en la propuesta (por ejemplo la cena, que el consenso no compuso) no puede
    # inventar la franja: la comida no está, y crearla solo para colgar de ella una cápsula sería fabricar estructura
    # que el consenso no respalda. Vuelve al bloque.
    huerfanos = [g for slot, gs in destino.items() if slot not in colocados for g in gs]
    if huerfanos:
        existente = next((i for i, m in enumerate(salida) if m.slot is MealSlot.SUPPLEMENTS), None)
        if existente is None:
            salida.append(ProposedMeal(slot=MealSlot.SUPPLEMENTS, groups=tuple(huerfanos)))
        else:
            salida[existente] = replace(salida[existente],
                                        groups=tuple(salida[existente].groups) + tuple(huerfanos))
    return salida
