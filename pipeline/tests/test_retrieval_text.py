# -*- coding: utf-8 -*-
"""Acceptance tests of the retrieval text (E3.1) built from the frozen dataset. Skipped when the dataset is absent."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import DATASET_DIR  # noqa: E402
from pipeline.retrieval_text import build_retrieval_texts, jl, select_informative_notes  # noqa: E402

HAVE = (DATASET_DIR / "diets.jsonl").exists() and (DATASET_DIR / "diet_items.jsonl").exists()
if HAVE:
    DIETS = jl(DATASET_DIR / "diets.jsonl")
    ITEMS = jl(DATASET_DIR / "diet_items.jsonl")
    TEXTS = build_retrieval_texts(DIETS, ITEMS)


def test_informative_notes_prefer_rare_words_and_dedupe():
    notes = {"d1": ["beber agua", "beber agua", "sin hidratos en la cena", "beber agua todos los días"], "d2": ["beber agua"], "d3": ["beber agua"]}
    picked = select_informative_notes(notes, n=2)
    assert picked["d1"][0] == "sin hidratos en la cena" and len(picked["d1"]) == 2 and len(set(picked["d1"])) == 2


def test_every_diet_has_a_text_with_header_and_slots():
    if not HAVE:
        return
    assert len(TEXTS) == len(DIETS) > 0          # one text per diet of whatever dataset is active
    for d in DIETS:
        t = TEXTS[d["id"]]["retrieval_text"]
        lines = t.splitlines()
        assert lines[0].startswith("OBJETIVO: ") and f"| META: {d['meta']['goal']}" in lines[0]
        assert lines[1].startswith("PERFIL: sexo ")
        # A diet with no indexed slot is one whose whole content sits in the non-composable OTHER bucket. Those
        # are the diets declared irrepresentable and removed from the evaluation, so an empty index for them is
        # the correct outcome, not a defect -- but it must be exactly those and no others.
        if TEXTS[d["id"]]["slots"] < 1:
            assert not [i for i in ITEMS if i["diet_id"] == d["id"] and i["meal_slot"] != "OTHER"
                        and i.get("canonical_name")], d["id"]


def test_texts_are_much_shorter_than_the_original_and_bounded():
    if not HAVE:
        return
    chars = sorted(r["chars"] for r in TEXTS.values())
    assert chars[-1] <= 1600, chars[-1]                                     # ~ under the 512-token window of e5-base
    assert chars[len(chars) // 2] < sorted(len(d["text"]) for d in DIETS)[len(DIETS) // 2]


def test_excluded_substances_and_unmapped_components_never_appear():
    if not HAVE:
        return
    unmapped_texts = {i["food_text"].lower() for i in ITEMS if i["unmapped"] and i["unmapped_reason"] == "excluded_substance"}
    canon = {i["canonical_name"] for i in ITEMS if i["canonical_name"]}
    body = "\n".join(r["retrieval_text"] for r in TEXTS.values()).lower()
    for w in unmapped_texts:
        if len(w) >= 6 and w not in {c.lower() for c in canon}:
            assert w not in body, w


def test_notes_capped_at_three_and_present_when_the_diet_has_notes():
    if not HAVE:
        return
    for d in DIETS:
        r = TEXTS[d["id"]]
        assert r["notes_used"] <= 3
        assert (r["notes_used"] > 0) == bool([n for n in d["notes"] if n.strip()])


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as ex:
                failed += 1; print(f"FAIL  {name}: {str(ex)[:400]}")
    if not HAVE:
        print("NOTE  dataset not present: data-dependent tests were skipped")
    sys.exit(1 if failed else 0)
