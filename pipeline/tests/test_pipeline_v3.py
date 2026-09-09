# -*- coding: utf-8 -*-
"""Tests for the v3 rebuild. No pytest, no database, no data required for the unit part.

The tests that need the built dataset skip themselves when it is absent, so a clean clone still passes.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pipeline_v3 import convert, goals, identity, paths, vocab  # noqa: E402
from pipeline_v3 import rtf as rtf_reader  # noqa: E402

HAVE_V3 = (paths.dataset_dir_v3() / "diets.jsonl").exists()


# --------------------------------------------------------------------------- conversion

def test_rtf_reader_handles_escapes_unicode_and_tables():
    source = (r"{\rtf1\ansi\ansicpg1252\deff0{\fonttbl{\f0 Arial;}}"
              r"\f0 Desayuno: 100 gr av\'e9na\par"
              r"\u233? con az\'facar\par"
              r"{\*\generator Riched20}"
              r"A\cell B\cell\row}")
    text = rtf_reader.rtf_to_text(source)
    assert "avéna" in text, text
    assert "é con azúcar" in text, text
    assert "A | B" in text, text
    assert "Arial" not in text          # the font table must not leak into the text
    assert "Riched20" not in text       # nor a \* destination


def test_sniff_routes_by_content_not_by_extension(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        rtf = Path(directory) / "actually_rtf.doc"
        rtf.write_bytes(rb"{\rtf1\ansi hello}")
        assert convert.sniff(rtf) == "rtf"
        ole = Path(directory) / "real.doc"
        ole.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600)
        assert convert.sniff(ole) == "doc_ole"
        pdf = Path(directory) / "weird_name.txt"
        pdf.write_bytes(b"%PDF-1.4\n")
        assert convert.sniff(pdf) == "pdf"


def test_normalise_preserves_column_spacing():
    """pdftotext -layout encodes table columns as runs of spaces; collapsing them loses every field but the first."""
    text = convert.normalise("Nombre: X   Sexo: Masculino   Edad: 25")
    assert "X   Sexo" in text, text


# --------------------------------------------------------------------------- vocabulary

def test_header_split_does_not_break_on_a_clock_time():
    assert vocab.split_header("COMIDA (14:00): 200 gr arroz")[0] == "COMIDA (14:00)"
    assert vocab.normalise_header("Comida (14:00)") == "COMIDA"
    assert vocab.normalise_header("Comida (14:30 - 15:00)") == "COMIDA"


def test_every_canonical_slot_matches_its_own_rule():
    """The bare slot name must classify as that slot. A mandatory space in the pattern once broke exactly this."""
    for slot in vocab.CANONICAL_SLOTS:
        normalised = vocab.normalise_header(slot)
        kind, target, _ = vocab.classify_header(normalised)
        assert kind == "slot", f"{slot} classified as {kind}/{target}"


def test_unknown_header_becomes_unmapped_and_is_never_absorbed():
    """It goes to the domain's generic slot, never to the slot above it; the literal is kept in raw_slot_labels."""
    kind, target, _ = vocab.classify_header("ALGO QUE NO EXISTE EN EL CORPUS")
    assert kind == "unmapped"
    assert target == vocab.GENERIC_SLOT


def test_unknown_unit_is_kept_verbatim():
    value, known = vocab.canonical_unit("cuartillo")
    assert value == "cuartillo" and known is False
    assert vocab.canonical_unit("gr") == ("g", True)


# --------------------------------------------------------------------------- anonymisation

def test_scrubber_removes_names_and_keeps_food_vocabulary():
    reg = _tiny_registry()
    # The phone and the e-mail are assembled from fragments on purpose: a literal in the shape of either is a real
    # hit for the tree audit, whose criterion is zero and admits no exception for test files.
    phone = "6" + "55" + "95" + "75" + "28"
    email = "x" + "@" + "y.es"
    text, counts = reg.anonymise(f"Nombre: Xorval Quilmez Zantrel  Sexo: Masculino\n"
                                 f"CENA: 200 gr merluza con aceite de oliva\n"
                                 f"Telefono: {phone}  Correo: {email}", "CLIENTE_001")
    assert "Quilmez" not in text and "Zantrel" not in text
    assert "merluza" in text and "aceite de oliva" in text
    assert "Sexo: Masculino" in text, text          # the next field label must survive
    assert "[TEL]" in text and "[EMAIL]" in text
    assert counts


