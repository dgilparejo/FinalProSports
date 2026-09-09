# -*- coding: utf-8 -*-
"""Unit tests for pipeline.parse_items (run with pytest or `python pipeline/tests/test_parse_items.py`)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline.parse_items import parse_item, parse_quantity, split_alternatives  # noqa: E402
from finalprosports.domain.model import Unit  # noqa: E402

G = "CLIENTE_000::CENA::0"


def foods(items):
    return [i.food_text for i in items]


def test_alternatives_with_slash_share_a_group():
    items = parse_item("150 gr Pollo / 160 gr Pavo / 180 gr Lomo", G)
    assert foods(items) == ["Pollo", "Pavo", "Lomo"]
    assert [i.quantity.value for i in items] == [150, 160, 180]
    assert all(i.quantity.unit is Unit.GRAM for i in items)
    assert len({i.alternative_group for i in items}) == 1 and items[0].alternative_group is not None
    assert not any(i.compound_item for i in items)


def test_tablespoon_qualifier_and_preposition_are_consumed():
    (item,) = parse_item("1 cucharada sopera de aceite de oliva virgen extra", G)
    assert item.quantity.value == 1 and item.quantity.unit is Unit.TABLESPOON
    assert item.food_text == "aceite de oliva virgen extra"


def test_teaspoon_variants():
    assert parse_quantity("1 cucharada pequeña de miel")[0].unit is Unit.TEASPOON
    assert parse_quantity("1 cucharadita de canela")[0].unit is Unit.TEASPOON
    assert parse_quantity("1 cucharada de postre de cacao")[0].unit is Unit.TEASPOON


def test_alternatives_with_o():
    items = parse_item("250 ml leche Almendras o Yogurt batido Natural sin azúcar y sin lactosa", G)
    assert len(items) == 2 and items[0].alternative_group == items[1].alternative_group
    assert items[0].quantity.unit is Unit.MILLILITER and items[0].quantity.value == 250
    assert items[1].food_text.startswith("Yogurt batido Natural")
    assert not any(i.compound_item for i in items)          # "y sin lactosa" is a descriptor, not a second food


def test_o_between_adjectives_does_not_split():
    assert split_alternatives("yogur natural o griego") == ["yogur natural o griego"]
    assert split_alternatives("pollo o pavo") == ["pollo", "pavo"]


def test_compound_item():
    items = parse_item("2 claras de huevo y 2 yemas con 1 lata de atún", G)
    assert len(items) == 3 and all(i.compound_item for i in items)
    assert len({i.compound_group for i in items}) == 1
    assert foods(items) == ["huevo", "yemas", "atún"] or foods(items) == ["claras de huevo", "yemas", "atún"]
    assert items[2].quantity.unit is Unit.CAN and items[2].quantity.value == 1


def test_instruction_without_food():
    (item,) = parse_item("NADA DURANTE 1 HORA", G)
    assert item.is_instruction and item.food_text is None and item.quantity.value is None


def test_implicit_piece():
    (item,) = parse_item("1 kiwi", G)
    assert item.quantity.value == 1 and item.quantity.unit is Unit.PIECE and item.food_text == "kiwi"


def test_food_without_quantity():
    (item,) = parse_item("Ensalada de tomate", G)
    assert not item.is_instruction and item.quantity.value is None and item.quantity.unit is Unit.NONE
    assert item.food_text == "Ensalada de tomate"


def test_uncovered_unit_is_reported_not_invented():
    (item,) = parse_item("2 tazas de caldo", G)
    assert item.quantity.value == 2 and item.quantity.unit is Unit.NONE and item.quantity.raw_unit == "taza"
    assert item.food_text == "caldo"


def test_scoop_and_capsule_units():
    (item,) = parse_item("2 cazos de proteína", G)
    assert item.quantity.value == 2 and item.quantity.unit is Unit.SCOOP and item.food_text == "proteína"
    for text in ("1 cápsula de omega 3", "2 perlas de onagra", "1 tableta de magnesio", "1 pastilla de potasio"):
        (item,) = parse_item(text, G)
        assert item.quantity.unit is Unit.CAPSULE, text


def test_signature_noise_is_flagged_not_parsed():
    for text in ('("', "tel", "correos/mail:", '" tel'):
        (item,) = parse_item(text, G)
        assert item.is_noise and not item.is_instruction and item.food_text is None, text


def test_descriptor_only_alternatives_are_not_split():
    items = parse_item("15 gr Almendras o nueces crudas o tostadas sin sal", G)
    assert [i.food_text for i in items] == ["Almendras", "nueces crudas o tostadas sin sal"]
    items = parse_item("300 gr Pescado PLANCHA, COCIDO O HERVIDO", G)
    assert len(items) == 1 and items[0].food_text.startswith("Pescado")


def test_fraction_is_not_an_alternative():
    (item,) = parse_item("1/2 aguacate", G)
    assert item.quantity.value == 0.5 and item.food_text == "aguacate" and item.alternative_group is None


def test_parenthesis_goes_to_note_and_name_is_never_truncated():
    (item,) = parse_item("200 gr Pollo (cualquier parte)", G)
    assert item.food_text == "Pollo" and item.note == "cualquier parte"
    long_name = "1 cucharada sopera de aceite de oliva virgen extra ecológico de primera presión en frío"
    (item,) = parse_item(long_name, G)
    assert item.food_text == "aceite de oliva virgen extra ecológico de primera presión en frío"
    assert len(item.food_text) > 30


def test_quantity_alternatives_in_parentheses_and_ranges():
    items = parse_item("200 gr (atún, pollo o pavo)", G)
    assert foods(items) == ["atún", "pollo", "pavo"] and all(i.quantity.value == 200 for i in items)
    (item,) = parse_item("1 o 2 latas de atún", G)
    assert item.quantity.value == 1.5 and item.quantity.unit is Unit.CAN and item.food_text == "atún"


def test_header_label_is_stripped():
    items = parse_item("MITAD DE ENTRENAMIENTO: 2 cucharadas de aminoácidos", G)
    assert len(items) == 1 and items[0].food_text == "aminoácidos" and items[0].quantity.unit is Unit.TABLESPOON
    (item,) = parse_item("MITAD DE ENTRENAMIENTO: NADA", G)
    assert item.is_instruction


def test_instruction_with_a_quantified_alternative_keeps_the_food():
    """Observacion del preparador: su post-entreno desaparecia de las propuestas.

    La linea es una condicion Y su alternativa. Juzgada entera es instruccion, y con ella se iba el batido, la
    amilopectina y las sales. Se rescata la rama que empieza por cantidad; la rama-instruccion se descarta.
    """
    raw = ("No ingerir nada durante al menos 1 hora despues de entrenamientos en ayunas o "
           "1 Batido de 40gr proteinas con 30 gr Amilopeptinas + 2 Sales minerales")
    items = parse_item(raw, "D::DESPUES DE ENTRENAR::0")
    assert not any(i.is_instruction for i in items), [i.raw_text for i in items]
    foods = {i.food_text.lower() for i in items if i.food_text}
    assert any("batido" in f or "proteina" in f for f in foods), foods
    assert any("sales minerales" in f for f in foods), foods


def test_instruction_without_a_quantified_alternative_stays_an_instruction():
    """El rescate exige CANTIDAD. Sin numero delante, una rama de prosa no es una racion.

    Medido sobre el corpus: rescatar toda rama no-instruccion daba 203 lineas, la mayoria jirones ("camina en
    ayunas"); exigir la cantidad deja 37, todas raciones reales.
    """
    for raw in ("No desayunes, entrena o camina en ayunas",
                "Intenta beber Te Verde o Cafe solo y evitar las bebidas con gas"):
        items = parse_item(raw, "D::DESAYUNO::0")
        assert len(items) == 1 and items[0].is_instruction, (raw, [i.food_text for i in items])


def test_a_quantity_hidden_inside_the_name_becomes_the_quantity():
    """Observacion del preparador: «el batido y la caseina, con sus gramos».

    El escribe «1 batido 48 gr Proteinas»: el 1 cuenta batidos y los 48 gr son la racion. Leidos como «1 unidad» los
    gramos se iban con el nombre al canonicalizar. 733 componentes del corpus traen la cantidad dentro del nombre.
    """
    for raw, valor, unidad in (("1 batido 48 gr Proteinas", 48.0, "g"),
                               ("1 Batido de 60gr proteinas", 60.0, "g"),
                               ("1 BATIDO 2 CAZOS 40 gr Proteinas", 40.0, "g")):
        items = parse_item(raw, "D::DESAYUNO::0")
        assert len(items) == 1, [i.food_text for i in items]
        assert items[0].quantity.value == valor and items[0].quantity.unit.value == unidad, (raw, items[0].quantity)
        assert "gr" not in (items[0].food_text or "").lower().split(), items[0].food_text


def test_the_promotion_does_not_decide_what_it_cannot_know():
    """Con multiplicador distinto de 1 no se toca: «2 latas de atun de 80 gr» serian 80 o 160 y elegir seria inventar.
    Con dos cantidades dentro del nombre, tampoco. Y si al quitar el numero no queda nombre, se deja entero."""
    dos_latas = parse_item("2 latas de atun de 80 gr", "D::COMIDA::0")[0]
    assert dos_latas.quantity.value == 2.0 and dos_latas.quantity.unit.value == "lata", dos_latas.quantity
    assert "80" in (dos_latas.food_text or ""), dos_latas.food_text
    solo = parse_item("1 Platano", "D::DESAYUNO::0")[0]
    assert solo.quantity.value == 1.0 and solo.quantity.unit.value == "unidad"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failed else 0)
