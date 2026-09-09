# -*- coding: utf-8 -*-
"""DietExporterOutputPort in OpenDocument Text — the format the professional actually writes in.

The PDF is what he hands to the client; the .odt is what he can still edit. His own diets are .odt files written in
LibreOffice Writer, so exporting one gives him back a document he can open, adjust and re-save, which is what he does today
with the previous version of every client.

The layout is the same `DietDocument` the PDF renders, and the styles are the ones measured in his originals (see
la memoria (plantilla del documento del profesional)): A4 with margins 1,783 / 2,549 cm, TimesNewRomanPSMT 11 pt, **no paragraph spacing** —
his automatic styles are declared without a parent and inherit the default, which has no margins — blank paragraphs between
blocks, the title at 15,5 pt bold with the date at 10 pt, «Objetivo:» centred at 12 pt, slot labels and «Notas:» bold, the
two logos anchored to the top corners and the light banner above the contact line.

An .odt is a ZIP with a fixed shape, so it is written with `zipfile` from the standard library: no new dependency, and the
mimetype entry goes first and uncompressed as the specification requires.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from finalprosports.domain.composition.policy.document_template_policy import DietDocument, render_document
from finalprosports.domain.model import DietProposal
from finalprosports.infrastructure.adapter.outbound.export.pdf_diet_exporter_adapter import (
    DATE_RE, LOGO, LOGO_CLEARANCE, LOGO_LIGHT, LOGO_TEAM, LOGO_BOX, LOGO_TEAM_BOX, LINK_COLOUR,
    M_LEFT, M_RIGHT, PAGE_W, TITLE_DATE_PT, TITLE_PT, fit_centred_label, fit_title, text_width_cm,
)

MIME = "application/vnd.oasis.opendocument.text"
FONT = "TimesNewRomanPSMT"
OBJECTIVE_PT = 12.0

# The two corner logos are `wrap="run-through"` frames, exactly as in his .odt: the text does not flow around them, it
# passes UNDER them. So the writer will happily lay the objective across the brand, and the exporter has to keep the
# header narrow enough itself — the same job the PDF does, decided by the same function so the two files break his
# objective in the same place.
#
# The difference is where the line is centred. The PDF centres it inside the gap; a word processor centres the whole
# paragraph on the text width, so what a centred line may measure is twice the SHORTER distance from the middle of the
# page to a logo. The logos are not quite symmetric (0,027 cm apart), and this takes the tighter of the two.
_TEXT_WIDTH = PAGE_W - M_LEFT - M_RIGHT
_CENTRE = M_LEFT + _TEXT_WIDTH / 2
CENTRED_WIDTH_BESIDE_LOGOS = 2 * min(_CENTRE - (LOGO_BOX[0] + LOGO_BOX[2] + LOGO_CLEARANCE),
                                     (LOGO_TEAM_BOX[0] - LOGO_CLEARANCE) - _CENTRE)

STYLES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
 xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" office:version="1.3">
 <office:font-face-decls>
  <style:font-face style:name="{font}" svg:font-family="&apos;Times New Roman&apos;" style:font-family-generic="roman"/>
 </office:font-face-decls>
 <office:styles>
  <style:default-style style:family="paragraph">
   <style:text-properties style:font-name="{font}" fo:font-size="11pt"/>
  </style:default-style>
  <style:style style:name="Internet_20_link" style:display-name="Internet link" style:family="text">
   <style:text-properties fo:color="{link}" style:text-underline-style="solid" style:text-underline-width="auto"/>
  </style:style>
 </office:styles>
 <office:automatic-styles>
  <style:page-layout style:name="pm1">
   <style:page-layout-properties fo:page-width="21.001cm" fo:page-height="29.7cm" style:print-orientation="portrait"
    fo:margin-top="1.783cm" fo:margin-bottom="2.549cm" fo:margin-left="1.783cm" fo:margin-right="1.783cm"/>
  </style:page-layout>
 </office:automatic-styles>
 <office:master-styles>
  <style:master-page style:name="Standard" style:page-layout-name="pm1"/>
 </office:master-styles>
</office:document-styles>
"""

# One automatic style per kind of line, with the sizes and weights measured in his documents.
PARA_STYLES = {
    "header": ("center", 15.5, True),
    "objetivo": ("center", 12.0, False),
    "slot": ("start", 11.0, True),
    "notes_title": ("start", 11.0, True),
    "item": ("start", 11.0, False),
    "note": ("start", 11.0, False),
    "inline": ("start", 11.0, False),
    "training": ("start", 11.0, False),
    "blank": ("start", 11.0, False),
    "footer": ("start", 10.0, False),
    "logos": ("start", 11.0, False),
}


