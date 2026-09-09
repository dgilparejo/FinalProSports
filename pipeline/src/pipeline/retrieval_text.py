# -*- coding: utf-8 -*-
"""
E3.1 — Retrieval text of every diet, built from the structured items (not from the original text).

Input:  _dataset/diets.jsonl (header: goal, goal_text, profile snapshot, notes), _dataset/diet_items.jsonl (canonical names per slot)
Output: _dataset/retrieval_text.jsonl  {diet_id, retrieval_text, chars, slots, notes_used}  + length statistics on stdout

Format (domain policy `retrieval_text_policy.document_text`; the query side shares the header):
  OBJETIVO: <goal_text> | META: <goal>
  PERFIL: sexo M | edad 25-39 | actividad 5 | intolerancias no
  DESAYUNO: <canonical foods>  ...  CENA: ...
  NOTAS: the 3 most informative notes

"Most informative" = highest sum of inverse document frequency of its tokens over the corpus of notes (rare words carry
the information: 'sin hidratos en la cena' beats 'beber agua'), after removing duplicates; each note capped at 160 chars.
Only mapped components contribute (unmapped 2 %: no canonical name; excluded substances must not appear anywhere).
Used by load_postgres.py (column diets.retrieval_text) and embed_corpus.py (what gets vectorised). Nothing printed but counts.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR  # noqa: E402
from pipeline import excluded  # noqa: E402
from finalprosports.domain.composition.policy.retrieval_text_policy import document_text  # noqa: E402
from finalprosports.domain.model import Goal  # noqa: E402

TOKEN = re.compile(r"[a-záéíóúñü0-9]{3,}")
STOP = {"para", "con", "sin", "por", "una", "uno", "los", "las", "del", "que", "como", "más", "mas", "muy", "tambien", "también", "puede",
        "pueden", "cada", "todo", "toda", "todos", "todas", "este", "esta", "esto", "hay", "ser", "tomar", "comer", "dia", "día", "dias", "días"}
NOTES_PER_DIET = 3


def tokens(note: str) -> set[str]:
    return {t for t in TOKEN.findall(note.lower()) if t not in STOP}


def select_informative_notes(notes_by_diet: dict[str, list[str]], n: int = NOTES_PER_DIET) -> dict[str, list[str]]:
    df: Counter = Counter()
    docs = 0
    for notes in notes_by_diet.values():
        for note in notes:
            docs += 1
            df.update(tokens(note))
    out = {}
    for diet_id, notes in notes_by_diet.items():
        unique = list(dict.fromkeys(x.strip() for x in notes if x and x.strip()))
        scored = sorted(unique, key=lambda x: (-sum(math.log((docs + 1) / (df[t] + 1)) for t in tokens(x)), unique.index(x)))
        out[diet_id] = scored[:n]
    return out


# The generic OTHER bucket is not indexed either. It is the slot the system may not compose into
# (composition_policy.NON_COMPOSABLE_SLOTS), so retrieving a case on the strength of its contents would rank
# neighbours by material that can never reach a proposal. It is also what pushed the longest retrieval text past
# the 512-token window of e5-base: one diet reached 1.927 characters, all of it an unmapped bucket.
NON_INDEXED_SLOTS = frozenset({"OTHER"})


def build_retrieval_texts(diets: list[dict], items: list[dict]) -> dict[str, dict]:
    """{diet_id: {retrieval_text, chars, slots, notes_used}} — pure data in, pure data out."""
    slot_foods: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for it in sorted(items, key=lambda i: (i["diet_id"], i["position"], i["component_index"])):
        if it.get("canonical_name") and it["meal_slot"] not in NON_INDEXED_SLOTS:
            slot_foods[it["diet_id"]][it["meal_slot"]].append(it["canonical_name"])
    notes = select_informative_notes({d["id"]: list(d.get("notes") or []) for d in diets})
    out = {}
    for d in diets:
        m = d["meta"]
        sex = m.get("sex") if m.get("sex") in ("M", "F") else None
        # The retrieval text takes FULL redaction, unlike `goal_text` itself, and the difference is deliberate.
        # `goal_text` is prose a person reads, so "mejorar la resistencia a la insulina" must survive intact.
        # This string is a machine-facing index that nobody reads: redacting every mention costs nothing a human
        # would miss and keeps the invariant absolute -- no excluded substance in any embedded or indexed output.
        text = excluded.redact(
            document_text(Goal(m["goal"]), m.get("goal_text"), sex, m.get("age"), m.get("activity_level"),
                          bool(m.get("has_intolerances")), dict(slot_foods.get(d["id"], {})), notes[d["id"]]))
        out[d["id"]] = {"retrieval_text": text, "chars": len(text), "slots": len(slot_foods.get(d["id"], {})), "notes_used": len(notes[d["id"]])}
    return out


def jl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diets", type=Path, default=DATASET_DIR / "diets.jsonl")
    ap.add_argument("--items", type=Path, default=DATASET_DIR / "diet_items.jsonl")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "retrieval_text.jsonl")
    args = ap.parse_args()
    diets, items = jl(args.diets), jl(args.items)
    texts = build_retrieval_texts(diets, items)
    with args.out.open("w", encoding="utf-8") as f:
        for diet_id, rec in texts.items():
            f.write(json.dumps({"diet_id": diet_id, **rec}, ensure_ascii=False) + "\n")
    chars = sorted(r["chars"] for r in texts.values())
    orig = sorted(len(d["text"]) for d in diets)
    q = lambda xs, p: xs[min(len(xs) - 1, int(p * (len(xs) - 1)))]  # noqa: E731
    print(json.dumps({"diets": len(texts), "chars_retrieval_text": {"p50": q(chars, .5), "p95": q(chars, .95), "max": chars[-1]},
                      "chars_original_text": {"p50": q(orig, .5), "p95": q(orig, .95), "max": orig[-1]},
                      "diets_with_notes": sum(r["notes_used"] > 0 for r in texts.values()), "diets_without_mapped_items": sum(r["slots"] == 0 for r in texts.values())}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
