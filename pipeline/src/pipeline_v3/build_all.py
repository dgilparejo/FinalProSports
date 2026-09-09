"""Build the whole v3 dataset, in order, from the raw sources.

Each stage is a module in this package and can be run on its own; this exists so the order is written down once and
the whole thing is reproducible with a single command. Nothing here touches the frozen v2 dataset: the E1 stage
goes through :mod:`pipeline_v3.run_e1`, which pins ``FPS_DATASET_DIR`` and verifies 16 guarded v2 files afterwards.

Usage::

    FPS_PROFESSIONAL_TOKENS=<surname> python pipeline/src/pipeline_v3/build_all.py

``FPS_PROFESSIONAL_TOKENS`` is only needed the first time: it seeds the salted digests used to recognise the
professional's own name, after which the plaintext is never stored or read again.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline_v3 import (  # noqa: E402
    crosswalk, extract_diets, extract_profiles, extract_training, goal_audit, inventory, labs,
    merge_meta, paths, provenance, run_e1, sanitise_artifacts, scale, vocab,
)

STAGES = [
    ("F1 inventory + conversion", lambda: inventory.build()),
    ("F3 scale export", lambda: scale.build()),
    ("F1 v2/v3 crosswalk", lambda: crosswalk.build()),
    ("F2 vocabularies", lambda: vocab.enumerate_all()),
    ("F3 diets", lambda: extract_diets.build()),
    ("F3 profiles", lambda: extract_profiles.build()),
    ("merge profile meta into diets", lambda: merge_meta.build()),
    ("E1 chain (parse, catalogue, rules, normalise)", lambda: run_e1.run()),
    ("F4 goal audit", lambda: goal_audit.build()),
    ("F3 lab reports", lambda: labs.build()),
    ("F3 training, follow-up, screenshots", lambda: extract_training.build()),
    ("F6 provenance artefacts (v2 shapes) + declared figures", lambda: {**provenance.build(), **provenance.unservable_goals(paths.dataset_dir_v3()), **provenance.write_declared_figures()}),
    ("strip paths from artefacts", lambda: sanitise_artifacts.build()),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="build the whole v3 dataset")
    parser.add_argument("--from-stage", type=int, default=0, help="skip the first N stages")
    args = parser.parse_args()

    print(f"building v3 into {paths.dataset_dir_v3()}")
    print(f"work directory     {paths.work_dir()}\n")
    results = []
    for index, (name, run) in enumerate(STAGES):
        if index < args.from_stage:
            print(f"  [{index:2}] {name:48} skipped")
            continue
        started = time.time()
        try:
            run()
            status = "ok"
        except Exception as exc:  # the stage logs its own detail; the runner must not hide a failure
            status = f"FAILED {type(exc).__name__}: {exc}"
        elapsed = time.time() - started
        print(f"  [{index:2}] {name:48} {status:12} {elapsed:6.1f}s", flush=True)
        results.append({"stage": name, "status": status, "seconds": round(elapsed, 1)})
        if status != "ok":
            sys.exit(1)

    (paths.dataset_dir_v3() / "build_all_log.json").write_text(
        json.dumps({"stages": results}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print("\nv3 built. It is NOT active: nothing in .env changed, no embeddings were rebuilt, no harness was run.")


if __name__ == "__main__":
    main()
