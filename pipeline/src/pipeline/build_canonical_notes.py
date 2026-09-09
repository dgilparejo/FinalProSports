# -*- coding: utf-8 -*-
"""Build the catalogue of canonical notes (E9 · realism batch) from the corpus.

The problem it solves. `compose_notes` consensused EXACT strings, and the professional writes the same instruction in many
wordings: the hydration line lives in 636 of the 1.033 diets across 357 distinct strings, the largest of which covers 33.
Measured consequence: not one note string in the corpus reaches the consensus threshold `note_t = 0,35` (0 of 1.171), so the
threshold branch never fired and everything the composer emitted came from the `min_notes` top-up — one neighbour's literal
sentence. The rule `agua_2.5L` therefore scored 0,088 against the professional's 0,790.

What this builds. A theme catalogue: each entry is a regular expression that recognises the instruction in any of his
wordings, plus ONE canonical wording chosen from the corpus, plus the corpus support. The composer then consensuses over
THEMES and emits the canonical wording, so the same instruction written 357 ways counts 357 times for one theme instead of
once for each string. The themes are human criterion and live versioned in `pipeline/src/pipeline/data/note_themes.json`;
this script only measures their support and picks the canonical wording, which is the most frequent full sentence of the
theme (a length floor keeps it from picking a fragment).

Artefacts. 14,5 % of the `notes` field is not notes: section headers the parser kept («Observaciones:», «Recomendaciones:»,
«Consejos:» = 370 occurrences) and fragments of the document footer («tel», «/ tel», `("` = 269). They were being copied into
proposals — one of them reached a golden snapshot. They are dropped here and by the composer.

Run:  python pipeline/src/pipeline/build_canonical_notes.py [--apply]
Out:  FPS_DATASET_DIR/canonical_notes.json  (+ pipeline/src/pipeline/data/note_themes.json is the input criterion)
Prints aggregates only. The canonical wordings are the professional's own instruction text, never client text; the tree
audit runs over the output like over everything else.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import dataset_dir, repo_root  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
MIN_CANONICAL_LEN = 15          # a canonical wording must be a sentence, not a fragment (with MIN_CANONICAL_WORDS)
MIN_CANONICAL_WORDS = 3         # at 25 chars the floor discarded «Dormir de 7 a 8 horas.» (22) and let a 1-occurrence
                                # sentence win the theme: the guard must reject fragments, not short instructions
MIN_SUPPORT_DIETS = 15          # a theme with less corpus support than this is not boilerplate, it is a personal note


def clean(s: str) -> str:
    """His own wording, minus the bullet or dash the document used to lay it out. Casing is his and is kept: he writes some
    instructions in capitals and that is part of how the diet reads."""
    return re.sub(r"^[\s\-*•.:;]+", "", (s or "").strip()).strip()


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def load_themes() -> dict:
    return json.loads((DATA / "note_themes.json").read_text(encoding="utf-8"))


def build(diets_notes: list[list[str]], themes: dict) -> dict:
    artefact = re.compile(themes["artefacts"]["pattern"], re.I)
    entries = []
    total_occ = kept_occ = artefact_occ = 0
    matched_occ = 0
    seen_strings: Counter = Counter()
    for entry in themes["themes"]:
        entries.append({**entry, "rx": re.compile(entry["pattern"], re.I), "diets": 0, "wordings": Counter(),
                        "must_rx": re.compile(entry["must_match"], re.I) if entry.get("must_match") else None})

    for notes in diets_notes:
        seen = set()
        themes_here = set()
        for raw in notes:
            n = norm(raw)
            if not n or n in seen:
                continue
            seen.add(n)
            total_occ += 1
            if artefact.search(n):
                artefact_occ += 1
                continue
            kept_occ += 1
            seen_strings[n] += 1
            hit = False
            for e in entries:
                if e["rx"].search(n):
                    hit = True
                    themes_here.add(e["id"])
                    text = clean(raw)
                    if len(text) >= MIN_CANONICAL_LEN and len(text.split()) >= MIN_CANONICAL_WORDS:
                        e["wordings"][text] += 1
            matched_occ += hit
        for tid in themes_here:
            next(e for e in entries if e["id"] == tid)["diets"] += 1

    n_diets = len(diets_notes)
    out = []
    for e in entries:
        if not e["wordings"] or e["diets"] < MIN_SUPPORT_DIETS:
            continue
        must = e.get("must_rx")
        ranked = e["wordings"].most_common()
        eligible = [(w, c) for w, c in ranked if must is None or must.search(w)]
        if must is not None and not eligible:
            print(f"  WARNING theme {e['id']}: no wording of the corpus satisfies the rule pattern it claims", file=sys.stderr)
        canonical, times = (eligible or ranked)[0]
        out.append({"id": e["id"], "pattern": e["pattern"], "canonical": canonical,
                    "support_diets": e["diets"], "support_share": round(e["diets"] / n_diets, 4),
                    "distinct_wordings": len(e["wordings"]), "canonical_times": times,
                    "must_match": e.get("must_match"), "rule_ids": e.get("rule_ids", [])})
    out.sort(key=lambda x: -x["support_diets"])
    return {"source": "dataset diets.jsonl notes", "n_diets": n_diets, "note_occurrences": total_occ,
            "artefacts_dropped": artefact_occ, "kept": kept_occ, "matched_by_a_theme": matched_occ,
            "artefact_pattern": themes["artefacts"]["pattern"],
            "min_support_diets": MIN_SUPPORT_DIETS, "themes": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the catalogue (otherwise only report)")
    args = ap.parse_args()
    D = dataset_dir()
    diets_notes = [json.loads(l).get("notes") or [] for l in (D / "diets.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    themes = load_themes()
    res = build(diets_notes, themes)
    print(f"diets {res['n_diets']} | note occurrences {res['note_occurrences']} | artefacts dropped {res['artefacts_dropped']} "
          f"({res['artefacts_dropped'] / res['note_occurrences']:.1%}) | matched by a theme {res['matched_by_a_theme']} "
          f"({res['matched_by_a_theme'] / max(1, res['kept']):.1%} of what remains)")
    print(f"themes kept (support >= {MIN_SUPPORT_DIETS} diets): {len(res['themes'])} of {len(themes['themes'])}\n")
    print(f"{'theme':26s} {'diets':>6s} {'share':>7s} {'wordings':>9s}  canonical")
    for t in res["themes"]:
        print(f"{t['id']:26s} {t['support_diets']:6d} {t['support_share']:7.1%} {t['distinct_wordings']:9d}  {t['canonical'][:78]}")
    if args.apply:
        (D / "canonical_notes.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(f"\nwritten: {D / 'canonical_notes.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