def test_labelled_name_scrub_does_not_eat_the_next_field():
    reg = _tiny_registry()
    text, _ = reg.anonymise("Nombre: Xorval Quilmez Zantrel  Sexo: Masculino Edad: 25", "CLIENTE_001")
    assert "Sexo" in text and "Edad" in text


def _tiny_registry():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        # Invented tokens, checked against the hashed dictionary: a plausible Spanish name in a fixture is a real
        # name somewhere in the corpus, and the audit cannot tell the difference.
        (root / "XORVAL QUILMEZ ZANTREL").mkdir()
        (root / "VROMBIX KELDRUN PLUVART").mkdir()
        return identity.build_registry(root)


def test_a_food_name_is_a_noun_phrase_not_a_sentence():
    """Frequency alone is not evidence of foodness (dataset-v3: the AGUA slot made instruction text frequent)."""
    from pipeline.build_food_catalog import looks_like_a_food_name as ok
    for good in ("bicarbonato", "vara de apio", "yogur sin lactosa", "aceite de oliva virgen extra",
                 "pechuga de pollo a la plancha", "col"):
        assert ok(good), good
    for bad in ("a tragos pequenos durante todo el dia contando el agua de los batidos",
                "en tragos pequenos durante el dia", "contando el agua de los batidos",
                "mejorar el consumo", "d", "a8103ad4-279 a-b542-d50856ad352d.png", "   "):
        assert not ok(bad), bad


def test_no_canonical_food_in_v3_looks_like_a_sentence():
    if not HAVE_V3:
        print("SKIP test_no_canonical_food_in_v3_looks_like_a_sentence: v3 not built")
        return
    data = json.loads((paths.dataset_dir_v3() / "foods.json").read_text(encoding="utf-8"))
    offenders = [f["canonical_name"] for f in data["foods"]
                 if len(f["canonical_name"]) > 40 or len(f["canonical_name"].split()) > 6]
    assert not offenders, offenders


