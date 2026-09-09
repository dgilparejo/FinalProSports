"""F3 -- diets: documents to ``diets.jsonl`` / ``meals.jsonl`` in the v2 schema.

The output schema is deliberately identical to v2 so that the existing E1 chain (``parse_items`` ->
``build_food_catalog`` -> ``normalize_diets``) runs unchanged on top of it. That keeps the comparison honest: the
item parser and the food catalogue are the same on both sides, so any difference in the result is attributable to
the extraction, which is the thing being rebuilt.

What changes is the splitter. v2 recognised twelve header prefixes and let anything else fall into whichever slot
was open; this one asks :mod:`pipeline_v3.vocab` about every header-shaped line and, when the answer is "no rule
matched", opens ``UNMAPPED_<literal>`` rather than extending the slot above (principle 4). Sections are routed:
the goal line becomes ``goal_text``, note blocks become ``notes`` (v2 discarded 713 of them), day-type variants
become ``day_variant`` on the meals they govern instead of being read as more food.

Every item keeps ``raw_text``.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline import excluded
    from pipeline_v3 import convert, goals as goal_taxonomy, identity, paths, vocab
else:
    from pipeline import excluded
    from . import convert, goals as goal_taxonomy, identity, paths, vocab

# A line that is only decoration, a page number or a converter artefact: skipped, and counted as skipped.
# A line with no content of its own: decoration, a page number, a converter artefact, or nothing but the
# placeholders the anonymiser left behind. The last alternative used to require a SINGLE placeholder, so the
# professional's signature line "[TEL] / [EMAIL]" survived as a note in 58 diets and inside 17 rendered texts.
_PLACEHOLDER = r"\[(?:url|email|tel|profesional|nombre|apellido)\]"
_NOISE = re.compile(r"^[\s\-_=*·•.|]*$|^p[áa]gina\s+\d+|^\d+\s*/\s*\d+$|"
                   r"^[\s\-_=*·•.|/,;:()+\d]*(?:" + _PLACEHOLDER + r"[\s\-_=*·•.|/,;:()+\d]*)+$", re.I)
_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})(?!\d)")
_VERSION_IN_NAME = re.compile(r"(?:^|[^0-9])(\d{1,2})(?:\s*$|[^0-9])")


def _parse_date(text: str) -> str | None:
    match = _DATE.search(text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    if year < 100:
        year += 2000 if year < 70 else 1900
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1990 <= year <= 2030):
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _split_items(rest: str) -> list[str]:
    """Split a line into item texts. ``|`` is a table-cell boundary introduced by the converters."""
    parts = [p.strip() for p in rest.split("|")]
    return [p for p in parts if p and not _NOISE.match(p)]


def parse_document(text: str) -> dict:
    """One diet document -> ``{meals, notes, goal_text, doc_date, unmapped_slots, stats}``.

    ``meals`` maps a slot name to its list of item texts, in document order. A repeated slot (``COMIDA`` twice under
    two different day variants) is kept as one slot whose items carry the variant, which is what the v2 schema can
    express; the variant itself is recorded per item so nothing is lost.
    """
    meals: dict[str, list[str]] = collections.OrderedDict()
    item_variants: dict[str, list[str | None]] = collections.OrderedDict()
    notes: list[str] = []
    goal_lines: list[str] = []
    preamble: list[str] = []
    unmapped: collections.Counter = collections.Counter()
    stats = collections.Counter()

    current_slot: str | None = None
    current_raw_label: str | None = None
    current_section: str | None = None
    current_variant: str | None = None
    doc_date: str | None = None

    raw_slot_labels: dict[str, list[str | None]] = collections.OrderedDict()

    def add_item(slot: str, item: str, variant: str | None) -> None:
        meals.setdefault(slot, [])
        item_variants.setdefault(slot, [])
        raw_slot_labels.setdefault(slot, [])
        meals[slot].append(item)
        item_variants[slot].append(variant)
        raw_slot_labels[slot].append(current_raw_label)

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or _NOISE.match(line):
            continue
        if doc_date is None:
            doc_date = _parse_date(line)

        parsed = vocab.split_header(line)
        if parsed is not None:
            head, rest = parsed
            normalised = vocab.normalise_header(head)
            kind, target, _reason = vocab.classify_header(normalised)

            if kind == "slot":
                current_slot, current_section = target, None
                current_raw_label = None
                stats["slot_headers"] += 1
                for item in _split_items(rest):
                    add_item(target, item, current_variant)
                continue
            if kind == "section":
                if target == "variant":
                    current_variant = normalised
                    current_slot, current_section = None, None
                    stats["variant_headers"] += 1
                    continue
                if target == "goal":
                    current_section, current_slot = "goal", None
                    if rest:
                        goal_lines.append(rest)
                    stats["goal_headers"] += 1
                    continue
                if target == "notes":
                    current_section, current_slot = "notes", None
                    if rest:
                        notes.append(rest)
                    stats["note_headers"] += 1
                    continue
                if target in ("contact", "profile_field"):
                    current_section, current_slot = target, None
                    stats[f"{target}_headers"] += 1
                    continue
                if target in ("conditional", "date"):
                    # A conditional block is real diet content under a condition, so it becomes its own slot
                    # rather than being merged into the previous one.
                    current_slot = vocab.GENERIC_SLOT
                    current_raw_label = normalised
                    current_section = None
                    unmapped[normalised] += 1
                    stats["conditional_headers"] += 1
                    for item in _split_items(rest):
                        add_item(current_slot, item, current_variant)
                    continue
            # kind == "unmapped": the content gets the generic OTHER slot, which the domain already has, and the
            # header's literal text is preserved in raw_slot_label. Neither invented as 528 enum members nor
            # thrown away (principle 4): the slot is generic, the label is data.
            current_slot = vocab.GENERIC_SLOT
            current_raw_label = normalised
            current_section = None
            unmapped[normalised] += 1
            stats["unmapped_headers"] += 1
            for item in _split_items(rest):
                add_item(current_slot, item, current_variant)
            continue

        # Not a header: content for whatever is open.
        if current_section == "notes":
            notes.append(line)
            stats["note_lines"] += 1
        elif current_section == "goal":
            goal_lines.append(line)
            stats["goal_lines"] += 1
        elif current_section in ("contact", "profile_field"):
            stats[f"{current_section}_lines_not_food"] += 1
        elif current_slot:
            for item in _split_items(line):
                add_item(current_slot, item, current_variant)
                stats["item_lines"] += 1
        else:
            # Before any header: the title line, the date, or a loose goal sentence. Kept, because titles like
            # "DIETA DE VOLUMEN" are where the goal is stated when there is no OBJETIVO label at all.
            preamble.append(line)
            stats["preamble_lines"] += 1

    return {
        "meals": meals,
        "item_variants": item_variants,
        "raw_slot_labels": raw_slot_labels,
        "notes": notes,
        "goal_text": " ".join(goal_lines).strip()[:500],
        "preamble": " ".join(preamble).strip()[:400],
        "doc_date": doc_date,
        "unmapped_slots": dict(unmapped),
        "stats": dict(stats),
    }


def _diet_text(goal_text: str, meals: dict[str, list[str]], redact: bool = True) -> str:
    """The rendered diet text, loaded into the database verbatim.

    Excluded substances are REDACTED here: this string is a derived output like any other, and leaving them in it
    is how a prescription drug reaches everything that reads ``diets.text``. Redaction is off only for the
    internal call that infers a goal from the diet's own content, where the marker would add nothing.

    Everything here is redacted, the OBJETIVO line included, and that is deliberately stricter than the ``goal_text``
    FIELD. Exactly one place keeps the professional's prose intact -- ``meta.goal_text``, which is what a person
    reads -- and every derived rendering of it is redacted without exception. Splitting the rule per line inside a
    rendering buys nothing (nobody reads this string) and costs the only invariant worth having here: no excluded
    substance in any derived output, with no case analysis to get wrong.
    """
    clean = excluded.redact if redact else (lambda t: t)
    lines = []
    if goal_text:
        lines.append(f"OBJETIVO: {clean(goal_text)}")
    for slot, items in meals.items():
        lines.append(f"{slot}: " + " | ".join(clean(i) for i in items))
    return "\n".join(lines)


def _clean_prose(text: str) -> str:
    """Redact a prose field only when its mentions are not recognisable clinical language."""
    return excluded.redact(text) if excluded.must_drop(text) else text


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    registry = identity.load_or_build_registry(paths.sources_root())
    scrub = registry.scrub_for_dataset
    manifest = [json.loads(line) for line in (out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()]
    rows = [r for r in manifest if r.get("label") == "diet" and r.get("status") == "ok" and r.get("client_code")]

    by_client: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        by_client[row["client_code"]].append(row)

    diets: list[dict] = []
    meal_records: list[dict] = []
    reconciliation: list[dict] = []
    totals = collections.Counter()
    unmapped_total: collections.Counter = collections.Counter()

    duplicates_dropped: list[dict] = []
    notes_dropped: list[dict] = []
    discarded_empty: list[dict] = []
    for code in sorted(by_client):
        # The same document is often stored twice under two names ("DIETA ... 4.odt" and "DIETA ... 5.odt" with
        # identical bytes). Keeping both invents a version: 38 of the 39 duplicate groups land on CONSECUTIVE
        # version numbers, and a consecutive pair with identical content scores novelty 0 and family overlap 1,
        # which drags the rotation figures down. Byte-identical documents OF THE SAME CLIENT are therefore counted
        # once. Identical documents of DIFFERENT clients are kept: that is a diet he gave to two people, which is
        # real and is already flagged by shared_diet / template_group_id.
        seen: dict[str, dict] = {}
        rows_for_client = []
        for row in sorted(by_client[code], key=lambda r: r["rel"]):
            first = seen.get(row["sha1"])
            if first is not None:
                duplicates_dropped.append({"client_code": code, "kept": first["rel"], "dropped": row["rel"],
                                           "sha1": row["sha1"],
                                           "reason": "byte-identical to another document of the same client"})
                continue
            seen[row["sha1"]] = row
            rows_for_client.append(row)

        parsed_docs = []
        for row in rows_for_client:
            parsed = parse_document(convert.cached_text(row["sha1"]))
            parsed_docs.append((row, parsed))
        # Version order: by document date when present, then by the masked file name for a stable tie-break.
        parsed_docs.sort(key=lambda rp: (rp[1]["doc_date"] or "9999-99-99", rp[0]["rel"]))

        for index, (row, parsed) in enumerate(parsed_docs, 1):
            # Final PII pass on everything that will be written (see ClientRegistry.scrub_for_dataset).
            parsed["meals"] = {slot: [scrub(i) for i in items] for slot, items in parsed["meals"].items()}
            # A note that names an excluded substance is DROPPED unless the mention is recognisable clinical
            # prose ("resistencia a la insulina"). It travels to the composer's note consensus and from there to
            # the printed PDF, so the default has to be discard: a dose test is a blocklist and "tomar proviron
            # por la noche" walks straight through it. See pipeline.excluded.must_drop.
            kept_notes = []
            for note in parsed["notes"]:
                if _NOISE.match(note):                       # signature residue: "[TEL] / [EMAIL]" and friends
                    continue
                if excluded.must_drop(note):
                    reason = ("prescribes an excluded substance" if excluded.prescribes(note)
                              else "names an excluded substance outside clinical prose")
                    notes_dropped.append({"client_code": code, "reason": reason})
                    continue
                kept_notes.append(scrub(note))
            parsed["notes"] = kept_notes
            # goal_text is copied verbatim into the header of retrieval_text, so it is a consumed output. It is
            # NOT redacted blindly: his stated objectives legitimately name hormones as physiology ("mejorar la
            # resistencia a la insulina"), and redacting those mangled 37 of them into nonsense. Redaction
            # applies only when the mention is not clinical prose.
            parsed["goal_text"] = _clean_prose(scrub(parsed["goal_text"]))
            parsed["preamble"] = scrub(parsed["preamble"])
            meals = parsed["meals"]
            item_count = sum(len(v) for v in meals.values())
            diet_id = f"{code}::v{index:02d}"
            if not meals:
                reconciliation.append({"rel": row["rel"], "client_code": code, "records": 0,
                                       "reason": "no meal slot was recognised in the document",
                                       "chars": row.get("chars", 0),
                                       "unmapped_slots": parsed["unmapped_slots"]})
                # Also emitted as a RECORD, in v2's discarded_empty.jsonl shape. A count in a log says a document
                # was dropped; a record says which one and what was in it, which is what "zero silent loss" means
                # and what the schema-parity rule requires (fields are added, never removed).
                discarded_empty.append({
                    "id": diet_id, "text": "", "meals": {}, "notes": [scrub(n) for n in parsed["notes"]],
                    "meta": {"client_code": code, "diet_version": index, "source_sha1": row["sha1"],
                             "source_rel": row["rel"], "unmapped_slots": parsed["unmapped_slots"],
                             "chars": row.get("chars", 0)},
                    "_emptied_by_cleaning": False,
                    "discard_reason": "no meal slot was recognised in the document",
                })
                totals["documents_without_meals"] += 1
                continue

            declared = parsed["goal_text"]
            labels = goal_taxonomy.labels_for(declared, vocab.fold)
            inferred = False
            if not labels:
                # No OBJETIVO line, or one that names no goal. Try the document's own opening lines (the title is
                # often "DIETA DE VOLUMEN"), then the meal text. Either way the label is marked as inferred.
                labels = goal_taxonomy.labels_for(parsed["preamble"], vocab.fold)
                if not labels:
                    labels = goal_taxonomy.labels_for(_diet_text("", meals, redact=False), vocab.fold)
                inferred = bool(labels)
            # The structural method, mined from the same declaration and kept apart from the goal (goals.py).
            # The preamble is included because the regime is often only in the title ("DIETA CETOGENICA"), while
            # the meal text is NOT: inferring "fasting" from a missing breakfast is what conflated the two fields
            # in the first place.
            methods = goal_taxonomy.methods_for(declared, vocab.fold, parsed["preamble"])
            meta = {
                "client_code": code,
                "diet_version": index,
                "goal": goal_taxonomy.primary(labels),
                "goals": labels,
                "method": goal_taxonomy.primary_method(methods),
                "methods": methods,
                "goal_inferred": inferred,
                "goal_declared": declared,
                "goal_is_compound": goal_taxonomy.is_compound(declared, labels, vocab.fold),
                "goal_uncovered_purposes": goal_taxonomy.uncovered_purposes(declared, vocab.fold),
                "goal_text": declared,
                "doc_date": parsed["doc_date"],
                "meal_count": len(meals),
                "item_count": item_count,
                "note_count": len(parsed["notes"]),
                "source_sha1": row["sha1"],
                "source_rel": row["rel"],
                "unmapped_slots": parsed["unmapped_slots"],
                "day_variants": sorted({v for values in parsed["item_variants"].values() for v in values if v}),
                "raw_slot_labels": {s: sorted({x for x in v if x})
                                    for s, v in parsed["raw_slot_labels"].items() if any(v)},
            }
            diets.append({
                "id": diet_id,
                "text": _diet_text(parsed["goal_text"], meals),
                "meta": meta,
                "meals": meals,
                "notes": parsed["notes"],
                "item_variants": parsed["item_variants"],
                "raw_slot_labels": parsed["raw_slot_labels"],
            })
            for slot, items in meals.items():
                meal_records.append({
                    "id": f"{diet_id}::{slot}",
                    "text": f"{slot}: " + " | ".join(items),
                    "meta": {"client_code": code, "diet_version": index, "slot": slot,
                             "item_count": len(items), "goal_text": parsed["goal_text"]},
                })
            totals["diets"] += 1
            totals["meals"] += len(meals)
            totals["items"] += item_count
            totals["notes"] += len(parsed["notes"])
            for key, value in parsed["unmapped_slots"].items():
                unmapped_total[key] += value
            for key, value in parsed["stats"].items():
                totals[f"stat_{key}"] += value
            reconciliation.append({"rel": row["rel"], "client_code": code, "diet_id": diet_id,
                                   "records": item_count, "meals": len(meals), "notes": len(parsed["notes"])})

    with open(out_dir / "diets.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for record in diets:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    with open(out_dir / "meals.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for record in meal_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    with open(out_dir / "discarded_empty.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for record in discarded_empty:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    slot_counts = collections.Counter()
    for record in diets:
        for slot in record["meals"]:
            slot_counts[slot] += 1
    summary = {
        "documents_in": len(rows),
        "duplicate_documents_dropped": len(duplicates_dropped),
        "clients": len(by_client),
        "diets_out": totals["diets"],
        "documents_without_meals": totals["documents_without_meals"],
        "meals_out": totals["meals"],
        "items_out": totals["items"],
        "notes_out": totals["notes"],
        "notes_dropped_prescribing_an_excluded_substance": len(notes_dropped),
        "slots_used": dict(slot_counts.most_common()),
        "unmapped_slot_occurrences": sum(unmapped_total.values()),
        "unmapped_slot_distinct": len(unmapped_total),
        "unmapped_slots_top": unmapped_total.most_common(40),
        "line_stats": {k[5:]: v for k, v in totals.items() if k.startswith("stat_")},
    }
    (out_dir / "extract_diets_log.json").write_text(
        json.dumps({"summary": summary, "reconciliation": reconciliation,
                    "duplicates_dropped": duplicates_dropped}, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    argparse.ArgumentParser(description="F3: extract diets from the converted documents").parse_args()
    summary = build()
    printable = {k: v for k, v in summary.items() if k != "unmapped_slots_top"}
    print(json.dumps(printable, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
