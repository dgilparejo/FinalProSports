"""DietExporterOutputPort (S6): the PDF the professional hands to the client, laid out as HIS document.

The TEXT comes from the domain policy (document_template_policy); this adapter reproduces the LAYOUT observed in two of his original
documents of 2026 (custody, not versioned; contrast in la memoria (plantilla del documento del profesional) §«Maquetación visual observada»):

  * A4 portrait, margins 1.783 cm (top / left / right) and 2.549 cm (bottom); one column; no page header or footer.
  * Times New Roman (his «TimesNewRomanPSMT»; Liberation Serif / DejaVu Serif as fallbacks), 11 pt body; paragraph spacing 0.423 cm before
    and 0.212 cm after, line height 115 %.
  * First paragraph: two small logos anchored at the top corners (2.36 × 1.33 cm left: the brand; 2.47 × 1.39 cm right: a secondary logo
    when configured). Then the title centred: «DIETA <nombre>» 15.5 pt bold + the date 10 pt bold; «Objetivo:» 12 pt (label bold) centred.
  * Slot labels bold 11 pt in upper case; items 11 pt regular, one line each; a line that does not fit is set in 9 pt (he shrinks, he does
    not wrap) and wrapped only if it still overflows; the inline lines («Recién levantado…», training) have their label in bold.
  * «Notas:» regular, notes as plain sentences; then a blank paragraph and the contact line preceded by the light brand banner (3.52 × 1.08 cm).
  * Nothing else, at all. The exported PDF is HIS document: no annex, no lab results, no validator or plausibility notes. He does not
    put an analysis inside a diet, so neither do we. What the professional needs to see about the engine — forced changes,
    plausibility adjustments, lab context — lives on the proposal screen of the application, not in the document handed to the client.

Rendering with matplotlib's PDF backend (no new dependency). Text widths are measured with the Agg renderer to centre, to place the bold label
of an inline line and to decide the 9 pt shrink."""
from __future__ import annotations

import io
import re
import textwrap
from datetime import date
from pathlib import Path

from finalprosports.domain.composition.policy.document_template_policy import DietDocument, render_document
from finalprosports.domain.model import DietProposal

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "logo.jpg"                  # brand, white on black (top-left of his document)
LOGO_LIGHT = ASSETS / "logo_light.jpg"      # brand, black on white (inline banner before the contact line)
LOGO_TEAM = ASSETS / "logo_team.png"        # the team badge, white on black (top-RIGHT of his document)
FAMILY_PREFERENCE = ("Times New Roman", "Liberation Serif", "DejaVu Serif")
LINK_COLOUR = "#000080"                     # his e-mail is a hyperlink in the .odt: navy, underlined


def _resolve_family() -> list[str]:
    """First available serif of his preference; resolved once so matplotlib does not warn on every text (DejaVu Serif always ships with it)."""
    try:
        from matplotlib import font_manager
        names = {f.name for f in font_manager.fontManager.ttflist}
        return [next((n for n in FAMILY_PREFERENCE if n in names), "DejaVu Serif")]
    except Exception:                                      # noqa: BLE001
        return ["DejaVu Serif"]


FAMILY = _resolve_family()
CM = 1 / 2.54
PAGE_W, PAGE_H = 21.0, 29.7                 # cm
M_TOP, M_BOTTOM, M_LEFT, M_RIGHT = 1.783, 2.549, 1.783, 1.783
SPACE_BEFORE, SPACE_AFTER, LINE_HEIGHT = 0.0, 0.0, 1.15
"""No paragraph spacing, because his document has none.

The 0,423 / 0,212 cm this used to carry are the margins of the `Standard` style of his .odt — and not one paragraph in the
document uses `Standard`: every automatic style is declared without a parent, so they all inherit the default paragraph style,
which has no margins at all. Reading the named style instead of the one in use made every exported diet a third taller than
his and pushed it onto a second sheet. He separates his blocks with EMPTY PARAGRAPHS, which the template now emits as `blank`
lines, and that is what the air in his document is made of."""
PT = 2.54 / 72                              # cm per point
DATE_RE = re.compile(r"\s+(\d{2} / \d{2} / \d{2})$")
TITLE_PT, TITLE_DATE_PT = 15.5, 10.0        # his centred title and the date that shares its baseline
LABEL_GAP = 0.18                            # the space after a bold label, measured in his .odt
CENTRED_MIN_PT = 9.0                        # a centred header line shrinks no further, like every other line of the document

