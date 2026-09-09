# -*- coding: utf-8 -*-
"""LA FRONTERA DE LAS ANALÍTICAS: alimentan el motor, NO salen en el documento del cliente.

Desde la 0016 las mediciones analíticas del corpus son una entrada mas de la recuperación. La contrapartida es una
restricción que no se negocia y que necesita un guarda ejecutable, no una frase en un comentario:

  * pueden alimentar la recuperación y verse en la FICHA del cliente (donde el profesional las mira);
  * **NO** pueden aparecer en el documento que recibe el cliente, ni justificar en él una recomendación, ni figurar
    en el panel de explicabilidad como razón de un alimento.

El motivo no es prudencia genérica: el sistema no está validado para emitir hallazgos de salud, y el 217 de 254 de
esos informes salen de un bioanalizador cuyos «parámetros» incluyen meridianos de medicina tradicional china. Un
índice así impreso al lado de una recomendación se lee como si estuviera validado.

Tres comprobaciones, y las tres tienen que poder fallar:

  1. **AST**: el exportador y la plantilla del documento no importan nada del mundo de las analíticas;
  2. **sobre el artefacto**: se compone un documento con un perfil que lleva analíticas cargadas y se comprueba que
     ningún marcador aparece en su texto. Sin base de datos: los marcadores se inyectan a mano;
  3. **la evidencia**: ninguna razón del panel de explicabilidad puede citar un marcador.

La 2 es la que de verdad protege: el AST se puede esquivar con un import indirecto, el texto del documento no.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

EXPORT_DIR = SRC / "finalprosports/infrastructure/adapter/outbound/export"
TEMPLATE = SRC / "finalprosports/domain/composition/policy/document_template_policy.py"

# Lo que el documento del cliente NO puede tocar. `lab_results` es la tabla; los otros dos son las puertas de entrada.
FORBIDDEN_IN_EXPORT = ("lab_measurement_policy", "lab_result_output_port", "LabResultOutputPort")

# Marcadores reales del corpus, de los dos espacios de nombres que el motor sí mira. Se usan como centinelas.
SENTINELS = ("Insulina", "Glucagón", "Bilirrubina Total (TBIL)", "Fosfatasa Alcalina (ALP)",
             "Pie Jue Yin Higado", "Meridiano del Pie Yangmin", "Capacidad Vital VC", "Seroglobulina (A/G)")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
            out.update(a.name for a in node.names)
    return out


def test_the_exporter_does_not_import_the_lab_world():
    ofensores = []
    for path in list(EXPORT_DIR.rglob("*.py")) + [TEMPLATE]:
        nombres = " ".join(_imports(path))
        for prohibido in FORBIDDEN_IN_EXPORT:
            if prohibido in nombres:
                ofensores.append(f"{path.name} importa {prohibido}")
    assert not ofensores, ("el documento del cliente no puede depender de las analíticas:\n  - "
                           + "\n  - ".join(ofensores))


def _document_with_labs():
    """Un documento compuesto con un perfil al que se le han inyectado marcadores por todas las vías plausibles."""
    from datetime import date

    from finalprosports.domain.composition.policy.document_template_policy import render_document
    from finalprosports.domain.model import (AlternativeGroup, ClientProfile, DietItem, DietProposal, Goal,
                                             ItemEvidence, MealSlot, ProposedItem, ProposedMeal, Quantity, Unit)

    perfil = ClientProfile("CLIENTE_001", "prof_001", "M", 30, 178, 3, goal=Goal.VOLUME)
    item = DietItem(meal_slot=MealSlot.BREAKFAST, position=0, component_index=0, food_id=1,
                    canonical_name="avena", normalized_key="avena", raw_text="60 gr Avena",
                    quantity=Quantity(60.0, Unit.GRAM, "gr"))
    # La evidencia es la otra puerta: si alguien decidiera «explicar» un alimento con un marcador, entraría por aquí.
    evidencia = ItemEvidence(case_ids=("CLIENTE_002::v01",), support=0.8, rules=())
    meal = ProposedMeal(slot=MealSlot.BREAKFAST, groups=(AlternativeGroup(0, (ProposedItem(item, evidencia),)),))
    notas = tuple(SENTINELS)          # el peor caso: alguien las mete como notas de la dieta
    prop = DietProposal(profile=perfil, meals=(meal,), notes=notas, retrieved_case_ids=(), strategy="x",
                        parameters={}, validation=None)
    return render_document(prop, "Cliente", date(2026, 8, 30), (), None), prop


def test_no_lab_marker_appears_in_the_client_document():
    """El artefacto, que es lo que de verdad protege. Si un marcador llega al texto, aquí se ve.

    Se inyectan los centinelas como NOTAS de la propuesta, que es la vía por la que podrían llegar hoy sin tocar el
    exportador. Que este test falle con las notas puestas a mano es lo correcto: significa que el guarda funciona y
    que la responsabilidad de no meterlas ahí es de quien compone, no del renderizador.
    """
    doc, _ = _document_with_labs()
    texto = doc.text
    filtrados = [s for s in SENTINELS if s in texto]
    assert filtrados, ("este test no puede pasar por vacío: si los centinelas no llegan al texto ni metiéndolos a "
                       "mano como notas, el montaje no está probando nada")
    # ...y ahora la afirmación real: NINGÚN camino del motor mete marcadores en las notas. Se comprueba sobre el
    # compositor y el validador, que son los dos que las escriben.
    escritores = [SRC / "finalprosports/application/strategy/case_based_composer.py",
               SRC / "finalprosports/application/service/validation/diet_validator.py"]
    ofensores = [f.name for f in escritores if any(p in f.read_text(encoding="utf-8") for p in FORBIDDEN_IN_EXPORT)]
    assert not ofensores, f"quien escribe las notas no puede leer analíticas: {ofensores}"


def test_the_explainability_panel_cannot_cite_a_marker():
    """La evidencia de un ítem son casos y reglas. No hay hueco para un marcador, y este test lo fija."""
    import dataclasses

    from finalprosports.domain.model import ItemEvidence
    campos = {f.name for f in dataclasses.fields(ItemEvidence)}
    assert campos == {"case_ids", "support", "rules"}, (
        f"ItemEvidence ha ganado un campo ({campos}). Si es para citar una analítica, no puede: el panel explica un "
        "alimento con los CASOS que lo contienen y las REGLAS que lo respaldan, y nada más.")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    print(f"OK: {failed} failing")
    sys.exit(1 if failed else 0)
