# -*- coding: utf-8 -*-
"""EL OBJETIVO QUE SE IMPRIME ES EL DE LA DIETA, no el que el cliente dijo que quería hace meses.

El defecto, encontrado usando la aplicación: generó una dieta de **definición** y otra de **ayuno
intermitente** para el mismo cliente y **las dos salían impresas como «Ganar masa muscular y tonificar»**.

La causa era una regla de precedencia escrita al revés. `ClientRecord.sports.goals_text` es el objetivo **en palabras
del cliente**, recogido en la hoja de entrada, y **no cambia nunca**; el objetivo de una DIETA sí cambia. El
renderizador daba prioridad absoluta al texto libre:

    obj = (goal_text or "").strip() or GOAL_TEXT.get(goal, "")

así que en cuanto el expediente tenía texto, ninguna dieta podía imprimir otro objetivo. **El dato estaba bien
guardado** —`definicion_grasa` y `ayuno_intermitente` en la columna y en el payload—; lo que fallaba era el documento.

La regla correcta, y la que este fichero fija: el texto del cliente se usa **solo cuando el objetivo de la dieta ES el
que él declaró**. Si la dieta persigue otra cosa, manda el objetivo de la dieta. No se intenta adivinar si el texto
«encaja»: se comparan los objetivos ESTRUCTURADOS, que son un dato y no una interpretación.

Por qué el sesgo va en ese sentido: imprimir el objetivo canónico cuando podría haberse usado el texto del cliente
produce un documento correcto y algo más seco. Al revés se le entrega a una persona una dieta de definición que dice
«Ganar masa muscular», y eso es un documento equivocado.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.usecase.diet.export_diet_use_case import ExportDietUseCase  # noqa: E402
from finalprosports.domain.model import ClientProfile, DietProposal, Goal  # noqa: E402
from finalprosports.domain.model.client_record import (ClientRecord, DietPreferences, Identification,  # noqa: E402
                                                       MedicalHistory, Physiology, SportsProfile)

DECLARADO = "Ganar masa muscular y tonificar"


class FakeProposals:
    def __init__(self, goal):
        self.goal = goal

    def get(self, professional_id, diet_id):
        perfil = ClientProfile("c1", professional_id, "M", 30, 178, 3, goal=self.goal)
        return DietProposal(profile=perfil, meals=(), notes=(), retrieved_case_ids=(), strategy="x",
                            parameters={"routing": "cold_start"}, validation=None)


class FakeRecords:
    def get(self, professional_id, client_code):
        return ClientRecord(client_code, professional_id, Identification("Nombre Ficticio"), Physiology(),
                            MedicalHistory(), DietPreferences(), SportsProfile(goals_text=DECLARADO))


class FakeClients:
    """El perfil del CLIENTE: su objetivo declarado, que es el que acompaña al texto libre del expediente."""

    def __init__(self, goal=Goal.VOLUME):
        self.goal = goal

    def get(self, professional_id, client_code):
        return ClientProfile(client_code, professional_id, "M", 30, 178, 3, goal=self.goal)


class SpyExporter:
    """Captura con qué `goal_text` se llama al exportador, que es exactamente donde se decidía mal."""

    def __init__(self):
        self.goal_text = "no llamado"

    def export(self, proposal, diet_id="", strategy_label=None, lab_results=(), client_name=None, goal_text=None):
        self.goal_text = goal_text
        return b"%PDF"


def _run(diet_goal, client_goal=Goal.VOLUME, clients=True):
    spy = SpyExporter()
    uc = ExportDietUseCase(FakeProposals(diet_goal), spy, None, FakeRecords(),
                           exporters={"pdf": spy}, clients=FakeClients(client_goal) if clients else None)
    uc.export("p", "c1::e05", "pdf")
    return spy.goal_text


def test_a_diet_with_another_goal_does_not_print_the_clients_stated_one():
    """El caso reportado: definición y ayuno salían como «Ganar masa muscular y tonificar»."""
    assert _run(Goal.FAT_LOSS) is None, "la dieta de definición seguía imprimiendo el objetivo declarado del cliente"
    assert _run(Goal.INTERMITTENT_FASTING) is None, "la de ayuno intermitente, igual"


def test_the_clients_own_words_are_used_when_they_do_describe_this_diet():
    """Y el test que impide 'arreglarlo' tirando el texto libre: cuando coincide, se usa, que era el punto de S6."""
    assert _run(Goal.VOLUME) == DECLARADO


def test_without_a_client_repository_the_free_text_is_not_used():
    """Si no se puede comprobar la coincidencia, no se usa: el sesgo va hacia el documento correcto y aburrido."""
    assert _run(Goal.VOLUME, clients=False) is None


def test_a_client_with_no_declared_goal_does_not_lend_his_words_to_any_diet():
    assert _run(Goal.VOLUME, client_goal=None) is None


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    print(f"OK: {failed} failing")
    sys.exit(1 if failed else 0)
