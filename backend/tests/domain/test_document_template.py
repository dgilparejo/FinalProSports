# -*- coding: utf-8 -*-
"""Domain tests (S6, against two original documents): the rendered document follows the professional's template — header
«DIETA <cliente>  DD / MM / AA», «Objetivo:» in the client's own words when given, «Recién levantado (…): …» inline, slots in upper case with the
fasting / keto timing hints («MEDIA TARDE» is his label for the afternoon slot), «cantidad gr Alimento / alternativa», the three training lines
with upper-case labels, «Notas:» with plain sentences, and the contact line only when configured."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.document_template_policy import MID_TRAINING, item_text, render_document  # noqa: E402
from finalprosports.domain.model import AlternativeGroup, ClientProfile, DietItem, DietProposal, Goal, ItemEvidence, MealSlot, ProposedItem, ProposedMeal, Quantity, Unit  # noqa: E402


def it(slot, fid, name, qty, unit=Unit.GRAM):
    return ProposedItem(DietItem(slot, 0, 0, fid, name, name, name, Quantity(qty, unit)), ItemEvidence(("C::v01",), 0.8))


def meal(slot, *groups):
    return ProposedMeal(slot, tuple(AlternativeGroup(i, tuple(g)) for i, g in enumerate(groups)))


PROPOSAL = DietProposal(ClientProfile("DEMO_X", "p", "M", 41, 176, 4, goal=Goal.INTERMITTENT_FASTING),
                        (meal(MealSlot.ON_WAKING, [it(MealSlot.ON_WAKING, 9, "electrolitos", 2, Unit.PIECE)]),
                         meal(MealSlot.LUNCH, [it(MealSlot.LUNCH, 1, "pollo", 250), it(MealSlot.LUNCH, 2, "ternera", 280), it(MealSlot.LUNCH, 3, "lomo", 230)], [it(MealSlot.LUNCH, 4, "aguacate", 60)]),
                         meal(MealSlot.SNACK, [it(MealSlot.SNACK, 10, "almendras", 23)]),
                         meal(MealSlot.DINNER, [it(MealSlot.DINNER, 5, "clara de huevo", 3, Unit.PIECE)], [it(MealSlot.DINNER, 6, "aceite de oliva virgen extra", 1, Unit.TABLESPOON)], [it(MealSlot.DINNER, 7, "atún", 2, Unit.CAN)]),
                         meal(MealSlot.POST_WORKOUT, [it(MealSlot.POST_WORKOUT, 8, "creatina", 5)])),
                        ("Beber 2,5 litros de agua al día", "No tomar postres ni azúcar"), ("C::v01",), "rotation_composer")


def test_header_objetivo_inline_slots_items_training_notes_and_footer():
    doc = render_document(PROPOSAL, "Cliente Demo Ficticio", date(2026, 8, 26), ("correo de contacto", "Tel: 000"))
    kinds = [l.kind for l in doc.lines]
    assert kinds[:3] == ["header", "objetivo", "inline"] and kinds[-1] == "footer"
    assert doc.of("header") == ("DIETA Cliente Demo Ficticio  26 / 08 / 26",)                          # two spaces before the date, as he types it
    assert doc.of("objetivo")[0].startswith("Objetivo: Ayuno intermitente")
    assert doc.of("inline") == ("Recién levantado (30 min antes del desayuno): 2 Electrolitos",)
    # MERIENDA prints as MERIENDA. Until dataset-v3 the model had no MEDIA TARDE slot, so the template printed
    # MERIENDA under that label; with both slots real the relabelling would put the wrong header on a real
    # MERIENDA. The fasting hints and his wording are unchanged.
    assert doc.of("slot") == ("COMIDA (lo más tarde que puedas):", "MERIENDA:", "CENA (Lo más temprano que puedas):")
    items = doc.of("item")
    assert items[0] == "250 gr Pollo / 280 gr Ternera / 230 gr Lomo" and items[1] == "60 gr Aguacate" and items[2] == "23 gr Almendras"
    assert items[3] == "3 Clara de huevo" and items[4] == "1 cucharada de Aceite de oliva virgen extra" and items[5] == "2 latas de Atún"
    assert doc.of("training") == ("ANTES DE ENTRENAR: Nada", MID_TRAINING, "DESPUES DE ENTRENAR: 5 gr Creatina")
    assert doc.of("notes_title") == ("Notas:",) and doc.of("note") == ("Beber 2,5 litros de agua al día", "No tomar postres ni azúcar")   # plain sentences, no bullets
    assert doc.of("footer") == ("correo de contacto / Tel: 000",)                                        # one line: «correo / Tel: teléfono»


def test_goal_in_the_clients_own_words_and_no_key_when_no_name():
    volume = DietProposal(ClientProfile("DEMO_Y", "p", "F", 30, 165, 3, goal=Goal.VOLUME), (meal(MealSlot.LUNCH, [it(MealSlot.LUNCH, 1, "pollo", 200)]),), (), (), "case_based_composer")
    doc = render_document(volume, None, date(2026, 1, 5), goal_text="ganar masa muscular y tonificar")
    assert doc.of("header") == ("DIETA  05 / 01 / 26",) and doc.of("slot") == ("COMIDA:",)             # S9: the internal key is never printed
    assert doc.of("objetivo") == ("Objetivo: Ganar masa muscular y tonificar",)                          # the record's words win over the goal's generic text
    assert render_document(volume, None, date(2026, 1, 5)).of("objetivo") == ("Objetivo: Ganar masa muscular",)
    assert doc.of("footer") == () and doc.of("notes_title") == () and doc.of("inline") == ()
    # The post-workout slot is OMITTED when it has nothing in it, because that is what he does: measured over his volume
    # diets, when it ends up empty he leaves the label out 58,4 % of the time and prints «Nada» 41,6 %. The pre-workout goes
    # the other way (he prints it 60,9 % of the time), so it stays.
    assert doc.of("training") == ("ANTES DE ENTRENAR: Nada", MID_TRAINING)
    assert item_text(it(MealSlot.LUNCH, 9, "plátano", 1, Unit.PIECE)) == "1 Plátano" and item_text(it(MealSlot.LUNCH, 9, "avena", 40.5)) == "40,5 gr Avena"


def test_every_goal_prints_an_objective_line_including_sin_clasificar():
    """`19_objetivo_vacio`: la linea «Objetivo:» sale SIEMPRE, tambien con `sin_clasificar`.

    `GOAL_TEXT[UNCLASSIFIED]` era la cadena vacia y `render_document` solo emite la linea cuando hay texto, asi que 52
    de sus 815 dietas (6,4 %) salian sin objetivo. La comprobacion no es «UNCLASSIFIED tiene texto» sino «NINGUN
    objetivo del enum se queda sin linea»: asi un objetivo nuevo con la entrada olvidada tambien lo rompe.
    """
    for g in Goal:
        p = DietProposal(ClientProfile("DEMO_Z", "p", "M", 30, 175, 3, goal=g), (meal(MealSlot.LUNCH, [it(MealSlot.LUNCH, 1, "pollo", 200)]),), (), (), "case_based_composer")
        linea = render_document(p, None, date(2026, 1, 5)).of("objetivo")
        assert linea and linea[0].strip() not in ("", "Objetivo:"), g
    # y sus palabras siguen ganando cuando existen, tambien en sin_clasificar
    sin = DietProposal(ClientProfile("DEMO_Z", "p", "M", 30, 175, 3, goal=Goal.UNCLASSIFIED), (meal(MealSlot.LUNCH, [it(MealSlot.LUNCH, 1, "pollo", 200)]),), (), (), "case_based_composer")
    assert render_document(sin, None, date(2026, 1, 5), goal_text="dieta detox preparativa").of("objetivo") == ("Objetivo: Dieta detox preparativa",)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