def _para_style_xml(objective_pt: float = OBJECTIVE_PT, title_pt: float = TITLE_PT, date_pt: float = TITLE_DATE_PT) -> str:
    """The sizes are his, except the two the header may have had to give up so it clears the logos (see `_header_fit`)."""
    out = []
    sizes = {"objetivo": objective_pt, "header": title_pt}
    for name, (align, size, bold) in PARA_STYLES.items():
        size = sizes.get(name, size)
        out.append(
            f'<style:style style:name="P_{name}" style:family="paragraph">'
            f'<style:paragraph-properties fo:text-align="{align}" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
            f'<style:text-properties style:font-name="{FONT}" fo:font-size="{size}pt"'
            f'{" fo:font-weight=\"bold\"" if bold else ""}/></style:style>')
    # the runs that differ inside a line: the date after the title, and the bold label of an inline line
    out.append(f'<style:style style:name="T_date" style:family="text">'
               f'<style:text-properties style:font-name="{FONT}" fo:font-size="{date_pt}pt" fo:font-weight="bold"/></style:style>')
    out.append(f'<style:style style:name="T_label" style:family="text">'
               f'<style:text-properties style:font-name="{FONT}" fo:font-weight="bold"/></style:style>')
    out.append(f'<style:style style:name="T_value" style:family="text">'
               f'<style:text-properties style:font-name="{FONT}" fo:font-weight="normal"/></style:style>')
    return "".join(out)


def _frame(name: str, href: str, x: str, y: str, w: str, h: str, z: int) -> str:
    return (f'<draw:frame draw:style-name="fr1" draw:name="{name}" text:anchor-type="char" svg:x="{x}" svg:y="{y}" '
            f'svg:width="{w}" svg:height="{h}" draw:z-index="{z}">'
            f'<draw:image xlink:href="{href}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame>')


