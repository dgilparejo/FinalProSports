"""Run the existing E1 chain against the v3 dataset, with the frozen v2 dataset protected.

The E1 tools take ``--parsed`` / ``--foods`` / ``--out``, but three of them also write side artefacts to a
**hardcoded** ``DATASET_DIR`` (``rules_evaluability.json``, ``food_attributes_dubious.json``,
``normalize_diets_log.json``, ``food_catalog_unmapped.json``, ``build_food_catalog_log.json``,
``excluded_substances.json``). Passing v3 paths on the command line is therefore not enough: running the chain that
way silently overwrote six files inside the frozen v2 dataset and broke its test suite.

So the chain is run here as subprocesses with ``FPS_DATASET_DIR`` pointed at the v3 directory, which is what
``DATASET_DIR`` resolves from. Then every write lands in v3 whether the tool was told about it or not, and v2 is
untouched by construction rather than by remembering.

Usage::

    python pipeline/src/pipeline_v3/run_e1.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import paths
else:
    from . import paths

# Files the v2 dataset must still have, byte for byte, after this runs. Checked before and after.
V2_GUARDED = (
    "foods.json", "diets.jsonl", "diet_items.jsonl", "profiles.jsonl", "meals.jsonl", "parsed_items.jsonl",
    "rules_evaluability.json", "food_attributes_dubious.json", "normalize_diets_log.json",
    "food_catalog_unmapped.json", "build_food_catalog_log.json", "excluded_substances.json",
    "validated_rules.json", "rules.json", "archetypes.json", "plausibility_envelope.json",
)

STEPS = [
    ("parse_items", ["pipeline/src/pipeline/parse_items.py"]),
    ("build_food_catalog", ["pipeline/src/pipeline/build_food_catalog.py", "--apply"]),
    ("analyze_rules", ["pipeline/src/data_tools/analyze_rules.py"]),
    ("build_validated_rules", ["pipeline/src/data_tools/build_validated_rules.py"]),
    ("enrich_catalog", ["pipeline/src/pipeline/enrich_catalog.py", "--apply"]),
    ("normalize_diets", ["pipeline/src/pipeline/normalize_diets.py"]),
    # Everything below is required by load_postgres, embed_corpus or the harness. Leaving them out is what an
    # activation attempt found: the dataset looked complete because diets/meals/items/foods were all there.
    ("loo_eligibility", ["pipeline/src/data_tools/loo_eligibility.py"]),
    ("plausibility_envelope", ["pipeline/src/pipeline/plausibility_envelope.py"]),
    ("build_canonical_notes", ["pipeline/src/pipeline/build_canonical_notes.py", "--apply"]),
    ("retrieval_text", ["pipeline/src/pipeline/retrieval_text.py"]),
    ("discriminative_power", ["pipeline/src/pipeline/discriminative_power.py"]),
    ("rotation_analysis", ["pipeline/src/pipeline/rotation_analysis.py"]),
]


def _flag_excluded_items(v3: Path) -> int:
    """Mark every item whose ORIGINAL text names an excluded substance.

    ``raw_text`` is kept verbatim on purpose -- it is the provenance the rebuild was asked to preserve -- and the
    item is already unproposable (``canonical_name`` is null, ``unmapped_reason`` is ``excluded_substance``). The
    flag exists so a consumer can filter on it without re-deriving the curated list, which is the mistake that let
    the substance out of the catalogue and into the notes in the first place.
    """
    from pipeline import excluded
    path = v3 / "diet_items.jsonl"
    if not path.exists():
        return 0
    rows, flagged = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        hit = excluded.contains(row.get("raw_text") or "") or excluded.contains(row.get("food_text") or "")
        row["contains_excluded_substance"] = bool(hit)
        flagged += bool(hit)
        rows.append(row)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return flagged


def _digests(directory: Path) -> dict[str, str]:
    out = {}
    for name in V2_GUARDED:
        path = directory / name
        if path.exists():
            out[name] = hashlib.sha1(path.read_bytes()).hexdigest()
    return out


def run(python: str | None = None) -> dict:
    v2 = paths.dataset_dir_v2()
    v3 = paths.dataset_dir_v3()
    python = python or sys.executable
    before = _digests(v2)

    env = dict(os.environ)
    env["FPS_DATASET_DIR"] = str(v3)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    results = []
    for name, argv in STEPS:
        extra: list[str] = []
        if name in ("build_validated_rules", "analyze_rules"):
            extra = ["--diets", str(v3 / "diets.jsonl"), "--out-dir", str(v3)]
        elif name == "plausibility_envelope":
            extra = ["--doc", str(v3 / "plausibility_envelope.md")]
        elif name == "rotation_analysis":
            # It writes its report to docs/ by default and would overwrite the PUBLISHED v2 one, which is the same
            # class of leak as the six dataset files: a tool writing outside the directory it was pointed at.
            extra = ["--doc", str(v3 / "rotation_analysis.md")]
        elif name == "loo_eligibility":
            extra = ["--diets", str(v3 / "diets.jsonl"), "--profiles", str(v3 / "profiles.jsonl"),
                     "--out", str(v3 / "loo_eligibility.json")]
        proc = subprocess.run([python, *argv, *extra], capture_output=True, env=env,
                              cwd=str(paths.repo_root()))
        ok = proc.returncode == 0
        results.append({"step": name, "ok": ok,
                        "stderr_tail": proc.stderr.decode("utf-8", "replace")[-400:] if not ok else ""})
        if not ok:
            break

    # The E1 tools record the path they were given, and that path carries a first name that is also a client's.
    # build_all sanitises as its last stage, but run_e1 is also run on its own, and then the leak survives -- which
    # is how validated_rules.json put the audit back in the red after a standalone rerun.
    _flag_excluded_items(v3)

    from pipeline_v3 import sanitise_artifacts
    sanitise_artifacts.build(v3)

    after = _digests(v2)
    changed = sorted(k for k in before if before.get(k) != after.get(k))
    summary = {"steps": results, "v2_files_checked": len(before), "v2_files_changed": changed,
               "v2_intact": not changed}
    (v3 / "run_e1_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                        encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    argparse.ArgumentParser(description="run the E1 chain against v3 without touching v2").parse_args()
    summary = run()
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if not summary["v2_intact"]:
        print("\nREFUSED: the frozen v2 dataset changed:", summary["v2_files_changed"], file=sys.stderr)
        sys.exit(1)
    if not all(s["ok"] for s in summary["steps"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
