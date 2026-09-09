# -*- coding: utf-8 -*-
"""The .odt export is a valid OpenDocument and carries the same document as the PDF.

He writes his diets in LibreOffice Writer, so the .odt is not a convenience: it is the document he can still edit, which is
what he does today with the previous version of every client. Both formats render the same `DietDocument`, so the assertion
is that the text of one is the text of the other — a divergence would mean two documents with the same name.
"""
import io
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # the PDF test holds the shared fixture

from finalprosports.domain.composition.policy.document_template_policy import GOAL_TEXT  # noqa: E402
from finalprosports.infrastructure.adapter.outbound.export import odt_diet_exporter_adapter as O  # noqa: E402
from finalprosports.infrastructure.adapter.outbound.export.odt_diet_exporter_adapter import MIME, OdtDietExporterAdapter  # noqa: E402
from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import (  # noqa: E402
    LABEL_GAP, LOGO_BOX, LOGO_CLEARANCE, LOGO_TEAM_BOX, M_LEFT, M_RIGHT, PAGE_W, text_width_cm)
from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import PdfDietExporterAdapter  # noqa: E402

pytestmark = pytest.mark.infrastructure


def _proposal():
    from test_pdf_exporter import PROPOSAL          # the same fixture the PDF test uses
    return PROPOSAL


def _text(data: bytes) -> list[str]:
    content = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode("utf-8")
    body = content.split("<office:text>", 1)[1]
    out = []
    for m in re.finditer(r"<text:p[^>]*>(.*?)</text:p>", body, re.S):
        # A soft line break is where the writer would have wrapped anyway, so it reads as a space: the objective is
        # broken by hand because the logos are drawn over the text width and Writer will not flow around them.
        t = re.sub(r"<[^>]+>", "", m.group(1).replace("<text:line-break/>", " ")).strip()
        if t:
            out.append(t)
    return out


def test_it_is_a_valid_opendocument_container():
    data = OdtDietExporterAdapter("Marca", "correo demo | Tel: demo").export(_proposal(), client_name="Cliente Demo Ficticio")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None
    first = z.infolist()[0]
    # the specification requires the mimetype first and stored, so a reader can identify the file without inflating it
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert z.read("mimetype").decode() == MIME
    for name in ("content.xml", "styles.xml", "META-INF/manifest.xml"):
        ET.fromstring(z.read(name))
    assert any(n.startswith("Pictures/") for n in z.namelist())


def test_the_odt_says_exactly_what_the_pdf_says():
    proposal = _proposal()
    odt = OdtDietExporterAdapter("Marca", "correo demo | Tel: demo")
    pdf = PdfDietExporterAdapter("Marca", "correo demo | Tel: demo")
    printed = [l.text.strip() for l in pdf.document(proposal, "Cliente Demo Ficticio").lines if l.kind != "blank" and l.text.strip()]
    assert _text(odt.export(proposal, client_name="Cliente Demo Ficticio")) == printed


def test_his_typography_is_the_one_measured_in_his_originals():
    data = OdtDietExporterAdapter().export(_proposal(), client_name="Cliente Demo Ficticio")
    styles = zipfile.ZipFile(io.BytesIO(data)).read("styles.xml").decode("utf-8")
    content = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode("utf-8")
    assert 'fo:margin-top="1.783cm"' in styles and 'fo:margin-bottom="2.549cm"' in styles
    assert 'fo:font-size="11pt"' in styles                      # the body size of his documents
    assert 'fo:font-size="15.5pt"' in content                   # the title
    assert 'fo:margin-top="0cm" fo:margin-bottom="0cm"' in content   # no paragraph spacing: his air is empty paragraphs


# The limit is derived HERE from the logo boxes instead of read from the exporter's own constant. Sharing the constant
# would make the assertion move with the code: blanking the fit would move the limit too and every case would still pass.
_FULL_WIDTH = PAGE_W - M_LEFT - M_RIGHT
_PAGE_CENTRE = M_LEFT + _FULL_WIDTH / 2
_BESIDE_LOGOS = 2 * min(_PAGE_CENTRE - (LOGO_BOX[0] + LOGO_BOX[2] + LOGO_CLEARANCE),
                        (LOGO_TEAM_BOX[0] - LOGO_CLEARANCE) - _PAGE_CENTRE)


