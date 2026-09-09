# -*- coding: utf-8 -*-
"""The canonical notes must stay consistent with the constitution they claim to serve.

A theme declares, in `rule_ids`, which note-level rules of the professional's constitution its canonical wording makes
evaluable. If the wording does not actually satisfy that rule's pattern, the composer emits a note that says the right thing
and the rule engine still scores it as absent — which is exactly what happened: the most frequent hydration wording was
«HAY QUE BEBER AUNQUE NO SE TENGA SED, PERO A TRAGOS PEQUEÑOS», which carries the instruction but does not match
«beber agua|litros de agua», and `agua_2.5L` fell to 0,019 against the professional's 0,787. This test is the guard.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "pipeline" / "src"))
from finalprosports.domain.composition.policy.note_catalogue import NoteCatalogue  # noqa: E402
from finalprosports.domain.composition.policy.rule_engine import NOTE_PATTERNS  # noqa: E402
from finalprosports.infrastructure.config.paths import dataset_dir  # noqa: E402

CATALOGUE = dataset_dir() / "canonical_notes.json"
THEMES = Path(__file__).resolve().parents[3] / "pipeline" / "src" / "pipeline" / "data" / "note_themes.json"


def _catalogue() -> dict | None:
    return json.loads(CATALOGUE.read_text(encoding="utf-8")) if CATALOGUE.exists() else None


def test_every_canonical_note_satisfies_the_rules_it_claims():
    d = _catalogue()
    if d is None:
        return                                        # the catalogue is a dataset artefact: absent in a bare checkout
    broken = []
    for t in d["themes"]:
        for rid in t.get("rule_ids", ()):
            pat = NOTE_PATTERNS.get(rid)
            if pat is not None and not pat.search(t["canonical"]):
                broken.append((t["id"], rid, t["canonical"][:60]))
    assert not broken, f"canonical wordings that do not satisfy the rule they claim: {broken}"


def test_no_canonical_note_is_an_artefact():
    d = _catalogue()
    if d is None:
        return
    cat = NoteCatalogue.from_dict(d)
    bad = [t["id"] for t in d["themes"] if cat.is_artefact(t["canonical"])]
    assert not bad, f"a section header or footer fragment became a canonical note: {bad}"


def test_the_themes_criterion_and_the_built_catalogue_agree():
    d = _catalogue()
    if d is None:
        return
    criterion = {t["id"] for t in json.loads(THEMES.read_text(encoding="utf-8"))["themes"]}
    built = {t["id"] for t in d["themes"]}
    assert built <= criterion, f"the catalogue carries themes that are not in the versioned criterion: {built - criterion}"


def test_a_theme_recognises_the_wordings_it_is_for():
    d = _catalogue()
    if d is None:
        return
    cat = NoteCatalogue.from_dict(d)
    assert "hidratacion" in cat.themes_in("Beber 2,5 litros de Agua al día a tragos pequeños")
    assert "hidratacion" in cat.themes_in("CONTROLAR LA INGESTA DE AGUA: 3 LITROS")
    assert cat.is_artefact("Observaciones:") and cat.is_artefact("tel") and not cat.is_artefact("Dormir de 7 a 8 horas.")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    sys.exit(1 if failed else 0)
