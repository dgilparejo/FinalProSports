# -*- coding: utf-8 -*-
"""S6 · The generated PDF contains every section of the professional's template (rendered through the domain policy), is a valid multi-page
PDF, carries both brand assets, keeps the professional's annex on its own page and tolerates missing logos / contact. No database needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.domain.composition.policy.document_template_policy import GOAL_TEXT, MID_TRAINING  # noqa: E402
from finalprosports.domain.model import AlternativeGroup, ClientProfile, DietItem, DietProposal, Goal, ItemEvidence, MealSlot, ProposedItem, ProposedMeal, Quantity, Unit  # noqa: E402
from finalprosports.domain.model.lab_result import LabResult  # noqa: E402
from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import LOGO, LOGO_LIGHT, PdfDietExporterAdapter  # noqa: E402

pytestmark = pytest.mark.infrastructure


def it(slot, fid, name, qty, unit=Unit.GRAM):
    return ProposedItem(DietItem(slot, 0, 0, fid, name, name, name, Quantity(qty, unit)), ItemEvidence(("C::v01",), 0.8))


def meal(slot, *groups):
    return ProposedMeal(slot, tuple(AlternativeGroup(i, tuple(g)) for i, g in enumerate(groups)))


PROPOSAL = DietProposal(ClientProfile("DEMO_X", "p", "M", 41, 176, 4, goal=Goal.KETO),
                        tuple(meal(s, [it(s, i, f"alimento {i}", 100)]) for i, s in enumerate((MealSlot.BREAKFAST, MealSlot.MID_MORNING, MealSlot.LUNCH, MealSlot.SNACK, MealSlot.DINNER))),
                        tuple(f"nota número {i} del profesional, con texto suficiente para comprobar el ajuste de línea en el documento" for i in range(12)), ("C::v01",), "case_based_composer")


def _pages(pdf: bytes) -> int:
    return max(pdf.count(b"/Type /Page\n"), pdf.count(b"/Type/Page\n"), pdf.count(b"/Type /Page ") + pdf.count(b"/Type/Page/"), 1)


def test_document_sections_and_pdf_validity():
    exporter = PdfDietExporterAdapter(brand="Marca Demo", contact="correo demo | Tel: demo")
    doc = exporter.document(PROPOSAL, "Cliente Demo Ficticio")
    assert [l.kind for l in doc.lines][:2] == ["header", "objetivo"]
    # MERIENDA prints as MERIENDA. Until dataset-v3 the model had no MEDIA TARDE slot, so the template table
    # carried a workaround that printed SNACK under the "MEDIA TARDE" header, and this expectation was written
    # against the workaround. v3 separated the two slots (v2's 896 MERIENDA diets are v3's MERIENDA *plus* its
    # MEDIA TARDE), the workaround was removed in document_template_policy, and the fixture's slot is SNACK.
    # The expectation, not the code, is what was left behind.
    assert doc.of("slot") == ("DESAYUNO:", "MEDIA MAÑANA:", "COMIDA (lo más tarde que puedas):", "MERIENDA:", "CENA (Lo más temprano que puedas):")
    # The post-workout slot is omitted when empty rather than printed as «Nada»: measured over his volume diets, that is
    # what he does 58,4 % of the time, and the printed «Nada» is the line the professional called an erratum.
    assert len(doc.of("item")) == 5 and doc.of("training") == ("ANTES DE ENTRENAR: Nada", MID_TRAINING)
    assert doc.of("notes_title") == ("Notas:",) and len(doc.of("note")) == 12 and doc.of("footer") == ("correo demo / Tel: demo",)
    pdf = exporter.export(PROPOSAL, "DEMO_X::e01", "consenso de casos (cliente nuevo)", lab_results=(LabResult("Glucosa", 101, "mg/dL", 70, 100),), client_name="Cliente Demo Ficticio")
    assert pdf[:5] == b"%PDF-" and len(pdf) > 10_000
    assert LOGO.exists() and LOGO_LIGHT.exists(), "brand assets missing from the export package"


def test_export_without_logos_and_without_contact_still_works(tmp_path):
    exporter = PdfDietExporterAdapter(logo=tmp_path / "missing.jpg", light_logo=tmp_path / "missing2.jpg")
    pdf = exporter.export(PROPOSAL)
    assert pdf[:5] == b"%PDF-" and exporter.document(PROPOSAL).of("footer") == ()


def test_the_document_carries_nothing_but_his_diet():
    """He does not put an analysis, or the engine's adjustments, inside a diet: neither does the exporter. The lab
    results are accepted by the signature and deliberately ignored — the professional sees them on the proposal screen."""
    plain = DietProposal(PROPOSAL.profile, PROPOSAL.meals[:2], ("una nota",), ("C::v01",), "rotation_composer")
    exporter = PdfDietExporterAdapter(contact="")
    bare = exporter.export(plain)
    with_labs = exporter.export(plain, lab_results=(LabResult("Glucosa", 101, "mg/dL", 70, 100), LabResult("LDL", 180, "mg/dL", None, 130)))
    assert _pages(bare) == _pages(with_labs) == 1, "the lab results added a page to the client's document"
    assert len(bare) == len(with_labs), "the lab results changed the document"
    assert b"Glucosa" not in with_labs and b"Anexo" not in with_labs


def _header_boxes(goal_text: str, client_name: str = "Nora Ficticia Demo"):
    """Lays out the two centred header lines on a page that has both logos and returns the box of every string drawn."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from finalprosports.infrastructure.adapter.outbound.export import pdf_diet_exporter_adapter as X

    class _Spy(X._Page):                                                   # noqa: SLF001 — the geometry is the thing under test
        def _image(self, *args, **kwargs):                                 # noqa: ANN002, ANN003 — the pixels are irrelevant, the box is not
            return None

        def _draw(self, x_cm, y_cm, s, size, bold=False, colour="#000000", ha="left", va="top", underline=False):  # noqa: ANN001, PLR0913
            self.boxes.append((x_cm, x_cm + self._text_width_cm(s, size, bold), y_cm))

    page = _Spy(plt, {"logo": 1, "secondary": 1})
    page.boxes = []
    page.first_page_logos()
    page.y = X.M_TOP + X._line_cm(12)                                      # noqa: SLF001 — the empty paragraph that anchors the logos
    page.title(f"DIETA {client_name}  08 / 09 / 26")
    page.centred_label_line(f"Objetivo: {goal_text}", 12.0)
    plt.close(page.fig)
    return X, page.boxes