def _objective(data: bytes) -> tuple[float, list[str]]:
    """The size the objective was set at and the lines it was broken into."""
    content = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode("utf-8")
    size = float(re.search(r'style:name="P_objetivo".*?fo:font-size="([\d.]+)pt"', content, re.S).group(1))
    para = re.search(r'<text:p text:style-name="P_objetivo">(.*?)</text:p>', content, re.S).group(1)
    return size, [re.sub(r"<[^>]+>", "", c).strip() for c in para.split("<text:line-break/>")]


@pytest.mark.parametrize("goal_text", sorted(set(GOAL_TEXT.values())))
def test_the_objective_never_runs_over_the_logos(goal_text):
    """His logos are `wrap="run-through"` frames: Writer lays text UNDER them instead of flowing around, so an objective
    wider than the gap between them is printed across the brand. Three of the nine goal texts are, and the fasting one
    measures 26,6 cm on a 21 cm sheet. Reported by the professional on a PDF of his own; the .odt is the
    same document and had the same defect."""
    data = OdtDietExporterAdapter(contact="correo demo | Tel: demo").export(
        _proposal(), client_name="Nora Ficticia Demo", goal_text=goal_text)
    size, chunks = _objective(data)
    assert size >= O.PARA_STYLES["item"][1], "the objective came out smaller than the body it introduces"
    for i, chunk in enumerate(chunks):
        label, _, rest = chunk.partition(":")
        width = text_width_cm(label + ":", size, True) + LABEL_GAP + text_width_cm(rest.strip(), size, False) if i == 0             else text_width_cm(chunk, size, False)
        limit = _BESIDE_LOGOS if i == 0 else _FULL_WIDTH
        assert width <= limit + 1e-6, f"line {i} is {width:.3f} cm, over the {limit:.3f} cm it may use"


def test_both_formats_break_the_objective_in_the_same_place():
    """They render the same `DietDocument`; a fit decided separately in each would give him two different documents."""
    from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import (
        CENTRED_MIN_PT, fit_centred_label)
    for goal_text in sorted(set(GOAL_TEXT.values())):
        odt_size, odt_chunks = _objective(OdtDietExporterAdapter().export(
            _proposal(), client_name="Nora Ficticia Demo", goal_text=goal_text))
        pdf_size, pdf_chunks = fit_centred_label(
            "Objetivo:", goal_text, O.OBJECTIVE_PT, _BESIDE_LOGOS, _FULL_WIDTH,
            text_width_cm, floor=max(CENTRED_MIN_PT, O.OBJECTIVE_PT - 1.0))
        assert (odt_size, len(odt_chunks)) == (pdf_size, len(pdf_chunks)), goal_text


def test_a_long_client_name_shrinks_the_title_in_the_odt_too():
    """The client's name is free text. The title cannot be broken —his is one line— so shrinking is the only tool it has,
    and for a name this long it does go under the body size. That is a degradation; printing it over the brand is a defect."""
    data = OdtDietExporterAdapter().export(
        _proposal(), client_name="Nora Ficticia Demo Con Un Nombre Larguisimo De Prueba")
    content = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode("utf-8")
    title_pt = float(re.search(r'style:name="P_header".*?fo:font-size="([\d.]+)pt"', content, re.S).group(1))
    date_pt = float(re.search(r'style:name="T_date".*?fo:font-size="([\d.]+)pt"', content, re.S).group(1))
    assert title_pt < 15.5, "the title kept his size and is laid out across the logos"
    para = re.search(r'<text:p text:style-name="P_header">(.*?)</text:p>', content, re.S).group(1)
    date = re.search(r'<text:span text:style-name="T_date">(.*?)</text:span>', para, re.S)
    name = re.sub(r"<text:span.*?</text:span>", "", para, flags=re.S)
    width = text_width_cm(re.sub(r"<[^>]+>", "", name), title_pt, True)
    if date:                                                   # the date is set smaller, on the name's baseline
        width += text_width_cm(re.sub(r"<[^>]+>", "", date.group(1)), date_pt, True)
    assert width <= _BESIDE_LOGOS + 1e-6, f"{width:.3f} cm over the {_BESIDE_LOGOS:.3f} cm it may use"
