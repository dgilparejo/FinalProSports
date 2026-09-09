# -*- coding: utf-8 -*-
"""Cada comprobación del verificador de conformidad DEBE poder fallar.

Un verificador que devuelve 0 puede estar diciendo dos cosas muy distintas: «no hay defectos» o «no estoy mirando».
La segunda ya nos ha pasado —el barrido de la Parte A encontró dos suites que existían y no corrían, y antes un
carácter invisible dejó muerta una rama del anonimizador durante meses—, así que aquí se construye, para cada
comprobación, una dieta que la viola A PROPÓSITO y se exige que la reporte. Y se construye también el caso limpio,
para que la comprobación no se convierta en una que siempre dispara.

Independiente del dataset y de la base de datos, que es el punto: si estas aserciones dependieran del corpus
activo, un rebuild podría vaciarlas sin que nadie se enterase. Las tablas mineras (`Tables`) se sustituyen por un
doble con los valores mínimos que cada comprobación necesita, declarados aquí.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from finalprosports.domain.model import (  # noqa: E402
    ClientProfile, DietItem, DietProposal, Food, FoodFlags, FoodGroup, Goal, MealSlot, Quantity, Unit,
)
from finalprosports.domain.model.diet_proposal import AlternativeGroup, ProposedItem, ProposedMeal  # noqa: E402
from finalprosports.infrastructure.adapter.inbound.eval import conformance as C  # noqa: E402


# ------------------------------------------------------------------------------------------------ dobles mínimos
def food(fid, name, group, secondary=None):
    return Food(id=fid, canonical_name=name, family="x", group=group, secondary_group=secondary,
                flags=FoodFlags(), synonyms=())


CATALOG = {
    1: food(1, "batido de proteínas", FoodGroup.SUPPLEMENT),
    2: food(2, "arroz", FoodGroup.CARB),
    3: food(3, "pollo", FoodGroup.PROTEIN),
    4: food(4, "pavo", FoodGroup.PROTEIN),
    5: food(5, "aceite de oliva virgen extra", FoodGroup.FAT),
    6: food(6, "pasas", FoodGroup.FRUIT),
    7: food(7, "electrolitos", FoodGroup.SUPPLEMENT),
    8: food(8, "zanahoria", FoodGroup.VEGETABLE),
    9: food(9, "remolacha", FoodGroup.VEGETABLE),
}


@dataclass
class FakeStats:
    """`are_interchangeable` decide si un par lo escribió ÉL como alternativa. Aquí se declara explícitamente."""
    pairs: set = field(default_factory=set)

    def are_interchangeable(self, a, b) -> bool:
        return (a, b) in self.pairs or (b, a) in self.pairs


class FakeTables:
    def __init__(self, **over):
        self.catalog = CATALOG
        self.stats = FakeStats(pairs=over.get("pairs", set()))
        self.unquantified = over.get("unquantified", {"electrolitos"})
        self.weighed = over.get("weighed", {"pasas": 25.0})
        self.variants = over.get("variants", {"arroz": {"arroz integral": "Arroz integral"}})
        self.rations = over.get("rations", {"batido de proteínas": "40 g"})
        self.medians = over.get("medians", {"pollo": 200.0, "arroz": 150.0})
        self.daily_totals = over.get("daily_totals", {"PROTEIN": {"n": 1158, "p05": 470.0, "p50": 1050.0, "p95": 2060.0}})
        self.bands = over.get("bands", {"PROTEIN": (0.8, 1.2)})
        self.env = None

    food = C.Tables.food
    name = C.Tables.name
    macro = C.Tables.macro


def item(fid, *, qty=None, unit=Unit.GRAM, display=None, key=None, raw="", slot=MealSlot.LUNCH):
    name = CATALOG[fid].canonical_name
    return DietItem(meal_slot=slot, position=0, component_index=0, food_id=fid, canonical_name=name,
                    normalized_key=key or name, raw_text=raw or name,
                    quantity=Quantity(qty, unit if qty is not None else Unit.NONE), display_name=display)


def proposal(slots: dict, goal=Goal.VOLUME, notes=("Beber 2,4 litros de agua al día.",)) -> DietProposal:
    meals = []
    for slot, groups in slots.items():
        gs = tuple(AlternativeGroup(n, tuple(ProposedItem(i, ()) for i in grp)) for n, grp in enumerate(groups))
        meals.append(ProposedMeal(slot, gs))
    return DietProposal(profile=ClientProfile("X", "p", "M", 30, 180, 5, goal=goal), meals=tuple(meals),
                        notes=tuple(notes), retrieved_case_ids=(), strategy="test", parameters={})


def fired(infractions, check_id) -> bool:
    return any(i.check == check_id for i in infractions)


# ------------------------------------------------------------------------------------------------ una por comprobación
def test_2_suplemento_sin_cantidad_puede_fallar():
    t = FakeTables()
    sucia = proposal({MealSlot.BREAKFAST: [[item(1, qty=None)]]})            # batido sin cantidad, y él la pone
    limpia = proposal({MealSlot.BREAKFAST: [[item(1, qty=40)]]})
    assert fired(C.check_supplements_quantified(sucia, t, ()), "2_suplemento_sin_cantidad")
    assert not C.check_supplements_quantified(limpia, t, ())
    # y no debe disparar con los que él mismo deja sin cantidad
    exenta = proposal({MealSlot.BREAKFAST: [[item(7, qty=None)]]})
    assert not C.check_supplements_quantified(exenta, t, ())


def test_3_generico_con_variante_disponible_puede_fallar():
    t = FakeTables()

    class Caso:
        def __init__(self, diet): self.diet = diet

    class Diet:
        def __init__(self, items): self.meals = (type("M", (), {"slot": MealSlot.LUNCH, "items": items})(),)

    vecinos = [Caso(Diet((item(2, qty=150, key="arroz integral"),))) for _ in range(3)]
    sucia = proposal({MealSlot.BREAKFAST: [[item(2, qty=150)]]})                      # «Arroz» a secas
    limpia = proposal({MealSlot.BREAKFAST: [[item(2, qty=150, display="Arroz integral")]]})
    assert fired(C.check_specific_variant(sucia, t, vecinos), "3_generico_con_variante_disponible")
    assert not C.check_specific_variant(limpia, t, vecinos)


def test_4b_alternativa_no_escrita_puede_fallar():
    t = FakeTables(pairs={(3, 4)})                     # él sí escribe pollo/pavo; nunca pollo/aceite
    sucia = proposal({MealSlot.LUNCH: [[item(3, qty=200), item(5, qty=10)]]})
    limpia = proposal({MealSlot.LUNCH: [[item(3, qty=200), item(4, qty=200)]]})
    assert fired(C.check_alternatives_interchangeable(sucia, t, ()), "4b_alternativa_no_escrita")
    assert not C.check_alternatives_interchangeable(limpia, t, ())


def test_4c_alternativas_de_distinto_papel_puede_fallar():
    t = FakeTables()
    sucia = proposal({MealSlot.LUNCH: [[item(3, qty=200), item(2, qty=150)]]})        # proteína / hidrato
    limpia = proposal({MealSlot.LUNCH: [[item(3, qty=200), item(4, qty=200)]]})       # proteína / proteína
    assert fired(C.check_alternatives_same_role(sucia, t, ()), "4c_alternativas_de_distinto_papel")
    assert not C.check_alternatives_same_role(limpia, t, ())


def test_4d_demasiadas_alternativas_puede_fallar():
    t = FakeTables()
    muchas = [item(f, qty=100) for f in (3, 4, 2, 5, 6, 8, 9)]
    assert fired(C.check_group_size(proposal({MealSlot.LUNCH: [muchas]}), t, ()), "4d_demasiadas_alternativas")
    assert not C.check_group_size(proposal({MealSlot.LUNCH: [[item(3, qty=200), item(4, qty=200)]]}), t, ())


def test_6b_unidad_absurda_puede_fallar():
    t = FakeTables()
    sucia = proposal({MealSlot.SNACK: [[item(6, qty=1, unit=Unit.PIECE)]]})           # «1 pasas»
    limpia = proposal({MealSlot.SNACK: [[item(6, qty=25, unit=Unit.GRAM)]]})
    assert fired(C.check_absurd_units(sucia, t, ()), "6b_unidad_absurda")
    assert not C.check_absurd_units(limpia, t, ())


def test_7b_repetido_entre_franjas_puede_fallar():
    t = FakeTables()
    sucia = proposal({MealSlot.LUNCH: [[item(8, qty=30)], [item(3, qty=200)]],
                      MealSlot.DINNER: [[item(8, qty=30)], [item(3, qty=200)]]})
    limpia = proposal({MealSlot.LUNCH: [[item(8, qty=30)]], MealSlot.DINNER: [[item(9, qty=30)]]})
    salida = C.check_repeated_between_slots(sucia, t, ())
    assert salida, "no reporta un alimento repetido entre comida y cena"
    assert all(i.kind == C.CALIBRATION for i in salida), "es una calibración, no una violación"
    assert not C.check_repeated_between_slots(limpia, t, ())


def test_11_franja_de_entreno_vacia_puede_fallar():
    t = FakeTables()
    vacia = proposal({MealSlot.BREAKFAST: [[item(1, qty=40)]], MealSlot.POST_WORKOUT: [[]]}, goal=Goal.VOLUME)
    salida = C.check_empty_training_slot(vacia, t, ())
    assert salida, "no reporta una franja de entreno impresa y vacía en una dieta de volumen"


def test_1_nota_de_hidratacion_puede_fallar():
    """Lo que el preparador señaló: «no dice cuánta agua». Sin nota y con nota sin cantidad, las dos formas."""
    t = FakeTables()
    sin_nota = proposal({MealSlot.BREAKFAST: [[item(2, qty=150)]]}, notes=("Masticar despacio.",))
    sin_cantidad = proposal({MealSlot.BREAKFAST: [[item(2, qty=150)]]}, notes=("Beber agua durante el día.",))
    buena = proposal({MealSlot.BREAKFAST: [[item(2, qty=150)]]}, notes=("Beber 2,4 litros de agua al día.",))
    assert fired(C.check_hydration_note(sin_nota, t, ()), "1_sin_nota_de_hidratacion")
    assert fired(C.check_hydration_note(sin_cantidad, t, ()), "1_hidratacion_sin_cantidad")
    assert not C.check_hydration_note(buena, t, ())


def test_13_total_diario_puede_fallar():
    """«Parece mucha proteína en total»: cada ración dentro de banda y la suma del día fuera. Nadie lo miraba."""
    t = FakeTables()
    mucha = proposal({MealSlot.LUNCH: [[item(3, qty=900)], [item(4, qty=900)]],
                      MealSlot.DINNER: [[item(3, qty=900)]]})              # 2.700 g > p95 2.060
    poca = proposal({MealSlot.LUNCH: [[item(3, qty=100)]]})                 # 100 g < p05 470
    justa = proposal({MealSlot.LUNCH: [[item(3, qty=600)], [item(4, qty=600)]]})
    assert fired(C.check_daily_totals(mucha, t, ()), "13_total_diario_alto")
    assert fired(C.check_daily_totals(poca, t, ()), "13_total_diario_bajo")
    assert not C.check_daily_totals(justa, t, ())


def test_14_sin_notas_puede_fallar():
    t = FakeTables()
    assert fired(C.check_note_count(proposal({MealSlot.LUNCH: [[item(3, qty=200)]]}, notes=()), t, ()), "14_sin_notas")
    assert not C.check_note_count(proposal({MealSlot.LUNCH: [[item(3, qty=200)]]}), t, ())


# ------------------------------------------------------ las tres nacidas del discriminador (bloque 4 de la 2a ronda)
def test_21_todo_mapeado_puede_fallar():
    """Salta cuando la dieta no lleva NINGUN item sin mapear y el escribe un 1,4 % (mediana).

    Es la unica de las tres que mira una propiedad que el sistema no puede corregir: componer desde un catalogo
    cerrado implica el 0 %. La comprobacion existe para que ese 0 % este DECLARADO y no se lea como perfeccion.
    """
    todos_mapeados = proposal({MealSlot.LUNCH: [[item(3, qty=200)], [item(2, qty=160)], [item(8, qty=100)],
                                                [item(5, qty=10)], [item(6, qty=30)], [item(4, qty=150)],
                                                [item(9, qty=80)], [item(1, qty=40)]]})
    assert fired(C.check_unmapped_share(todos_mapeados, FakeTables(), ()), "21_todo_mapeado")
    # ...y el caso limpio: con un item sin mapear, no salta.
    sin_mapear = DietItem(meal_slot=MealSlot.LUNCH, position=0, component_index=0, food_id=None,
                          canonical_name=None, normalized_key="algo raro", raw_text="algo raro",
                          quantity=Quantity(None, Unit.NONE))
    mezcla = proposal({MealSlot.LUNCH: [[item(3, qty=200)], [item(2, qty=160)], [item(8, qty=100)],
                                        [item(5, qty=10)], [item(6, qty=30)], [item(4, qty=150)],
                                        [item(9, qty=80)], [sin_mapear]]})
    assert not fired(C.check_unmapped_share(mezcla, FakeTables(), ()), "21_todo_mapeado")


def test_22_reparto_de_unidades_puede_fallar():
    """Salta cuando la fraccion de una unidad se sale de SU banda medida. Aqui: todo en cucharadas."""
    cucharadas = proposal({MealSlot.LUNCH: [[item(f, qty=1, unit=Unit.TABLESPOON)] for f in (1, 2, 3, 4, 5, 6, 7, 8, 9)]})
    assert fired(C.check_unit_mix(cucharadas, FakeTables(), ()), "22_reparto_de_unidades")
    # el caso limpio: gramos y piezas en proporciones suyas
    normal = proposal({MealSlot.LUNCH: [[item(f, qty=100)] for f in (2, 3, 4, 5, 8, 9)]
                                       + [[item(f, qty=1, unit=Unit.PIECE)] for f in (1, 6, 7)]})
    assert not fired(C.check_unit_mix(normal, FakeTables(), ()), "22_reparto_de_unidades")


def test_23_reparto_por_macrogrupo_puede_fallar():
    """Salta cuando la proporcion de fruta o verdura se sale de SU banda. Aqui: media dieta de fruta."""
    mucha_fruta = proposal({MealSlot.LUNCH: [[item(6, qty=30)]] * 5 + [[item(3, qty=200)], [item(2, qty=160)],
                                                                       [item(5, qty=10)]]})
    assert fired(C.check_macro_share(mucha_fruta, FakeTables(), ()), "23_reparto_por_macrogrupo")
    # El caso limpio: UNA fruta y UNA verdura entre nueve items (11,1 % cada una, dentro de sus bandas [0 %, 13,0 %]
    # y [0 %, 20,9 %]). Con dos verduras se pasaria al 22,2 % y saltaria -- lo cual esta bien, y es la razon de que
    # este caso lleve solo una: un «limpio» que roza el limite no demuestra que la comprobacion sepa callarse.
    equilibrada = proposal({MealSlot.LUNCH: [[item(3, qty=200)], [item(4, qty=150)], [item(2, qty=160)],
                                             [item(5, qty=10)], [item(1, qty=40)], [item(7, qty=1, unit=Unit.PIECE)],
                                             [item(8, qty=80)], [item(6, qty=30)], [item(3, qty=120)]]})
    assert not fired(C.check_macro_share(equilibrada, FakeTables(), ()), "23_reparto_por_macrogrupo")


def test_toda_comprobacion_esta_cubierta_por_un_test_de_falsabilidad():
    """El guarda del guarda: si mañana se añade una comprobación, este test obliga a añadirle su caso que falla."""
    cubiertas = {C.check_alternative_group_count, C.check_no_duplicate_food_in_slot, C.check_printed_slot_names,
                 C.check_post_workout_present, C.check_hydration_note, C.check_daily_totals, C.check_note_count,
                 C.check_supplements_quantified, C.check_specific_variant, C.check_alternatives_interchangeable,
                 C.check_alternatives_same_role, C.check_group_size, C.check_absurd_units,
                 C.check_repeated_between_slots, C.check_empty_training_slot,
                 C.check_unmapped_share, C.check_unit_mix, C.check_macro_share}
    # Declaradas SIN caso que falla, con su motivo. `check_overlapping_supplements` está vacía a propósito (la
    # observación se refutó sobre el corpus). Las otras dos necesitan la envolvente minada y se cubren en la
    # suite de integración, no aquí, porque su umbral no puede inventarse en un doble.
    sin_caso = {C.check_overlapping_supplements: "refutada sobre el corpus: devuelve [] a propósito",
                C.check_ration_coherence: "necesita ration_bands de la envolvente minada",
                C.check_number_agreement: "depende de SINGULAR del exportador, se cubre en test_pdf_exporter",
                C.check_document_footer: "necesita el exportador real; se cubre en test_pdf_exporter",
                C.check_goal_printed_in_full: "necesita el exportador real; se cubre en test_pdf_exporter"}
    faltan = [c.__name__ for c in C.CHECKS if c not in cubiertas and c not in sin_caso]
    assert not faltan, f"comprobaciones sin test de falsabilidad ni motivo declarado: {faltan}"





# ---------------------------------------------------------------- las que miran el DOCUMENTO (revisión del preparador)
def test_15_grupos_de_alternativas_fuera_de_rango_puede_fallar():
    """La que habría cazado en el acto la regresión de `split_mixed_groups`: 46 grupos donde él escribe 7."""
    t = FakeTables()
    muchos = proposal({MealSlot.LUNCH: [[item(3, qty=200), item(4, qty=200)] for _ in range(14)]})
    pocos = proposal({MealSlot.LUNCH: [[item(3, qty=200)]]})
    justos = proposal({MealSlot.LUNCH: [[item(3, qty=200), item(4, qty=200)] for _ in range(7)]})
    assert fired(C.check_alternative_group_count(muchos, t, ()), "15_demasiados_grupos")
    assert fired(C.check_alternative_group_count(pocos, t, ()), "15_pocos_grupos")
    assert not C.check_alternative_group_count(justos, t, ())


def test_16_alimento_repetido_en_la_franja_puede_fallar():
    """«300 gr Pechuga de pollo» suelto y «320 gr Pechuga de pollo» en un grupo, en la misma cena."""
    t = FakeTables()
    sucia = proposal({MealSlot.DINNER: [[item(3, qty=300)], [item(3, qty=320), item(4, qty=300)]]})
    limpia = proposal({MealSlot.DINNER: [[item(3, qty=300)], [item(4, qty=300)]]})
    assert fired(C.check_no_duplicate_food_in_slot(sucia, t, ()), "16_alimento_repetido_en_la_franja")
    assert not C.check_no_duplicate_food_in_slot(limpia, t, ())


def test_17_franja_que_no_es_suya_puede_fallar():
    """«OTROS» es el cajón del extractor asomando en el documento del cliente."""
    t = FakeTables()
    sucia = proposal({MealSlot.OTHER: [[item(3, qty=200)]]})
    limpia = proposal({MealSlot.DINNER: [[item(3, qty=200)]]})
    assert fired(C.check_printed_slot_names(sucia, t, ()), "17_franja_no_suya")
    assert not C.check_printed_slot_names(limpia, t, ())


def test_17_media_tarde_se_imprime_como_media_tarde():
    from finalprosports.domain.composition.policy.document_template_policy import SLOT_LABEL
    assert SLOT_LABEL[MealSlot.MID_AFTERNOON] == "MEDIA TARDE"
    assert SLOT_LABEL[MealSlot.SNACK] == "MERIENDA"


def test_20_post_entreno_ausente_en_volumen_puede_fallar():
    """En el 79,9 % de sus dietas de volumen la franja lleva contenido; omitirla pierde esa instrucción."""
    t = FakeTables()
    sin = proposal({MealSlot.DINNER: [[item(3, qty=200)]]}, goal=Goal.VOLUME)
    con = proposal({MealSlot.DINNER: [[item(3, qty=200)]], MealSlot.POST_WORKOUT: [[item(1, qty=40)]]}, goal=Goal.VOLUME)
    otra = proposal({MealSlot.DINNER: [[item(3, qty=200)]]}, goal=Goal.FAT_LOSS)
    assert fired(C.check_post_workout_present(sin, t, ()), "20_sin_post_entreno")
    assert not C.check_post_workout_present(con, t, ())
    assert not C.check_post_workout_present(otra, t, ()), "solo aplica a las dietas de volumen"

if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS  {nombre}")
        except AssertionError as e:
            fallos += 1; print(f"FAIL  {nombre}: {e}")
        except Exception as e:  # noqa: BLE001
            fallos += 1; print(f"ERROR {nombre}: {type(e).__name__}: {e}")
    print(f"\n{'FALLAN' if fallos else 'OK'}: {fallos}")
    sys.exit(1 if fallos else 0)