class OdtDietExporterAdapter:
    """Same contract as the PDF adapter, same document, other container."""

    fmt = "odt"
    media_type = MIME
    extension = "odt"

    def __init__(self, brand: str = "Final Pro Sports", contact: str = "", logo: Path | None = LOGO,
                 secondary_logo: Path | None = None, light_logo: Path | None = LOGO_LIGHT):
        self._brand, self._contact = brand, contact
        self._logo, self._secondary, self._light = logo, secondary_logo or LOGO_TEAM, light_logo

    def document(self, proposal: DietProposal, client_name: str | None = None, today: date | None = None,
                 goal_text: str | None = None) -> DietDocument:
        contact = tuple(c.strip() for c in self._contact.split("|") if c.strip())
        return render_document(proposal, client_name, today or date.today(), contact, goal_text)

    def export(self, proposal: DietProposal, diet_id: str = "", strategy_label: str | None = None, lab_results=(),
               client_name: str | None = None, goal_text: str | None = None) -> bytes:
        """`lab_results` and `strategy_label` are accepted and deliberately NOT rendered: the delivered document is his."""
        doc = self.document(proposal, client_name, goal_text=goal_text)
        images: dict[str, bytes] = {}
        for key, path in (("logo", self._logo), ("team", self._secondary), ("light", self._light)):
            if path and Path(path).exists():
                images[f"Pictures/{key}{Path(path).suffix}"] = Path(path).read_bytes()
        body = self._body(doc, images)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            # the specification requires the mimetype first and stored, so a reader can sniff it without inflating
            z.writestr(zipfile.ZipInfo("mimetype"), MIME, compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/manifest.xml", self._manifest(images))
            z.writestr("styles.xml", STYLES_XML.format(font=FONT, link=LINK_COLOUR))
            z.writestr("content.xml", body)
            for name, data in images.items():
                z.writestr(name, data)
        return buf.getvalue()

    # ------------------------------------------------------------------------------------------------------------ xml
    @staticmethod
    def _manifest(images: dict[str, bytes]) -> str:
        rows = "".join(
            f'<manifest:file-entry manifest:full-path="{n}" manifest:media-type="image/'
            f'{"png" if n.endswith(".png") else "jpeg"}"/>' for n in images)
        return ('<?xml version="1.0" encoding="UTF-8"?>'
                '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
                f'<manifest:file-entry manifest:full-path="/" manifest:media-type="{MIME}"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
                '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
                f'{rows}</manifest:manifest>')

    @staticmethod
    def _header_fit(doc: DietDocument) -> tuple[float, list[str], float, float]:
        """The objective's size and lines, and the title's two sizes, so neither runs over a corner logo.

        `LABEL_GAP` is the 0,18 cm the PDF leaves after a bold label, while the .odt separates them with a plain space
        (~0,11 cm at 12 pt). Measuring with the wider of the two only ever makes this file give way sooner than it had
        to, never later, so the mismatch is left alone rather than paid for with a second measurement path."""
        width = CENTRED_WIDTH_BESIDE_LOGOS
        objective = next((l for l in doc.lines if l.kind == "objetivo"), None)
        size, chunks = OBJECTIVE_PT, []
        if objective is not None:
            label, sep, rest = objective.text.partition(":")
            if sep:
                size, chunks = fit_centred_label(label + sep, rest.strip(), OBJECTIVE_PT, width, _TEXT_WIDTH,
                                                 text_width_cm, floor=PARA_STYLES["item"][1])
        header = next((l for l in doc.lines if l.kind == "header"), None)
        title_pt, date_pt = TITLE_PT, TITLE_DATE_PT
        if header is not None:
            m = DATE_RE.search(header.text)
            name, when = (header.text[: m.start()], m.group(1)) if m else (header.text, "")
            title_pt, date_pt = fit_title(name, when, width, text_width_cm)
        return size, chunks, title_pt, date_pt

    def _body(self, doc: DietDocument, images: dict[str, bytes]) -> str:
        objective_pt, objective_lines, title_pt, date_pt = self._header_fit(doc)
        paras: list[str] = []
        logo = next((n for n in images if n.startswith("Pictures/logo")), None)
        team = next((n for n in images if n.startswith("Pictures/team")), None)
        light = next((n for n in images if n.startswith("Pictures/light")), None)
        frames = ""
        if logo:
            frames += _frame("Marca", logo, "0.222cm", "0.067cm", "2.36cm", "1.328cm", 1)
        if team:
            frames += _frame("Equipo", team, "14.905cm", "0.074cm", "2.468cm", "1.388cm", 0)
        paras.append(f'<text:p text:style-name="P_logos">{frames}</text:p>')

        for line in doc.lines:
            kind, text = line.kind, line.text
            if kind == "blank":
                paras.append('<text:p text:style-name="P_blank"/>')
            elif kind == "header":
                m = DATE_RE.search(text)
                name, when = (text[: m.start()], m.group(1)) if m else (text, "")
                run = escape(name) + (f'<text:span text:style-name="T_date">  {escape(when)}</text:span>' if when else "")
                paras.append(f'<text:p text:style-name="P_header">{run}</text:p>')
            elif kind == "objetivo":
                label, sep, rest = text.partition(":")
                if sep:
                    value = "<text:line-break/>".join(
                        f'<text:span text:style-name="T_value">{escape((" " if i == 0 else "") + chunk)}</text:span>'
                        for i, chunk in enumerate(objective_lines or [rest.strip()]))
                    run = f'<text:span text:style-name="T_label">{escape(label + sep)}</text:span>{value}'
                else:
                    run = escape(text)
                paras.append(f'<text:p text:style-name="P_objetivo">{run}</text:p>')
            elif kind in ("inline", "training"):
                label, sep, rest = text.partition(":")
                run = (f'<text:span text:style-name="T_label">{escape(label + sep)}</text:span>'
                       f'<text:span text:style-name="T_value">{escape(" " + rest.strip())}</text:span>') if sep else escape(text)
                paras.append(f'<text:p text:style-name="P_{kind}">{run}</text:p>')
            elif kind == "footer":
                if light:
                    paras.append(f'<text:p text:style-name="P_logos">'
                                 f'<draw:frame draw:style-name="fr2" draw:name="Banner" text:anchor-type="as-char" '
                                 f'svg:width="3.522cm" svg:height="1.076cm" draw:z-index="2">'
                                 f'<draw:image xlink:href="{light}" xlink:type="simple" xlink:show="embed" '
                                 f'xlink:actuate="onLoad"/></draw:frame></text:p>')
                mail, _, rest = text.partition(" ")
                run = (f'<text:a xlink:type="simple" xlink:href="mailto:{escape(mail)}" text:style-name="Internet_20_link">'
                       f'{escape(mail)}</text:a>{escape(" " + rest)}') if "@" in mail else escape(text)
                paras.append(f'<text:p text:style-name="P_footer">{run}</text:p>')
            else:
                paras.append(f'<text:p text:style-name="P_{kind}">{escape(text)}</text:p>')

        return ('<?xml version="1.0" encoding="UTF-8"?>'
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
                ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
                ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
                ' xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"'
                ' xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"'
                ' xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"'
                ' xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.3">'
                '<office:automatic-styles>'
                + _para_style_xml(objective_pt, title_pt, date_pt) +
                '<style:style style:name="fr1" style:family="graphic">'
                '<style:graphic-properties style:wrap="run-through" style:vertical-rel="paragraph" style:horizontal-rel="paragraph"/>'
                '</style:style>'
                '<style:style style:name="fr2" style:family="graphic">'
                '<style:graphic-properties style:vertical-rel="baseline"/></style:style>'
                '</office:automatic-styles>'
                '<office:body><office:text>' + "".join(paras) + '</office:text></office:body></office:document-content>')