# The two corner logos are drawn ON the text area of the first page, so a centred line at their height may only use the
# GAP BETWEEN THEM (12,32 cm), not the 17,43 cm of the text width. Held as constants because `first_page_logos` and
# `_Page._free_span` have to agree on where they are: when they did not, the objective was laid out across them.
LOGO_BOX = (M_LEFT + 0.222, M_TOP + 0.067, 2.36, 1.328)              # brand, top-left
LOGO_TEAM_BOX = (M_LEFT + 14.905, M_TOP + 0.074, 2.468, 1.388)       # team badge, top-right
# Both logos are solid black blocks, so a line that merely does not overlap one still reads as stuck to it: this much
# white is kept between them. It is the difference between the objective ending 0,41 cm from the badge and 0,25 cm of
# clear paper on each side at one type size less.
LOGO_CLEARANCE = 0.25

# His diet is ONE sheet, and his layout has no paragraph spacing to give: the only thing that can yield when a proposal runs
# longer than his did is the body size. Each rung keeps the type styles intact — Times, bold labels, the 15.5 pt title, the
# blank paragraphs between blocks — and 9 pt is the floor, which is already the size he drops to for a line that will not fit.
FIT_LADDER = ((0.0, 0.0, 11.0), (0.0, 0.0, 10.5), (0.0, 0.0, 10.0), (0.0, 0.0, 9.5), (0.0, 0.0, 9.0))


def _line_cm(size_pt: float) -> float:
    return size_pt * PT * LINE_HEIGHT


_MEASURE_FIG = None


def text_width_cm(text: str, size: float, bold: bool = False) -> float:
    """Width of a run of his type, in cm, measured with the same font resolution the PDF lays out with.

    It exists so the .odt can ask the question too: both exporters render the SAME document, and a fit decided with
    different metrics in each would break his objective in a different place in each file."""
    global _MEASURE_FIG                                    # noqa: PLW0603 — one throw-away figure reused, not per call
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if _MEASURE_FIG is None:
        _MEASURE_FIG = plt.figure(figsize=(PAGE_W * CM, PAGE_H * CM), dpi=100)
        _MEASURE_FIG.add_axes([0, 0, 1, 1]).axis("off")
    ax = _MEASURE_FIG.axes[0]
    t = ax.text(0, 0, text, fontsize=size, fontweight="bold" if bold else "normal", family=FAMILY, transform=ax.transAxes)
    width = t.get_window_extent(renderer=_MEASURE_FIG.canvas.get_renderer()).width
    t.remove()
    return width / _MEASURE_FIG.dpi * 2.54


def fit_centred_label(label: str, rest: str, size: float, first_width: float, other_width: float, measure,
                      floor: float = CENTRED_MIN_PT) -> tuple[float, list[str]]:
    """The type size and the lines a centred «Etiqueta: texto» needs so it never runs over a corner logo.

    `first_width` is what the line may use while it runs alongside the logos; `other_width` what it gets once it has
    cleared them. It shrinks first, which is what he does with a line that will not fit, down to `floor`. Wrapping is
    the last resort and goes back to his size: shrinking buys nothing once the line is broken anyway.

    The caller puts the floor at the BODY size, so the objective is never set smaller than the diet it introduces: the
    keto text needs 10 pt to hold one line under an 11 pt body, and a heading below its own body reads as a mistake.
    It wraps at his 12 pt instead.

    Shared by the two exporters on purpose. Three of the nine goal texts are wider than the gap between the logos at
    12 pt and the fasting one —135 characters— measures 26,6 cm on a 21 cm sheet."""
    requested = size
    while True:
        if measure(label, size, True) + LABEL_GAP + measure(rest, size, False) <= first_width:
            return size, [rest]
        if size <= floor:
            break
        size = round(size - 0.5, 1)
    size, words, lines = requested, rest.split(), []
    while words:
        available = (first_width - measure(label, size, True) - LABEL_GAP) if not lines else other_width
        take = len(words)
        while take > 1 and measure(" ".join(words[:take]), size, False) > available:
            take -= 1
        lines.append(" ".join(words[:take]))
        words = words[take:]
    return size, lines