@pytest.mark.parametrize("goal_text", sorted(set(GOAL_TEXT.values())))
def test_the_header_never_runs_over_the_logos_or_off_the_sheet(goal_text):
    """The regression of 2026-09-08, reported by the professional on an exported diet of his own.

    «Objetivo:» is centred on the full text width at 12 pt, but the two corner logos are drawn ON that width, leaving a gap of
    only 12,32 cm. Three of the nine goal texts are wider than the gap and the fasting one measured 26,6 cm on a 21 cm sheet:
    it was laid out across both logos and off the paper on either side. The title had the same latent defect, since the client's
    name is free text."""
    X, boxes = _header_boxes(goal_text)
    logo_bottom = max(X.LOGO_BOX[1] + X.LOGO_BOX[3], X.LOGO_TEAM_BOX[1] + X.LOGO_TEAM_BOX[3])
    left_edge, right_edge = X.LOGO_BOX[0] + X.LOGO_BOX[2], X.LOGO_TEAM_BOX[0]
    for x0, x1, y in boxes:
        assert x0 >= X.M_LEFT - 1e-3 and x1 <= X.PAGE_W - X.M_RIGHT + 1e-3, f"off the text width at y={y:.3f}: {x0:.3f}-{x1:.3f}"
        if y < logo_bottom:                                                # the line runs alongside the logos
            assert x0 >= left_edge - 1e-3, f"over the brand logo at y={y:.3f}: starts at {x0:.3f} < {left_edge:.3f}"
            assert x1 <= right_edge + 1e-3, f"over the team badge at y={y:.3f}: ends at {x1:.3f} > {right_edge:.3f}"


def test_a_long_client_name_shrinks_the_title_instead_of_crossing_the_logos():
    X, boxes = _header_boxes("Ganar masa muscular", "Nora Ficticia Demo Con Un Nombre Larguisimo De Prueba")
    title = [b for b in boxes if b[2] < X.M_TOP + X._line_cm(12) + 0.7]    # noqa: SLF001 — the title shares one baseline
    assert title, "the title was not drawn"
    assert min(b[0] for b in title) >= X.LOGO_BOX[0] + X.LOGO_BOX[2] - 1e-3
    assert max(b[1] for b in title) <= X.LOGO_TEAM_BOX[0] + 1e-3
