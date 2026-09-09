# -*- coding: utf-8 -*-
"""The exported diet must be HIS document, and the layout constants are the ones measured in his .odt.

The originals live in the custody and are not versioned, so what is pinned here are the values read from their `styles.xml`
and `content.xml` (procedure and full table in la memoria (plantilla del documento del profesional)). The test exists because one
of them was wrong for a whole sprint: the paragraph spacing was taken from the `Standard` style, which NOT ONE paragraph of his
document uses — every automatic style is declared without a parent and inherits the default, which has no margins. The same
diet came out 50,8 cm tall against his 25,4 and spilled onto a second sheet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.infrastructure.adapter.outbound.export import pdf_diet_exporter_adapter as X  # noqa: E402


def test_page_geometry_is_the_one_of_his_document():
    assert (X.PAGE_W, X.PAGE_H) == (21.0, 29.7)
    assert (X.M_TOP, X.M_LEFT, X.M_RIGHT, X.M_BOTTOM) == (1.783, 1.783, 1.783, 2.549)


def test_his_layout_has_no_paragraph_spacing():
    """The correction of 2026-08-28. If this ever goes back above zero, every exported diet grows by ~0,6 cm per line."""
    assert X.SPACE_BEFORE == 0.0 and X.SPACE_AFTER == 0.0


def test_the_three_images_of_his_document_are_bundled():
    """Brand top-left, team badge top-right, light banner above the contact. The badge used to be optional configuration and
    was therefore missing from every PDF ever exported."""
    for asset in (X.LOGO, X.LOGO_TEAM, X.LOGO_LIGHT):
        assert Path(asset).exists(), asset
    exporter = X.PdfDietExporterAdapter()
    assert exporter._secondary == X.LOGO_TEAM                       # noqa: SLF001 — bundled by default, not by configuration


def test_the_fit_ladder_only_ever_gives_up_type_size():
    """His diet is one sheet. When a proposal runs longer, the body yields — never the spacing (there is none to give) and
    never below 9 pt, the size he himself drops to for a line that will not fit."""
    assert X.FIT_LADDER[0][2] == 11.0 and X.FIT_LADDER[-1][2] == 9.0
    assert all(before == 0.0 and after == 0.0 for before, after, _ in X.FIT_LADDER)
    sizes = [body for _, _, body in X.FIT_LADDER]
    assert sizes == sorted(sizes, reverse=True), sizes


def test_the_email_is_rendered_as_the_hyperlink_it_is_in_his_document():
    assert X.LINK_COLOUR == "#000080"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:300]}")
    sys.exit(1 if failed else 0)
