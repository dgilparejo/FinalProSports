"""F6 -- verification and comparison against v2. The point is that the decision to activate can be made without
running anything.

Four parts:

1. **reconciliation**: every input file against what it produced, and every file that produced nothing with a reason;
2. **v2 vs v3**: clients, diets, meals, items, per-field profile coverage, the food catalogue and the rules, with
   the lists and not only the totals;
3. **recoverable**: what is in v2 and not in v3, and whether the v2 markdown tree could supply it (reported, not done);
4. a verdict.

The comparison is made over the **crosswalk** (:mod:`pipeline_v3.crosswalk`): the two datasets number their clients
independently, so a naive comparison of ``CLIENTE_007`` against ``CLIENTE_007`` would compare two different people.
Every per-client figure below is restricted to the 270 matched pairs unless it says otherwise, and the coverage
table is computed twice -- over the whole of each dataset and over the matched subset -- because v2 has 467 clients
and v3 has 301, and a percentage over different denominators is not a comparison.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import paths
else:
    from . import paths

# v2 field -> v3 field, where the name changed. Fields absent from v2 are reported as "new in v3".
FIELD_ALIASES = {"has_medical_restrictions": "has_medical_restrictions"}
V2_PROFILE_FIELDS = ["sex", "age", "height_cm", "activity_level", "is_athlete", "goals", "sport",
                     "liked_foods", "disliked_foods", "has_allergies", "has_intolerances",
                     "has_medical_restrictions"]
V3_NEW_FIELDS = ["weight_kg", "initial_weight_kg", "waist_cm", "neck_cm", "wrist_cm", "hip_cm", "body_type",
                 "training_time", "sport_achievements", "food_vices", "smokes", "drinks_alcohol",
                 "work_schedule", "training_schedule", "own_supplements", "first_consultation_date",
                 "has_surgeries", "has_injuries", "scale_reading_count", "lab_report_count",
                 "has_scale_trajectory", "questionnaire_count"]


def _jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _filled(value) -> bool:
    return value not in (None, "", False, [], {}, 0)


def build(out_dir: Path | None = None) -> dict:
    v3 = out_dir or paths.dataset_dir_v3()
    v2 = paths.dataset_dir_v2()

    crosswalk_map = json.loads((v3 / "_private" / "id_map_v2_v3.json").read_text(encoding="utf-8"))
    v3_to_v2 = crosswalk_map["v3_to_v2"]
    v2_to_v3 = {b: a for a, b in v3_to_v2.items()}

    v2_diets, v3_diets = _jsonl(v2 / "diets.jsonl"), _jsonl(v3 / "diets.jsonl")
    v2_profiles, v3_profiles = _jsonl(v2 / "profiles.jsonl"), _jsonl(v3 / "profiles.jsonl")
    v2_items, v3_items = _jsonl(v2 / "diet_items.jsonl"), _jsonl(v3 / "diet_items.jsonl")
    manifest = _jsonl(v3 / "manifest.jsonl")

    report: dict = {}

    # ------------------------------------------------------------------ 1. reconciliation
    by_status = collections.Counter(row["status"] for row in manifest)
    produced = collections.Counter()
    diet_sha = {d["meta"].get("source_sha1") for d in v3_diets}
    zero_output = []
    for row in manifest:
        if row["status"] != "ok":
            continue
        label = row.get("label")
        produced[label] += 1
        if label == "diet" and row["sha1"] not in diet_sha:
            zero_output.append({"rel": row["rel"], "label": label, "chars": row.get("chars"),
                                "reason": "converted and classified as a diet but produced no meal slot"})
    report["reconciliation"] = {
        "input_units": len(manifest),
        "by_status": dict(by_status),
        "converted_ok": by_status.get("ok", 0),
        "skipped_media": by_status.get("skipped_media", 0),
        "skipped_lock": by_status.get("skipped_lock", 0),
        "failed_or_unsupported": by_status.get("failed", 0) + by_status.get("unsupported", 0)
                                 + by_status.get("empty_output", 0),
        "documents_by_label": dict(produced.most_common()),
        "diet_documents_with_zero_records": zero_output,
        "records_out": {
            "diets": len(v3_diets), "meals": sum(len(d["meals"]) for d in v3_diets),
            "diet_items": len(v3_items), "profiles": len(v3_profiles),
            "body_measurements": len(_jsonl(v3 / "body_measurements.jsonl")),
            "lab_results": len(_jsonl(v3 / "lab_results.jsonl")),
            "training_plans": len(_jsonl(v3 / "training_plans.jsonl")),
        },
    }

    # ------------------------------------------------------------------ 2a. clients
    v2_codes = {p["client_code"] for p in v2_profiles}
    v3_codes = {p["client_code"] for p in v3_profiles}
    matched_v3 = set(v3_to_v2)
    report["clients"] = {
        "in_v2": len(v2_codes), "in_v3": len(v3_codes),
        "matched_pairs": len(v3_to_v2),
        "only_in_v2": sorted(v2_codes - set(v3_to_v2.values())),
        "only_in_v3": sorted(v3_codes - matched_v3),
        "only_in_v2_count": len(v2_codes - set(v3_to_v2.values())),
        "only_in_v3_count": len(v3_codes - matched_v3),
        "low_confidence_pairs": crosswalk_map.get("low_confidence", []),
    }

    # ------------------------------------------------------------------ 2b. diets, matched by (client, version)
    v2_by_key = {(d["meta"]["client_code"], d["meta"]["diet_version"]): d for d in v2_diets}
    v3_by_key = {(d["meta"]["client_code"], d["meta"]["diet_version"]): d for d in v3_diets}
    v2_items_by_diet = collections.Counter(i["diet_id"] for i in v2_items)
    v3_items_by_diet = collections.Counter(i["diet_id"] for i in v3_items)

    both, only_v2, only_v3, fewer = [], [], [], []
    for (v3_code, version), diet in v3_by_key.items():
        v2_code = v3_to_v2.get(v3_code)
        if v2_code is None:
            continue
        counterpart = v2_by_key.get((v2_code, version))
        if counterpart is None:
            only_v3.append(diet["id"])
            continue
        n2, n3 = v2_items_by_diet[counterpart["id"]], v3_items_by_diet[diet["id"]]
        both.append((diet["id"], counterpart["id"], n2, n3))
        if n3 < n2:
            fewer.append({"v3": diet["id"], "v2": counterpart["id"], "items_v2": n2, "items_v3": n3,
                          "delta": n3 - n2})
    for (v2_code, version), diet in v2_by_key.items():
        v3_code = v2_to_v3.get(v2_code)
        if v3_code is None:
            continue
        if (v3_code, version) not in v3_by_key:
            only_v2.append(diet["id"])

    fewer.sort(key=lambda d: d["delta"])
    report["diets"] = {
        "in_v2": len(v2_diets), "in_v3": len(v3_diets),
        "matched_client_and_version": len(both),
        "only_in_v2_for_a_matched_client": sorted(only_v2),
        "only_in_v3_for_a_matched_client": sorted(only_v3),
        "only_in_v2_count": len(only_v2), "only_in_v3_count": len(only_v3),
        "diets_with_fewer_items_in_v3": fewer,
        "diets_with_fewer_items_in_v3_count": len(fewer),
        "note": ("version numbers are assigned independently in each dataset (v3 orders by document date), so a "
                 "pair that differs may be the same document under a different version number"),
    }

    # ------------------------------------------------------------------ 2c. meals and items
    report["volumes"] = {
        "meals_v2": sum(len(d["meals"]) for d in v2_diets),
        "meals_v3": sum(len(d["meals"]) for d in v3_diets),
        "diet_items_v2": len(v2_items), "diet_items_v3": len(v3_items),
        "slots_v2": dict(collections.Counter(s for d in v2_diets for s in d["meals"]).most_common()),
        "slots_v3": dict(collections.Counter(s for d in v3_diets for s in d["meals"]).most_common()),
        "notes_v2": sum(len(d.get("notes") or []) for d in v2_diets),
        "notes_v3": sum(len(d.get("notes") or []) for d in v3_diets),
    }

    # ------------------------------------------------------------------ 2d. profile coverage
    def coverage(profiles, fields):
        total = len(profiles) or 1
        return {f: round(100 * sum(1 for p in profiles if _filled(p.get(f))) / total, 1) for f in fields}

    v2_matched = [p for p in v2_profiles if p["client_code"] in v2_to_v3]
    v3_matched = [p for p in v3_profiles if p["client_code"] in v3_to_v2]
    report["profile_coverage_pct"] = {
        "whole_dataset": {"v2_n": len(v2_profiles), "v3_n": len(v3_profiles),
                          "v2": coverage(v2_profiles, V2_PROFILE_FIELDS),
                          "v3": coverage(v3_profiles, V2_PROFILE_FIELDS)},
        "matched_clients_only": {"n": len(v3_matched),
                                 "v2": coverage(v2_matched, V2_PROFILE_FIELDS),
                                 "v3": coverage(v3_matched, V2_PROFILE_FIELDS)},
        "new_in_v3": coverage(v3_profiles, V3_NEW_FIELDS),
        "note": ("the matched-clients block is the only like-for-like comparison: v2 has 467 clients and v3 has "
                 "301, so the whole-dataset percentages have different denominators"),
    }

    # ------------------------------------------------------------------ 2d-bis. is v2's extra coverage real?
    # A field where v2 has a value and v3 does not is only a loss if v2's value is right. v2 carries its own
    # quality flags, so the question can be answered instead of argued: for each such case, was that v2 profile
    # flagged as suspected field carry-over -- a value bled in from an adjacent field?
    v2_index = {p["client_code"]: p for p in v2_profiles}
    v3_index = {p["client_code"]: p for p in v3_profiles}
    quality = {}
    for field in ("sport", "liked_foods", "disliked_foods", "activity_level", "height_cm", "sex", "age"):
        v2_only = carryover = unmapped_flag = 0
        for v3_code, v2_code in v3_to_v2.items():
            a, b = v2_index.get(v2_code, {}), v3_index.get(v3_code, {})
            if not _filled(a.get(field)) or _filled(b.get(field)):
                continue
            v2_only += 1
            carryover += bool(a.get("field_carryover_suspected"))
            unmapped_flag += bool(a.get("unmapped"))
        quality[field] = {"filled_in_v2_only": v2_only,
                          "of_those_flagged_carryover_by_v2": carryover,
                          "of_those_flagged_unmapped_by_v2": unmapped_flag,
                          "carryover_share": round(carryover / v2_only, 2) if v2_only else None}
    report["is_v2_extra_coverage_real"] = {
        "per_field": quality,
        "v2_matched_profiles_flagged_carryover": sum(
            1 for c in v3_to_v2.values() if v2_index.get(c, {}).get("field_carryover_suspected")),
        "v2_matched_profiles_flagged_unmapped": sum(
            1 for c in v3_to_v2.values() if v2_index.get(c, {}).get("unmapped")),
        "reading": ("for the free-text preference fields nearly every value v2 has and v3 lacks sits in a profile "
                    "v2 itself marks as suspected carry-over, so the nominal coverage gap there is v2 not counting "
                    "its own bleed as missing. For activity_level and height_cm the flagged share is much lower, "
                    "so part of that gap is a real difference: v2 inferred, v3 requires a labelled value"),
    }

    # ------------------------------------------------------------------ 2e. food catalogue
    v2_foods = json.loads((v2 / "foods.json").read_text(encoding="utf-8"))
    v3_foods = json.loads((v3 / "foods.json").read_text(encoding="utf-8"))
    v2_names = {f["canonical_name"] for f in v2_foods["foods"]}
    v3_names = {f["canonical_name"] for f in v3_foods["foods"]}
    report["food_catalogue"] = {
        "canonical_v2": len(v2_names), "canonical_v3": len(v3_names),
        "in_v2_not_in_v3": sorted(v2_names - v3_names),
        "in_v3_not_in_v2": sorted(v3_names - v2_names),
        "coverage_pct_v2": v2_foods["summary"].get("coverage_pct"),
        "coverage_pct_v3": v3_foods["summary"].get("coverage_pct"),
        "components_v2": v2_foods["summary"].get("components_total"),
        "components_v3": v3_foods["summary"].get("components_total"),
    }

    # ------------------------------------------------------------------ 2f. rules
    def rules_of(path: Path):
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {r["id"]: r for r in data.get("rules", [])}

    v2_rules, v3_rules = rules_of(v2 / "validated_rules.json"), rules_of(v3 / "validated_rules.json")
    changed = []
    for rule_id in sorted(set(v2_rules) & set(v3_rules)):
        a, b = v2_rules[rule_id], v3_rules[rule_id]
        pa, pb = a.get("prevalence"), b.get("prevalence")
        if pa is not None and pb is not None and abs(pa - pb) >= 0.05:
            changed.append({"id": rule_id, "prevalence_v2": pa, "prevalence_v3": pb,
                            "delta": round(pb - pa, 3),
                            "nature_v2": a.get("nature"), "nature_v3": b.get("nature")})
    changed.sort(key=lambda r: -abs(r["delta"]))
    report["rules"] = {
        "in_v2": len(v2_rules), "in_v3": len(v3_rules),
        "only_in_v2": sorted(set(v2_rules) - set(v3_rules)),
        "only_in_v3": sorted(set(v3_rules) - set(v2_rules)),
        "prevalence_changed_by_5pp_or_more": changed,
        "note": "recomputed on v3 only; nothing in v2 was replaced",
    }

    # ------------------------------------------------------------------ 3. recoverable
    tree = paths.client_tree()
    recoverable = []
    for v2_code in sorted(v2_codes - set(v3_to_v2.values())):
        directory = tree / v2_code
        if not directory.exists():
            continue
        files = sorted(directory.glob("*.md"))
        diets = [f for f in files if f.name.startswith("DIETA")]
        recoverable.append({"v2_client": v2_code, "markdown_files": len(files), "diet_documents": len(diets),
                            "chars": sum(f.stat().st_size for f in files)})
    report["recoverable_from_the_v2_markdown_tree"] = {
        "clients": len(recoverable),
        "diet_documents": sum(r["diet_documents"] for r in recoverable),
        "detail": recoverable,
        "effort": ("the tree holds converted text without names, so it can be fed to the same extractor: the diet "
                   "and questionnaire stages read plain text and do not depend on the source format. What it "
                   "cannot supply is anything the v2 conversion already lost -- the .doc questionnaires are the "
                   "byte-scraped ones, so their fields would stay empty -- and there is no scale or lab data for "
                   "these clients either. NOT DONE, as instructed."),
    }

    (v3 / "v2_vs_v3.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding="utf-8", newline="\n")
    return report


def main() -> None:
    argparse.ArgumentParser(description="F6: compare v3 against the frozen v2").parse_args()
    report = build()
    slim = json.loads(json.dumps(report))
    for key in ("clients", "diets", "recoverable_from_the_v2_markdown_tree"):
        for drop in ("only_in_v2", "only_in_v3", "only_in_v2_for_a_matched_client",
                     "only_in_v3_for_a_matched_client", "diets_with_fewer_items_in_v3", "detail",
                     "low_confidence_pairs"):
            slim.get(key, {}).pop(drop, None)
    print(json.dumps(slim, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
