"""F6 -- the provenance artefacts of the rebuild, in v2's shapes.

The rebuild is only comparable to v2 if it declares the same things about itself. v2's ``sanitize.py`` writes three
files that the dataset tests and the anonymisation report read, and the first v3 build wrote none of them: it had
the same information (``extract_diets_log.json`` carries the reconciliation and the dropped duplicates) under
different names, which is precisely the "renamed, not added" that the schema-parity rule forbids.

  ``sanitize_log.json``      the counts of what the build did, including the note ledger (before = sum of actions)
  ``duplicates.json``        one record per duplicate / template group, in v2's key set
  ``discarded_empty.jsonl``  written by :mod:`pipeline_v3.extract_diets`, where the discard happens

It also writes ``declared_figures.json`` next to the dataset (the document is its render), so the figures cannot drift
from the data: the builder emits them and ``pipeline/tests/test_dataset.py`` checks them back against the files.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import paths
else:
    from . import paths

DOC = Path(__file__).resolve().parents[3] / "docs" / "data" / "V3_PROVENANCE.md"


def _jl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    diets = _jl(out_dir / "diets.jsonl")
    meals = _jl(out_dir / "meals.jsonl")
    discarded = _jl(out_dir / "discarded_empty.jsonl")
    log = json.loads((out_dir / "extract_diets_log.json").read_text(encoding="utf-8"))
    summary, dropped = log["summary"], log.get("duplicates_dropped", [])

    # ---------------------------------------------------------------- duplicates.json
    # Two kinds, and v2's shape distinguishes them with `same_client`: a byte-identical document of the SAME client
    # is a duplicate and one copy is dropped; the same meal set across DIFFERENT clients is a template, and both
    # members are kept (dropping one would change the leave-one-out query set) and marked with a template group.
    # Only DIET-level duplicates go in this ledger, because v2's shape identifies members by diet id. The
    # byte-identical DOCUMENTS dropped earlier never became diets and have no id; they stay recorded, with their
    # file names, in extract_diets_log.json, and their count is in `counts.duplicate_documents_dropped` below.
    groups: list[dict] = []
    # The content-level duplicates dropped by merge_meta. Two different documents whose MEAL SET is identical are
    # the same diet however their bytes differ, and they are the majority of the ledger (43 groups against the
    # byte-identical ones): leaving them out would under-report what the build removed.
    merge_log = out_dir / "merge_meta_log.json"
    if merge_log.exists():
        by_signature: dict[str, list[dict]] = collections.defaultdict(list)
        for row in json.loads(merge_log.read_text(encoding="utf-8")).get("duplicates_detail", []):
            by_signature[row["meals_signature"]].append(row)
        for signature, rows in sorted(by_signature.items()):
            groups.append({"meals_sha1": signature, "kept": rows[0]["kept"],
                           "dropped": [r["dropped"] for r in rows],
                           "clients": sorted({r["kept"].split("::")[0] for r in rows}
                                             | {r["dropped"].split("::")[0] for r in rows}),
                           "same_client": all(r["same_client"] for r in rows),
                           "template_group_id": None if all(r["same_client"] for r in rows) else signature})

    # A cross-client duplicate group is ALSO a template group -- the same signature seen from the two ends -- so a
    # template is only added when the signature is not already in the ledger. Emitting both views listed 28 groups
    # twice and turned 43 real groups into 71.
    seen_signatures = {g["meals_sha1"] for g in groups}
    by_template: dict[str, list[dict]] = collections.defaultdict(list)
    for d in diets:
        tid = d["meta"].get("template_group_id")
        if tid and tid not in seen_signatures:
            by_template[tid].append(d)
    for tid, members in sorted(by_template.items()):
        ids = sorted(m["id"] for m in members)
        groups.append({"meals_sha1": tid, "kept": ids, "dropped": [],
                       "clients": sorted({m["meta"]["client_code"] for m in members}), "same_client": False,
                       "template_group_id": tid})
    (out_dir / "duplicates.json").write_text(json.dumps(groups, ensure_ascii=False, indent=1), encoding="utf-8",
                                             newline="\n")

    # ---------------------------------------------------------------- sanitize_log.json
    notes_kept = sum(len(d["notes"]) for d in diets) + sum(len(d["notes"]) for d in discarded)
    notes_excluded = summary.get("notes_dropped_prescribing_an_excluded_substance", 0)
    counts = {
        "input_diets": summary["documents_in"],
        "discarded_empty_meals": len(discarded),
        "discarded_empty_after_link_cleaning": 0,
        "discarded_short_text": 0,
        "duplicate_documents_dropped": len(dropped),      # byte-identical documents, before any diet id exists
        "duplicate_groups": len(groups),
        "duplicates_dropped": sum(len(g["dropped"]) for g in groups),
        "duplicate_groups_same_client": sum(1 for g in groups if g["same_client"]),
        "template_groups_cross_client": sum(1 for g in groups if not g["same_client"]),
        "output_diets": len(diets),
        "output_diets_with_template_group": sum(1 for d in diets if d["meta"].get("template_group_id")),
        "output_meals": len(meals),
        "slot_sections_expanded": summary["line_stats"].get("slot_headers", 0),
        "items_with_links_cleaned": summary["line_stats"].get("item_lines", 0),
        "diets_goal_inferred": sum(1 for d in diets if d["meta"]["goal_inferred"]),
        "diets_with_method_declared": sum(1 for d in diets if d["meta"].get("method")),
        "unmapped_slot_occurrences": summary["unmapped_slot_occurrences"],
        "unmapped_slot_distinct": summary["unmapped_slot_distinct"],
    }
    log_out = {
        "counts": counts,
        # The note ledger has to balance: before = kept + every reason one was not kept. It is the invariant
        # `test_notes_after_matches_log` checks, and it is what makes "zero silent loss" verifiable for notes.
        "notes": {
            "total_before": notes_kept + notes_excluded,
            "total_after": notes_kept,
            "actions": {"kept": notes_kept, "dropped_excluded_substance": notes_excluded},
            "diets_with_notes_before": sum(1 for d in diets + discarded if d["notes"]),
            "diets_with_notes_after": sum(1 for d in diets if d["notes"]),
        },
        "slots_after": summary["slots_used"],
        "goals_after_main_final": dict(collections.Counter(d["meta"]["goal"] for d in diets).most_common()),
        "methods_after_final": dict(collections.Counter(d["meta"].get("method") or "sin_metodo" for d in diets).most_common()),
        "goal_inferred_final": counts["diets_goal_inferred"],
    }
    (out_dir / "sanitize_log.json").write_text(json.dumps(log_out, ensure_ascii=False, indent=1), encoding="utf-8",
                                               newline="\n")
    return {"duplicate_groups": len(groups), "discarded_empty": len(discarded), **counts}


def _other_bucket_figures(out_dir: Path) -> dict:
    """How much real content lives in the non-composable OTHER bucket, and how many diets that makes unusable.

    Published because it is a limit of the delivered system, not an implementation detail: the diets counted in
    ``diets_excluded_irrepresentable`` are removed from the evaluation on purpose (retrieval_benchmark.
    IRREPRESENTABLE_SHARE), and a number removed from a denominator has to be visible.
    """
    total: dict[str, int] = collections.Counter()
    other: dict[str, int] = collections.Counter()
    for i in _jl(out_dir / "diet_items.jsonl"):
        total[i["diet_id"]] += 1
        if i["meal_slot"] == "OTHER":
            other[i["diet_id"]] += 1
    shares = {d: other.get(d, 0) / n for d, n in total.items() if n}
    return {
        "items_total": sum(total.values()),
        "items_in_other_bucket": sum(other.values()),
        "diets_with_content_in_other": sum(1 for v in shares.values() if v > 0),
        "diets_excluded_irrepresentable": sum(1 for v in shares.values() if v > 0.5),
        "diets_entirely_in_other": sum(1 for v in shares.values() if v == 1.0),
    }


def unservable_goals(out_dir: Path) -> dict:
    """Goals the case base cannot serve, declared in the dataset instead of discovered by the user.

    Two categorical conditions, the same two the use case raises on: no diet at all with that goal, or no diet whose
    content is composable (everything either in the non-composable OTHER bucket or unmapped). Written as an artefact
    so the catalogue states it up front -- `GoalNotServableError` names the goal at request time, and this file is
    where the reason and the count live.
    """
    scorable: dict[str, int] = collections.Counter()
    for i in _jl(out_dir / "diet_items.jsonl"):
        if i["meal_slot"] != "OTHER" and i.get("normalized_key"):
            scorable[i["diet_id"]] += 1
    diets = _jl(out_dir / "diets.jsonl")
    total: dict[str, int] = collections.Counter()
    usable: dict[str, int] = collections.Counter()
    for d in diets:
        goal = d["meta"]["goal"]
        total[goal] += 1
        if scorable.get(d["id"], 0):
            usable[goal] += 1
    known = ["volumen_masa", "definicion_grasa", "cetosis_keto", "ayuno_intermitente", "descarga_carga",
             "hipocalorica", "alta_en_fibra", "mantenimiento", "sin_clasificar"]
    rows = []
    for goal in known:
        n, u = total.get(goal, 0), usable.get(goal, 0)
        if n == 0:
            reason = "no hay ninguna dieta con este objetivo en el corpus"
        elif u == 0:
            reason = "ninguna de sus dietas tiene contenido componible (todo en el cajón OTHER o sin mapear)"
        elif u < 3:
            reason = "menos de tres dietas componibles: el consenso no puede formarse"
        else:
            continue
        rows.append({"goal": goal, "diets": n, "usable_diets": u, "reason": reason})
    out = {"criterion": "un objetivo es no servible si no tiene dietas, o ninguna componible, o menos de tres componibles",
           "goals": rows, "servable": [{"goal": g, "diets": total[g], "usable_diets": usable[g]}
                                       for g in known if total.get(g) and usable.get(g, 0) >= 3]}
    (out_dir / "unservable_goals.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                                   encoding="utf-8", newline="\n")
    return out


def write_declared_figures(out_dir: Path | None = None) -> dict:
    """The published figures of the rebuild, emitted from the data so they cannot drift from it."""
    out_dir = out_dir or paths.dataset_dir_v3()
    diets, meals = _jl(out_dir / "diets.jsonl"), _jl(out_dir / "meals.jsonl")
    profiles = _jl(out_dir / "profiles.jsonl")
    san = json.loads((out_dir / "sanitize_log.json").read_text(encoding="utf-8"))
    dup = json.loads((out_dir / "duplicates.json").read_text(encoding="utf-8"))
    vr = json.loads((out_dir / "validated_rules.json").read_text(encoding="utf-8"))
    loo = json.loads((out_dir / "loo_eligibility.json").read_text(encoding="utf-8"))
    # v3 builds profiles with extract_profiles, not v2's build_profiles, so the carry-over count comes from the
    # profiles themselves. Same figure, read from the data rather than from a log the rebuild does not produce.
    rules = json.loads((out_dir / "rules.json").read_text(encoding="utf-8"))
    private = out_dir / "_private" / "health_profiles.jsonl"
    figures = {
        "input_diets": san["counts"]["input_diets"],
        "discarded_empty": len(_jl(out_dir / "discarded_empty.jsonl")),
        "duplicate_groups": len(dup),
        "duplicates_dropped": sum(len(g["dropped"]) for g in dup),
        "template_groups": sum(1 for g in dup if not g["same_client"]),
        "output_diets": len(diets),
        "output_meals": len(meals),
        "clients_with_diets": len({d["meta"]["client_code"] for d in diets}),
        "profiles": len(profiles),
        "empty_profiles": sum(1 for p in profiles if p["empty_profile"]),
        "unmapped_profiles": sum(1 for p in profiles if p["unmapped"]),
        "health_profiles": len(_jl(private)),
        "goal_inferred": sum(1 for d in diets if d["meta"]["goal_inferred"]),
        "shared_diet": sum(1 for d in diets if d["meta"]["shared_diet"]),
        "notes_before": san["notes"]["total_before"],
        "notes_after": san["notes"]["total_after"],
        "notes_after_in_final_diets": sum(len(d["notes"]) for d in diets),
        "slot_sections_expanded": san["counts"]["slot_sections_expanded"],
        "items_with_links_cleaned": san["counts"]["items_with_links_cleaned"],
        "distinct_rules": len(rules) if isinstance(rules, list) else len(rules.get("rules", [])),
        "validated_rules": len(vr["rules"]),
        "validated_kept": sum(1 for r in vr["rules"] if r["status"] == "kept"),
        "validated_retired": sum(1 for r in vr["rules"] if r["status"] == "retired"),
        "loo_eligible_clients": loo["all_diets"]["eligible_ge2"]["clients"],
        "loo_eligible_complete_clients": loo["all_diets"]["eligible_ge2_complete_demographics"]["clients"],
        "loo_queries_complete": loo["all_diets"]["eligible_ge2_complete_demographics"]["queries"],
        "loo_pairs_complete": loo["all_diets"]["eligible_ge2_complete_demographics"]["pairs"],
        "loo_excl_template_complete_clients": loo["excluding_template_groups"]["eligible_ge2_complete_demographics"]["clients"],
        "loo_excl_template_complete_queries": loo["excluding_template_groups"]["eligible_ge2_complete_demographics"]["queries"],
        "field_carryover_profiles": sum(1 for p in profiles if p.get("field_carryover_suspected")),
        # The generic bucket, published as a declared limit of the system rather than left implicit in the metric.
        **_other_bucket_figures(out_dir),
    }
    body = (
        "# Procedencia de dataset-v3\n\n"
        "Cifras declaradas de la reconstrucción, **emitidas por el propio build** (`pipeline_v3/provenance.py`) y\n"
        "verificadas contra los ficheros por `pipeline/tests/test_dataset.py`. El equivalente para el v2 es el bloque\n"
        "de la memoria (informe de anonimizacion).\n\n"
        "<!-- declared-figures\n" + json.dumps(figures, ensure_ascii=False) + "\n-->\n\n"
        "| Magnitud | Valor |\n|---|---|\n"
        + "".join(f"| `{k}` | {v} |\n" for k, v in figures.items())
    )
    # LAS CIFRAS VIVEN CON EL DATASET, no con el documento. El bloque `declared-figures` estaba solo dentro de un
    # .md del arbol de codigo, asi que la comprobacion de deriva dependia de que ese documento se publicara. Ahora
    # la fuente de verdad es este JSON, que se queda al lado de los ficheros que describe; el .md es su render.
    (out_dir / "declared_figures.json").write_text(json.dumps(figures, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8", newline="\n")
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(body, encoding="utf-8", newline="\n")
    return figures


def main() -> None:
    print(json.dumps(build(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