def fit_title(name: str, when: str, width: float, measure) -> tuple[float, float]:
    """The size of «DIETA <nombre>» and of the date sharing its baseline, shrunk together so a long name —it is free
    text— is not laid out across the brand. The title is never broken: his is one line."""
    size, date_size = TITLE_PT, TITLE_DATE_PT
    while size > CENTRED_MIN_PT:
        if measure(name, size, True) + (measure("  " + when, date_size, True) if when else 0.0) <= width:
            break
        size, date_size = round(size - 0.5, 1), round(date_size * (size - 0.5) / size, 2)
    return size, date_size


class PdfDietExporterAdapter:
    def __init__(self, brand: str = "Final Pro Sports", contact: str = "", logo: Path | None = LOGO, secondary_logo: Path | None = None,
                 light_logo: Path | None = LOGO_LIGHT):
        # His document carries THREE images and always the same three: the brand top-left, the team badge top-right and the
        # light brand banner beside the contact line. The second one used to be optional configuration and was therefore
        # missing from every PDF; it is bundled now and configuration only overrides it.
        secondary_logo = secondary_logo or LOGO_TEAM
        self._brand, self._contact, self._logo, self._secondary, self._light = brand, contact, logo, secondary_logo, light_logo

    def document(self, proposal: DietProposal, client_name: str | None = None, today: date | None = None, goal_text: str | None = None) -> DietDocument:
        contact = tuple(c.strip() for c in self._contact.split("|") if c.strip())
        return render_document(proposal, client_name, today or date.today(), contact, goal_text)

    # ------------------------------------------------------------------------------------------------------------------ export
    def export(self, proposal: DietProposal, diet_id: str = "", strategy_label: str | None = None, lab_results=(), client_name: str | None = None,
               goal_text: str | None = None) -> bytes:
        """``lab_results`` and ``strategy_label`` are accepted and deliberately NOT rendered: the delivered document is his."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages

        buf = io.BytesIO()
        with PdfPages(buf) as pdf:
            self._render(proposal, diet_id, strategy_label, lab_results, client_name, goal_text, plt, pdf)
        return buf.getvalue()

    def export_previews(self, proposal: DietProposal, diet_id: str = "", strategy_label: str | None = None, lab_results=(), client_name: str | None = None,
                        goal_text: str | None = None, dpi: int = 110) -> list[bytes]:
        """The same pages as PNG (documentation and visual comparison with the professional's originals; no PDF renderer needed)."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        class _PngSink:
            def __init__(self): self.pages: list[bytes] = []
            def savefig(self, fig):
                b = io.BytesIO(); fig.savefig(b, format="png", dpi=dpi); self.pages.append(b.getvalue())

        sink = _PngSink()
        self._render(proposal, diet_id, strategy_label, lab_results, client_name, goal_text, plt, sink, dpi)
        return sink.pages

    def _render(self, proposal, diet_id, strategy_label, lab_results, client_name, goal_text, plt, pdf, dpi: int = 100) -> None:
        doc = self.document(proposal, client_name, goal_text=goal_text)
        images = {k: self._read(p, plt) for k, p in (("logo", self._logo), ("secondary", self._secondary), ("light", self._light))}
        before, after, body = self._fit(doc, plt, images, dpi)
        page = _Page(plt, images, dpi=dpi, before=before, after=after, body=body)
        self._lay_out(doc, page, pdf)
        page.flush(pdf)

    def _fit(self, doc: DietDocument, plt, images: dict, dpi: int) -> tuple[float, float, float]:
        """The tightest rung of the ladder that still fits on ONE sheet — his diet is one sheet.

        The document is laid out with drawing switched off, which costs one throw-away figure per rung and keeps the decision
        out of the drawing code. If no rung fits (a proposal with far more lines than he ever writes), the loosest is used and
        the layout falls back to several pages rather than to unreadable type."""
        for before, after, body in FIT_LADDER:
            page = _Page(plt, images, dpi=dpi, before=before, after=after, body=body, measure=True)
            page.first_page_logos()
            page.y = M_TOP + (before + _line_cm(12) + after)
            self._lay_out(doc, page, None)
            fits = page.fits_one_sheet
            page.flush(None)
            if fits:
                return before, after, body
        return FIT_LADDER[-1]

    @staticmethod
    def _lay_out(doc: DietDocument, page: "_Page", pdf) -> None:
        page.first_page_logos()
        page.y = M_TOP + (page.before + _line_cm(12) + page.after)                 # the empty first paragraph that anchors the logos
        body = page.body
        for line in doc.lines:
            if line.kind == "blank":
                page.blank_line(body)
            elif line.kind == "header":
                page.title(line.text)
            elif line.kind == "objetivo":
                page.centred_label_line(line.text, body + 1)
                page.blank_line(body)                                               # his blank paragraph after the objective
            elif line.kind in ("inline", "training"):
                page.label_line(line.text, body, pdf)
            elif line.kind == "slot":
                page.text_line(line.text, body, bold=True, pdf=pdf)
            elif line.kind == "item":
                page.shrinking_line(line.text, pdf, size=body)
            elif line.kind == "notes_title":
                page.text_line(line.text, body, bold=True, pdf=pdf)                 # his «Notas:» carries the same bold style as a slot label
            elif line.kind == "note":
                page.shrinking_line(line.text, pdf, size=body, min_size=body)
            elif line.kind == "footer":
                page.blank_line(body)                                               # his blank paragraph before the banner
                page.contact_line(line.text, pdf)

    @staticmethod
    def _read(path: Path | None, plt):
        if path and Path(path).exists():
            try:
                return plt.imread(str(path))
            except Exception:                                  # noqa: BLE001 — a missing / unreadable logo must never block the export
                return None
        return None


class _Page:
    """One A4 page in cm from the top-left corner; y is the top of the next paragraph. Text widths measured with the Agg renderer."""

    def __init__(self, plt, images: dict, compact: bool = False, dpi: int = 100,
                 before: float = SPACE_BEFORE, after: float = SPACE_AFTER, body: float = 11.0, measure: bool = False):
        self._plt, self._images, self._compact, self._dpi = plt, images, compact, dpi
        self._body, self._measure, self._overflowed = body, measure, False
        self._logos = False                       # set by `first_page_logos`; narrows `_free_span` while a line runs alongside them
        self._before, self._after = (0.05, 0.05) if compact else (before, after)
        self.fig = plt.figure(figsize=(PAGE_W * CM, PAGE_H * CM), dpi=dpi)       # measured and rasterised at the same dpi (hinting)
        self.ax = self.fig.add_axes([0, 0, 1, 1]); self.ax.axis("off")
        self._renderer = self.fig.canvas.get_renderer()
        self.y = M_TOP
        self.width = PAGE_W - M_LEFT - M_RIGHT

    # geometry helpers ----------------------------------------------------------------------------------------------------------
    @property
    def before(self) -> float:
        return self._before

    @property
    def after(self) -> float:
        return self._after

    @property
    def body(self) -> float:
        return self._body

    def _fx(self, x_cm: float) -> float:
        return x_cm / PAGE_W

    def _fy(self, y_cm: float) -> float:
        return 1 - y_cm / PAGE_H

    def _text_width_cm(self, s: str, size: float, bold: bool) -> float:
        t = self.ax.text(0, 0, s, fontsize=size, fontweight="bold" if bold else "normal", family=FAMILY, transform=self.ax.transAxes)
        w = t.get_window_extent(renderer=self._renderer).width
        t.remove()
        return w / self.fig.dpi * 2.54

    def _ensure_room(self, needed_cm: float, pdf) -> None:
        if self.y + needed_cm > PAGE_H - M_BOTTOM:
            self._overflowed = True
            if self._measure:                                   # a measuring pass never breaks the page: it reports that it would
                return
            self.flush(pdf)
            self.__init__(self._plt, self._images, self._compact, self._dpi)
            self.y = M_TOP

    def flush(self, pdf) -> None:
        if self._measure:
            self._plt.close(self.fig); return
        pdf.savefig(self.fig); self._plt.close(self.fig)

    @property
    def fits_one_sheet(self) -> bool:
        return not self._overflowed and self.y <= PAGE_H - M_BOTTOM

    def _draw(self, x_cm: float, y_cm: float, s: str, size: float, bold: bool = False, colour: str = "#000000", ha: str = "left", va: str = "top",
              underline: bool = False) -> None:
        if self._measure:
            return
        t = self.ax.text(self._fx(x_cm), self._fy(y_cm), s, fontsize=size, fontweight="bold" if bold else "normal", family=FAMILY, color=colour,
                         transform=self.ax.transAxes, va=va, ha=ha)
        if underline:
            t.set_url(None)
            w = self._text_width_cm(s, size, bold)
            self.ax.plot([self._fx(x_cm), self._fx(x_cm + w)], [self._fy(y_cm + size * PT * 1.05)] * 2,
                         transform=self.ax.transAxes, color=colour, linewidth=0.6)

    # blocks ------------------------------------------------------------------------------------------------------------------------
    def first_page_logos(self) -> None:
        self._logos = True                                   # set even while measuring: the geometry must be the same in both passes
        logo, secondary = self._images.get("logo"), self._images.get("secondary")
        if logo is not None:
            self._image(logo, *LOGO_BOX)
        if secondary is not None:
            self._image(secondary, *LOGO_TEAM_BOX)

    def _free_span(self, y_top: float, y_bottom: float) -> tuple[float, float]:
        """The x-range a line may occupy at that height: the text width, minus whichever corner logo it runs alongside.

        Only the first page has logos, and only a line whose band overlaps theirs is narrowed; everything below them —and
        every page after the first— gets the full text width back."""
        left, right = M_LEFT, PAGE_W - M_RIGHT
        if not self._logos:
            return left, right
        for img, (x, y, w, h) in ((self._images.get("logo"), LOGO_BOX), (self._images.get("secondary"), LOGO_TEAM_BOX)):
            if img is None or y_top >= y + h or y_bottom <= y:
                continue
            if x < (M_LEFT + PAGE_W - M_RIGHT) / 2:
                left = max(left, x + w + LOGO_CLEARANCE)
            else:
                right = min(right, x - LOGO_CLEARANCE)
        return left, right

    def _image(self, img, x_cm: float, y_cm: float, w_cm: float, h_cm: float) -> None:
        if self._measure:
            return
        ax = self.fig.add_axes([self._fx(x_cm), self._fy(y_cm + h_cm), w_cm / PAGE_W, h_cm / PAGE_H])
        ax.imshow(img); ax.axis("off")

    def blank_line(self, size: float) -> None:
        """An empty paragraph, exactly as he types it: one line of body height and nothing on it."""
        self.y += _line_cm(size)

    def paragraph_gap(self, size: float) -> None:
        self.y += SPACE_BEFORE + _line_cm(size) + SPACE_AFTER

    def title(self, text: str) -> None:
        """«DIETA <nombre>  dd / mm / aa» centred, the date on the name's baseline.

        It sits between the two corner logos, and the name is free text: a long one used to be laid out across them. It
        shrinks —name and date together, so the baseline they share is kept— rather than running over the brand."""
        m = DATE_RE.search(text)
        name, when = (text[: m.start()], m.group(1)) if m else (text, "")
        self.y += SPACE_BEFORE
        left, right = self._free_span(self.y, self.y + _line_cm(TITLE_PT))
        size, date_size = fit_title(name, when, right - left, self._text_width_cm)
        w_name = self._text_width_cm(name, size, True)
        w_date = self._text_width_cm("  " + when, date_size, True) if when else 0.0
        x0 = left + (right - left - w_name - w_date) / 2
        base = self.y + size * PT * 0.95                                            # shared baseline for the name and the date
        self._draw(x0, base, name, size, bold=True, va="baseline")
        if when:
            self._draw(x0 + w_name, base, "  " + when, date_size, bold=True, va="baseline")
        self.y += _line_cm(TITLE_PT) + SPACE_AFTER                                  # the block keeps his height even if the type shrank

    def centred_label_line(self, text: str, size: float) -> None:
        """«Objetivo: …» centred, the label in bold.

        The line runs alongside the two corner logos, so its usable width is the gap between them, not the text width.
        Three of the nine goal texts are wider than that gap at 12 pt and the fasting one —135 characters— measured
        26,6 cm on a 21 cm sheet: it was laid out over both logos and off the paper on either side.

        It shrinks first, which is what he does with a line that will not fit, down to the same 9 pt floor as the rest of
        the document. Wrapping is the last resort, and when it has to wrap the type size goes back to his: shrinking buys
        nothing once the line is broken anyway. The second line clears the logos, so it gets the full width back."""
        label, _, rest = text.partition(":")
        label, rest = label + ":", rest.strip()
        self.y += SPACE_BEFORE
        alongside = self._free_span(self.y, self.y + _line_cm(size))
        cleared = self._free_span(self.y + _line_cm(size), self.y + 2 * _line_cm(size))
        size, chunks = fit_centred_label(label, rest, size, alongside[1] - alongside[0], cleared[1] - cleared[0],
                                         self._text_width_cm, floor=max(CENTRED_MIN_PT, size - 1.0))
        for i, chunk in enumerate(chunks):
            w_l = self._text_width_cm(label, size, True) + LABEL_GAP if i == 0 else 0.0
            w_r = self._text_width_cm(chunk, size, False)
            left, right = self._free_span(self.y, self.y + _line_cm(size))
            x0 = left + (right - left - w_l - w_r) / 2
            if i == 0:
                self._draw(x0, self.y, label, size, bold=True)
            self._draw(x0 + w_l, self.y, chunk, size)
            self.y += _line_cm(size)
        self.y += SPACE_AFTER

    def label_line(self, text: str, size: float, pdf) -> None:
        """«ETIQUETA: texto» with the label in bold; shrinks to 9 pt before wrapping, like his long lines."""
        label, sep, rest = text.partition(":")
        if not sep:
            self.text_line(text, size, False, pdf); return
        label += ":"
        # The label and its trailing space are MEASURED, not estimated: a fixed 0,18 cm allowance pushed
        # «MITAD DE ENTRENAMIENTO: Agua en cantidad …» over the text width by 0,02 cm and shrank to 9 pt a line his own
        # document sets at 11 pt.
        for s in (size, size - 1, 9):
            if self._text_width_cm(label + " ", s, True) + self._text_width_cm(rest.strip(), s, False) <= self.width:
                size = s; break
        else:
            size = 9
        w_l = self._text_width_cm(label + " ", size, True)
        chunks = self._wrap(rest.strip(), size, self.width - w_l) or [""]
        self._ensure_room(SPACE_BEFORE + _line_cm(size) * len(chunks) + SPACE_AFTER, pdf)
        self.y += SPACE_BEFORE
        self._draw(M_LEFT, self.y, label, size, bold=True)
        for k, chunk in enumerate(chunks):
            self._draw(M_LEFT + w_l, self.y + _line_cm(size) * k, chunk, size)
        self.y += _line_cm(size) * len(chunks) + SPACE_AFTER

    def text_line(self, text: str, size: float, bold: bool, pdf, colour: str = "#000000") -> None:
        chunks = self._wrap(text, size, self.width, bold) or [""]
        self._ensure_room(self._before + _line_cm(size) * len(chunks) + self._after, pdf)
        self.y += self._before
        for k, chunk in enumerate(chunks):
            self._draw(M_LEFT, self.y + _line_cm(size) * k, chunk, size, bold=bold, colour=colour)
        self.y += _line_cm(size) * len(chunks) + self._after

    def shrinking_line(self, text: str, pdf, size: float = 11, min_size: float = 9, bold: bool = False, colour: str = "#000000") -> None:
        use = size
        if self._text_width_cm(text, size, bold) > self.width and self._text_width_cm(text, min_size, bold) <= self.width:
            use = min_size
        self.text_line(text, use, bold, pdf, colour)

    def contact_line(self, text: str, pdf) -> None:
        """The banner on its own line and the contact BELOW it, which is how his document has it: two separate paragraphs,
        the image anchored as-char in the first and the text in the second. The e-mail is a hyperlink in the .odt, so it is
        navy and underlined; the rest of the line is plain."""
        light = self._images.get("light")
        w_img, h_img = (3.522, 1.076) if light is not None else (0.0, 0.0)
        size = 10
        self._ensure_room(h_img + _line_cm(size), pdf)
        if light is not None:
            self._image(light, M_LEFT, self.y, w_img, h_img)
            self.y += h_img
        mail, sep, rest = text.partition(" ")
        if "@" in mail:
            self._draw(M_LEFT, self.y, mail, size, colour=LINK_COLOUR, underline=True)
            self._draw(M_LEFT + self._text_width_cm(mail, size, False), self.y, sep + rest, size)
        else:
            self._draw(M_LEFT, self.y, text, size)
        self.y += _line_cm(size)

    def _wrap(self, text: str, size: float, width_cm: float, bold: bool = False) -> list[str]:
        if not text:
            return [""]
        if self._text_width_cm(text, size, bold) <= width_cm:
            return [text]
        per_char = self._text_width_cm(text, size, bold) / max(1, len(text))
        cols = max(20, int(width_cm / per_char))
        return textwrap.wrap(text, cols) or [text]