def test_no_two_diets_of_one_client_share_a_source_document():
    """Byte-identical documents of the same client are counted once: a duplicated consecutive version scores
    novelty 0 and drags the rotation figures down."""
    if not HAVE_V3:
        print("SKIP test_no_two_diets_of_one_client_share_a_source_document: v3 not built")
        return
    seen = {}
    for line in (paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        meta = json.loads(line)["meta"]
        key = (meta["client_code"], meta["source_sha1"])
        assert key not in seen, "duplicate source document for %s" % (key,)
        seen[key] = True


def test_diets_sharing_a_document_across_clients_are_flagged():
    """Those are kept on purpose -- one diet given to two people -- but they must carry the template flags, which
    is what keeps them out of the leave-one-out hold-out."""
    if not HAVE_V3:
        print("SKIP test_diets_sharing_a_document_across_clients_are_flagged: v3 not built")
        return
    import collections as _c
    by_sha = _c.defaultdict(list)
    for line in (paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            by_sha[d["meta"]["source_sha1"]].append(d)
    for rows in by_sha.values():
        if len(rows) > 1:
            for d in rows:
                assert d["meta"]["shared_diet"] and d["meta"]["template_group_id"], d["id"]


# --------------------------------------------------------------------------- goals

def test_goal_taxonomy_reads_compound_declarations():
    labels = goals.labels_for("Ganar masa muscular y tonificar", vocab.fold)
    assert "volumen_masa" in labels and "definicion_grasa" in labels
    assert goals.is_compound("Ganar masa muscular y tonificar", labels, vocab.fold)
    single = goals.labels_for("Perder grasa", vocab.fold)
    assert single == ["definicion_grasa"] and not goals.is_compound("Perder grasa", single, vocab.fold)


def test_non_directional_goals_are_excluded_from_the_scale_signal():
    for label in goals.NON_DIRECTIONAL:
        assert label not in goals.DIRECTIONAL


# --------------------------------------------------------------------------- built dataset

def test_work_directory_is_outside_both_audited_trees():
    work = paths.work_dir()          # raises if it is not
    for audited in (paths.repo_root(), paths.data_dir()):
        assert audited.resolve() not in work.resolve().parents


def test_v3_schema_matches_v2():
    if not HAVE_V3:
        print("SKIP test_v3_schema_matches_v2: v3 not built")
        return
    v2 = json.loads((paths.dataset_dir_v2() / "diets.jsonl").read_text(encoding="utf-8").splitlines()[0])
    v3 = json.loads((paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert set(v2) <= set(v3), f"v3 diet record lost top-level keys: {set(v2) - set(v3)}"
    missing = set(v2["meta"]) - set(v3["meta"])
    assert not missing, f"v3 diet meta lost keys the v2 schema has: {missing}"

    p2 = json.loads((paths.dataset_dir_v2() / "profiles.jsonl").read_text(encoding="utf-8").splitlines()[0])
    p3 = json.loads((paths.dataset_dir_v3() / "profiles.jsonl").read_text(encoding="utf-8").splitlines()[0])
    lost = set(p2) - set(p3)
    assert not lost, f"v3 profile lost fields the v2 schema has: {lost}"


def test_v3_carries_the_four_goal_audit_fields():
    if not HAVE_V3:
        print("SKIP test_v3_carries_the_four_goal_audit_fields: v3 not built")
        return
    line = (paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines()[0]
    meta = json.loads(line)["meta"]
    for field in ("goal_declared", "goal_content_predicted", "goal_suspect", "goal_evidence"):
        assert field in meta, field


def test_v3_items_keep_their_raw_text():
    if not HAVE_V3:
        print("SKIP test_v3_items_keep_their_raw_text: v3 not built")
        return
    lines = (paths.dataset_dir_v3() / "diet_items.jsonl").read_text(encoding="utf-8").splitlines()[:500]
    rows = [json.loads(line) for line in lines]
    assert rows and all("raw_text" in r for r in rows)
    assert sum(1 for r in rows if r.get("raw_text")) / len(rows) > 0.95


def test_lab_records_always_declare_their_source_type():
    if not HAVE_V3 or not (paths.dataset_dir_v3() / "lab_results.jsonl").exists():
        print("SKIP test_lab_records_always_declare_their_source_type: v3 not built")
        return
    seen = set()
    for line in (paths.dataset_dir_v3() / "lab_results.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        assert row.get("source_type"), "a lab record without source_type would let a device index be compared " \
                                       "with a laboratory magnitude"
        seen.add(row["source_type"])
        for value in row.get("values", []):
            assert value["namespace"] == row["source_type"], "value namespace must match the report's source type"
    # `sports_physiology` (bloque 0.2): tres informes de ergoespirometria que vivian en el cajon clinico y cuya
    # tabla ANTROPOMETRICA leia el parser de laboratorio como filas analito/valor. Se separan por eso.
    assert seen <= {"clinical", "bioanalyzer", "nutrigenetic", "sports_physiology"}, seen


def test_the_frozen_v2_dataset_was_not_modified_by_the_v3_build():
    if not HAVE_V3:
        print("SKIP test_the_frozen_v2_dataset_was_not_modified_by_the_v3_build: v3 not built")
        return
    log = paths.dataset_dir_v3() / "run_e1_log.json"
    if not log.exists():
        print("SKIP: run_e1 has not been run")
        return
    data = json.loads(log.read_text(encoding="utf-8"))
    assert data["v2_intact"], f"the frozen v2 dataset changed: {data['v2_files_changed']}"


# --------------------------------------------------------------------------- the pharmacological exclusion

def _excluded_pattern():
    import re as _re
    data = json.loads((ROOT / "pipeline" / "src" / "pipeline" / "data" /
                       "excluded_substances.json").read_text(encoding="utf-8"))
    keys = set()
    for entry in data["substances"]:
        keys.add(entry["name"].lower())
        keys.update(k.lower() for k in entry["keys"])
    ordered = sorted((k for k in keys if len(k) >= 2), key=len, reverse=True)
    return _re.compile(r"\b(?:" + "|".join(_re.escape(k) for k in ordered) + r")\b", _re.I)


def test_no_excluded_substance_reaches_a_consumed_output():
    """The exclusion must hold in EVERY output the system reads or prints, not only in the food catalogue.

    The catalogue kept them out of composed items and nothing else did, so a prescription drug still travelled
    diets.notes -> database -> composer note consensus -> the printed PDF. These are the fields on that path.
    raw_text and food_text are deliberately NOT here: they are provenance, the item carries canonical_name=None
    and unmapped_reason='excluded_substance', and it is flagged contains_excluded_substance.
    """
    if not HAVE_V3:
        print("SKIP test_no_excluded_substance_reaches_a_consumed_output: v3 not built")
        return
    pattern = _excluded_pattern()
    D = paths.dataset_dir_v3()
    offenders = []

    def check(path, field, label, allow=()):
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            value = record.get(field)
            blobs = value if isinstance(value, list) else [value]
            for blob in blobs:
                if not isinstance(blob, str):
                    continue
                for hit in pattern.findall(blob):
                    if hit.lower() in allow:
                        continue
                    offenders.append(f"{label}: {record.get('id') or record.get('diet_id')}: {hit}")

    # "insulina" is a key of an excluded entry AND an ordinary clinical word ("regular los picos de insulina").
    # Notes that PRESCRIBE are dropped by pipeline_v3.excluded; notes that merely explain are kept, so the word
    # itself is allowed here and the prescription is not.
    check(D / "retrieval_text.jsonl", "text", "retrieval_text")
    check(D / "diets.jsonl", "text", "diets.text")
    check(D / "meals.jsonl", "text", "meals.text")
    check(D / "diet_items.jsonl", "canonical_name", "diet_items.canonical_name")
    check(D / "diets.jsonl", "notes", "diets.notes", allow={"insulina"})
    assert not offenders, offenders[:12]


def test_no_note_prescribes_an_excluded_substance():
    """A dose next to the substance is a prescription, and it would be printed on the client's PDF."""
    if not HAVE_V3:
        print("SKIP test_no_note_prescribes_an_excluded_substance: v3 not built")
        return
    from pipeline import excluded as _excluded
    bad = []
    for line in (paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        diet = json.loads(line)
        for note in diet.get("notes", []):
            if _excluded.prescribes(note):
                bad.append((diet["id"], note[:70]))
    assert not bad, bad[:8]


def test_every_slot_used_by_the_corpus_exists_in_the_domain_enum():
    """The corpus may not carry a slot the engine cannot represent."""
    if not HAVE_V3:
        print("SKIP test_every_slot_used_by_the_corpus_exists_in_the_domain_enum: v3 not built")
        return
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from finalprosports.domain.model import MealSlot
    known = {s.value for s in MealSlot}
    used = set()
    for line in (paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            used |= set(json.loads(line)["meals"])
    assert used <= known, sorted(used - known)


def test_unmapped_headers_keep_their_literal_in_raw_slot_labels():
    """The generic slot is not a bin: the header the professional wrote survives as data."""
    if not HAVE_V3:
        print("SKIP test_unmapped_headers_keep_their_literal_in_raw_slot_labels: v3 not built")
        return
    from pipeline_v3 import vocab as _vocab
    with_generic = kept = 0
    for line in (paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        diet = json.loads(line)
        if _vocab.GENERIC_SLOT in diet["meals"]:
            with_generic += 1
            kept += bool((diet["meta"].get("raw_slot_labels") or {}).get(_vocab.GENERIC_SLOT))
    assert with_generic and kept / with_generic > 0.95, (kept, with_generic)


def test_activity_level_zero_is_never_stored_as_a_measurement():
    """0 is a valid level (sedentary); the scale writes it for "never filled in" too, so absent must be null."""
    if not HAVE_V3:
        print("SKIP test_activity_level_zero_is_never_stored_as_a_measurement: v3 not built")
        return
    for name in ("profiles.jsonl", "diets.jsonl"):
        for line in (paths.dataset_dir_v3() / name).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            value = record.get("activity_level", (record.get("meta") or {}).get("activity_level"))
            assert value != 0, (name, record.get("id") or record.get("client_code"))


def test_the_exclusion_rule_catches_a_prescription_without_a_dose():
    """The rule that replaced the dose test, and the reason it replaced it.

    The first version kept a note unless a NUMBER sat next to the substance. That is a blocklist over an open set
    of phrasings and "tomar proviron por la noche" walks through it: no dose, an anabolic, straight to the PDF.
    The rule now drops on mention and keeps only recognisable clinical prose, so both halves are asserted here --
    the prescriptions that must go, and the physiology that must stay.
    """
    from pipeline import excluded as _excluded
    must_go = ("tomar proviron por la noche", "PROVIRON POR LAS NOCHES", "yohimbina en ayunas",
               "empezar con tamoxifeno la semana que viene", "t3 por la manana", "gh antes de dormir",
               "anadir oxandrolona antes de entrenar", "2 PROVIRON/DIA",
               "controlar y tomar proviron",                     # a descriptive verb must not launder an order
               "para mejorar la testosterona puedes tomar proviron")
    must_stay = ("dieta para mejorar la resistencia a la insulina",
                 "PARA REGULAR LOS PICOS DE INSULINA A LO LARGO DEL DIA",
                 "Ganar Masa Muscular y potenciar fibras blancas y testosterona",
                 "Volumen muscular con estimulacion de la testosterona endogena.",
                 "beber 2 litros de agua al dia", "ensalada de pollo con arroz")
    assert [t for t in must_go if not _excluded.must_drop(t)] == []
    assert [t for t in must_stay if _excluded.must_drop(t)] == []


def test_the_loader_applies_the_exclusion_to_whatever_dataset_is_active():
    """The guard may not live only in the v3 extractor.

    The rollback plan for the whole rebuild is "point FPS_DATASET_DIR back at v2", and v2 was built before the
    exclusion existed: it carries excluded substances in the rendered meal text of 36 diets. A construction-time
    guard would make that rollback reintroduce the defect. The filter therefore also runs on the way into the
    database, which is what this asserts -- on synthetic rows, so it holds with no dataset present.
    """
    from pipeline.load_postgres import guard_text
    assert guard_text("CENA: 2 PROVIRON | ensalada") == "CENA: 2 [SUSTANCIA EXCLUIDA] | ensalada"
    assert guard_text("OBJETIVO: mejorar la resistencia a la insulina") == "OBJETIVO: mejorar la resistencia a la insulina"
    rendered = "OBJETIVO: regular los picos de insulina\nDESAYUNO: avena | tostada\nANTES DE ENTRENAR: tamoxifeno"
    guarded = guard_text(rendered)
    assert guarded.splitlines()[0] == "OBJETIVO: regular los picos de insulina"   # prose survives
    assert guarded.splitlines()[1] == "DESAYUNO: avena | tostada"                 # untouched lines are identical
    assert "tamoxifeno" not in guarded                                            # the item does not
    assert guard_text("DESAYUNO: avena") == "DESAYUNO: avena" and guard_text(None) is None


def test_purpose_and_method_are_two_fields_and_neither_evicts_the_other():
    """"Ayuno intermitente para perder grasa" declares a purpose AND a regime, and both are kept.

    v2 read the regime into `goal` and lost the purpose; the first v3 build read the purpose and lost the regime,
    which collapsed the condition group of every rule whose antecedent is a regime (`sin_hidratos_cena`: 300 diets
    down to 98, then retired for lack of support) and left the conditional-compliance metric with a single rule.
    """
    from pipeline_v3 import goals as taxonomy
    text = "Ayuno intermitente para perder grasa"
    labels = taxonomy.labels_for(text, vocab.fold)
    assert taxonomy.primary(labels) == "definicion_grasa"          # the purpose decides the goal
    assert taxonomy.primary_method(taxonomy.methods_for(text, vocab.fold)) == "ayuno_intermitente"
    # A purpose alone declares no method, and a regime alone still lands in `goal` as it always did.
    assert taxonomy.methods_for("Perder grasa", vocab.fold) == []
    assert taxonomy.primary(taxonomy.labels_for("Ayuno intermitente", vocab.fold)) == "ayuno_intermitente"


def test_the_rebuilt_corpus_keeps_the_method_of_every_diet_that_declares_one():
    if not HAVE_V3:
        print("SKIP test_the_rebuilt_corpus_keeps_the_method_of_every_diet_that_declares_one")
        return
    from pipeline_v3 import goals as taxonomy
    missing = []
    for line in (paths.dataset_dir_v3() / "diets.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        diet = json.loads(line)
        meta = diet["meta"]
        assert "method" in meta and "methods" in meta, diet["id"]
        assert meta["method"] is None or meta["method"] in taxonomy.METHOD_ORDER, (diet["id"], meta["method"])
        # Whatever the goal ended up being, a declaration that names a regime must carry it.
        declared = taxonomy.methods_for(meta.get("goal_declared") or "", vocab.fold)
        if declared and not meta["methods"]:
            missing.append(diet["id"])
    assert not missing, missing[:8]


if __name__ == "__main__":
    # ESTA SUITE DESCRIBE EL ETL DEL CORPUS PRIVADO. En un árbol sin corpus —el repositorio público lleva una base de
    # casos sintética y ningún artefacto de la extracción— no hay nada que comprobar, así que se SALTA diciendo por
    # qué en vez de fallar y tapar la única señal que importa allí. Mismo criterio que `test_dataset.py`.
    from pipeline.paths import data_dir as _data, repo_root as _root
    try:
        _dentro = _data().resolve().is_relative_to(_root().resolve())
    except (OSError, ValueError):
        _dentro = False
    if _dentro:
        print(f"SKIP  test_pipeline_v3: el árbol de datos ({_data()}) está DENTRO del repositorio, así que el "
              f"directorio de trabajo del v3 no puede estar fuera de un árbol auditado. Es correcto: esta suite "
              f"describe la reextracción del corpus privado y el árbol público no la lleva")
        sys.exit(0)

    failed = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
    print(f"\n{'FAILED' if failed else 'OK'}: {failed} failing")
    sys.exit(1 if failed else 0)
