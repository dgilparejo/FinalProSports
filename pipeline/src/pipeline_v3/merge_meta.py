"""Denormalise the profile into every diet's ``meta``, as v2 does.

The v2 schema carries the client's sex, age bucket, activity level and intolerance flag inside each diet's ``meta``
so that retrieval and the rule miner can read a diet without joining. The v3 extractor writes diets before profiles
exist (the profile needs the diet count), so this runs last and fills the same fields in.

It also adds the two structural flags v2 computes over the whole corpus -- ``shared_diet`` and ``template_group_id``:
the professional gives the same diet to more than one client, and both the evaluation's hold-out and the duplicate
report depend on knowing which those are.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline import excluded
    from pipeline_v3 import paths
else:
    from pipeline import excluded
    from . import paths

PROFILE_TO_META = ("sex", "age", "age_bucket", "activity_level", "activity_level_reported",
                   "has_intolerances", "has_allergies", "suspicious_demographics", "is_athlete")


def _signature(meals: dict) -> str:
    """A diet's content fingerprint: the same meal sets given to two clients hash to the same value."""
    payload = json.dumps({k: sorted(v) for k, v in sorted(meals.items())}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _jl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    diets_path = out_dir / "diets.jsonl"
    profiles = {}
    for line in (out_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            profiles[record["client_code"]] = record

    diets = [json.loads(line) for line in diets_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # Content-level deduplication, with v2's criterion so the two corpora stay comparable.
    #
    # v2's sanitize.py groups diets by the SHA-1 of their meal set and keeps one per group: 63 groups, 71 diets
    # dropped, 32 of them same-client. Deduplicating v3 only by source-file bytes left 16 content-identical
    # same-client pairs that v2 would have removed, and kept every cross-client copy where v2 keeps one. Any
    # harness figure compared across the two would then be measuring that difference as if it were the engine.
    # The group is recorded whole, so which clients received the same diet is not lost -- it moves to
    # template_clients on the survivor, which is exactly where v2 puts it.
    by_signature: dict[str, list[dict]] = collections.defaultdict(list)
    for diet in diets:
        by_signature[_signature(diet["meals"])].append(diet)

    dropped: list[dict] = []
    keep: list[dict] = []
    for signature, group in by_signature.items():
        group.sort(key=lambda d: (d["meta"]["client_code"], d["meta"]["diet_version"]))
        survivor, rest = group[0], group[1:]
        keep.append(survivor)
        for other in rest:
            dropped.append({"kept": survivor["id"], "dropped": other["id"],
                            "same_client": other["meta"]["client_code"] == survivor["meta"]["client_code"],
                            "meals_signature": signature})
    diets = [d for d in diets if any(d is k for k in keep)]
    diets.sort(key=lambda d: (d["meta"]["client_code"], d["meta"]["diet_version"]))

    signatures: dict[str, list[str]] = collections.defaultdict(list)
    for signature, group in by_signature.items():
        signatures[signature] = sorted({d["meta"]["client_code"] for d in group})

    for diet in diets:
        meta = diet["meta"]
        profile = profiles.get(meta["client_code"], {})
        for field in PROFILE_TO_META:
            meta[field] = profile.get(field)
        if meta.get("sex") is None:
            meta["sex"] = "?"
        if not meta.get("age_bucket"):
            meta["age_bucket"] = "edad_NA"
        signature = _signature(diet["meals"])
        clients = signatures[signature]
        meta["shared_diet"] = len(clients) > 1
        meta["shared_diet_signals"] = ["identical_meal_set"] if len(clients) > 1 else []
        meta["template_group_id"] = signature if len(clients) > 1 else None
        meta["template_clients"] = clients if len(clients) > 1 else []

    with open(diets_path, "w", encoding="utf-8", newline="\n") as handle:
        for diet in diets:
            handle.write(json.dumps(diet, ensure_ascii=False) + "\n")

    # meals.jsonl carries the same meta, so it is rewritten from the updated diets.
    with open(out_dir / "meals.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for diet in diets:
            for slot, items in diet["meals"].items():
                meta = dict(diet["meta"])
                # v2's meal meta names these `diet_id` and `meal_slot`, and load_postgres reads them by those
                # names. Calling the slot `slot` was enough for everything in this package and broke the loader.
                meta["diet_id"] = diet["id"]
                meta["meal_slot"] = slot
                meta["slot"] = slot
                meta["item_count"] = len(items)
                handle.write(json.dumps({
                    "id": f"{diet['id']}::{slot}",
                    "text": f"[Perfil {meta.get('sex', '?')} {meta.get('age_bucket')}, objetivo {meta.get('goal')}] "
                            f"{slot}: " + " | ".join(excluded.redact(i) for i in items),
                    "meta": meta,
                }, ensure_ascii=False) + "\n")

    # The profiles were counted against the diet file as it stood BEFORE this step, and this step is what drops the
    # content-level duplicates: 1.253 diets became 1.208 while every profile kept the old number. `diet_count` is
    # documented as the count in the CLEAN corpus, so it is recomputed here, where the corpus stops changing.
    # The pre-drop figure is not lost -- it stays in `diet_count_raw`.
    profiles_path = out_dir / "profiles.jsonl"
    if profiles_path.exists():
        final_counts: collections.Counter = collections.Counter(d["meta"]["client_code"] for d in diets)
        rows = [json.loads(line) for line in profiles_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            row["diet_count"] = final_counts.get(row["client_code"], 0)
            row["diet_count_stored"] = final_counts.get(row["client_code"], 0)
        with open(profiles_path, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    shared = sum(1 for d in diets if d["meta"]["shared_diet"])
    summary = {
        "diets": len(diets),
        "duplicates_dropped": len(dropped),
        "duplicate_groups": sum(1 for g in by_signature.values() if len(g) > 1),
        "duplicate_groups_same_client": sum(1 for g in by_signature.values() if len(g) > 1
                                            and len({d["meta"]["client_code"] for d in g}) == 1),
        "duplicate_groups_cross_client": sum(1 for g in by_signature.values() if len(g) > 1
                                             and len({d["meta"]["client_code"] for d in g}) > 1),
        "duplicates_detail": dropped,
        "profile_fields_merged": list(PROFILE_TO_META),
        "diets_with_sex": sum(1 for d in diets if d["meta"]["sex"] in ("M", "F")),
        "diets_with_age": sum(1 for d in diets if d["meta"]["age"]),
        "shared_diets": shared,
        "template_groups": len({d["meta"]["template_group_id"] for d in diets if d["meta"]["template_group_id"]}),
    }
    # The private diet-id map, in the SHAPE v2 uses: one entry per diet id, with the same field names. v3 was
    # writing a folder->code map under that file name, so test_ids_are_stable_against_private_map could not read
    # it at all. The folder map keeps its own file.
    private = out_dir / "_private"
    private.mkdir(parents=True, exist_ok=True)
    id_map = {
        diet["id"]: {
            "client_code": diet["meta"]["client_code"],
            "diet_version": diet["meta"]["diet_version"],
            "source_index": index,
            "original_id": diet["id"],
            "file_on_disk": diet["meta"].get("source_rel"),
            "source_sha1": diet["meta"].get("source_sha1"),
            "doc_date": diet["meta"].get("doc_date"),
        }
        for index, diet in enumerate(diets)
    }
    # The discarded documents belong in the map too. It is the ledger that makes an id traceable back to the file
    # it came from, and a document that produced no diet is exactly the case someone will need to trace.
    for index, row in enumerate(dropped, start=len(diets) + 10_000):
        # A diet dropped HERE as a content duplicate is still a document that existed. The duplicates ledger names
        # it, so the id map has to resolve it, or the ledger points at ids nothing can trace.
        id_map.setdefault(row["dropped"], {
            "client_code": row["dropped"].split("::")[0], "diet_version": None, "source_index": index,
            "original_id": row["dropped"], "file_on_disk": None, "source_sha1": None, "doc_date": None,
            "duplicate_of": row["kept"],
        })
    discarded = _jl(out_dir / "discarded_empty.jsonl")
    for index, diet in enumerate(discarded, start=len(diets)):
        id_map[diet["id"]] = {
            "client_code": diet["meta"]["client_code"], "diet_version": diet["meta"]["diet_version"],
            "source_index": index, "original_id": diet["id"], "file_on_disk": diet["meta"].get("source_rel"),
            "source_sha1": diet["meta"].get("source_sha1"), "doc_date": None, "discarded": True,
        }
    (private / "id_map.json").write_text(json.dumps(id_map, ensure_ascii=False, indent=1),
                                         encoding="utf-8", newline="\n")

    (out_dir / "merge_meta_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                 encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    argparse.ArgumentParser(description="merge the profile into each diet's meta").parse_args()
    print(json.dumps(build(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
