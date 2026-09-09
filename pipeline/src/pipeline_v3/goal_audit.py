"""F4 -- does the declared goal match the diet's content?

The hypothesis is about how the professional works: he starts from the client's previous diet, changes the food and
forgets to update the objective in the header. If that happens, some diets carry a goal their content contradicts --
and since the goal is the primary retrieval key and the stratum of nearly every figure in the evaluation, a corrupt
one is not a cosmetic problem. It would also confound the ceiling on conditional precision measured in the previous
phase: no model predicts well from a variable that is itself wrong.

Nothing is corrected here. Diets are **marked**, with four fields (F4.3) and the evidence behind them.

Two independent signals, never one alone:

1. a multiclass classifier from content to declared goal, cross-validated with the clients held out together, so a
   client whose diets look alike cannot be scored on himself. Its own accuracy is checked FIRST: if it cannot
   separate goals on the diets we take to be correct, its disagreement means nothing and the analysis stops there.
2. the direction the scale actually moved between two consecutive versions, compared with the direction the declared
   goal implies. Only goals with an unambiguous direction take part -- ``mantenimiento``, ``alta_en_fibra`` and
   ``descarga_carga`` have none and are excluded by name.

F4.2 then tests the *mechanism* rather than the symptom: copy-and-forget can only happen on a version that was
copied from something, so suspicion should concentrate in v2 and later and be near absent in v1.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import goals as goal_taxonomy, paths
else:
    from . import goals as goal_taxonomy, paths

SEED = 20260828
# A diet is marked only when the classifier is this sure the declared label is wrong. Deliberately severe: the
# point is a short, credible list, not a large one.
P_DECLARED_MAX = 0.10
P_OTHER_MIN = 0.60
MIN_CLASS_SUPPORT = 30


def _load(out_dir: Path):
    diets = [json.loads(l) for l in (out_dir / "diets.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    items = collections.defaultdict(list)
    for line in (out_dir / "diet_items.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            items[row["diet_id"]].append(row)
    return diets, items


def _features(diet, item_rows):
    """Bag of content features: which foods, in what proportion, in which slot, and how the diet is shaped."""
    tokens: list[str] = []
    groups = collections.Counter()
    for row in item_rows:
        name = row.get("canonical_name")
        if name:
            tokens.append(f"food={name}")
            tokens.append(f"slot_food={row.get('meal_slot')}|{name}")
        group = row.get("group")
        if group:
            tokens.append(f"group={group}")
            groups[group] += 1
        family = row.get("family")
        if family:
            tokens.append(f"family={family}")
    total = max(1, sum(groups.values()))
    for group, count in groups.items():
        share = count / total
        tokens.append(f"share={group}={'hi' if share > 0.30 else 'mid' if share > 0.15 else 'lo'}")
    meals = diet.get("meals", {})
    tokens.append(f"nslots={min(len(meals), 10)}")
    tokens.append(f"nitems={min(len(item_rows) // 5, 12)}")
    for slot in meals:
        tokens.append(f"slot={slot}")
    return tokens


def _quantity_stats(item_rows):
    grams = [r["quantity"] for r in item_rows if r.get("unit") == "g" and r.get("quantity")]
    return float(np.median(grams)) if grams else None


def classify(diets, items, log: dict) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold

    labelled = [d for d in diets if d["meta"].get("goal") and not d["meta"].get("goal_inferred")]
    counts = collections.Counter(d["meta"]["goal"] for d in labelled)
    keep = {g for g, n in counts.items() if n >= MIN_CLASS_SUPPORT}
    usable = [d for d in labelled if d["meta"]["goal"] in keep]
    log["classes_kept"] = sorted(keep)
    log["classes_dropped_for_support"] = {g: n for g, n in counts.items() if g not in keep}
    log["diets_labelled"] = len(labelled)
    log["diets_usable"] = len(usable)
    if len(keep) < 2 or len(usable) < 100:
        log["status"] = "not enough labelled data to train a classifier"
        return {}

    corpus = [" ".join(_features(d, items.get(d["id"], []))) for d in usable]
    y = np.array([d["meta"]["goal"] for d in usable])
    groups = np.array([d["meta"]["client_code"] for d in usable])

    vectoriser = TfidfVectorizer(analyzer=lambda s: s.split(), min_df=3, sublinear_tf=True)
    X = vectoriser.fit_transform(corpus)

    classes = sorted(keep)
    proba = np.zeros((len(usable), len(classes)))
    predicted = np.empty(len(usable), dtype=object)
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    for train_index, test_index in splitter.split(X, y, groups):
        model = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
        model.fit(X[train_index], y[train_index])
        order = [list(model.classes_).index(c) for c in classes]
        proba[test_index] = model.predict_proba(X[test_index])[:, order]
        predicted[test_index] = model.predict(X[test_index])

    accuracy = float((predicted == y).mean())
    per_class = {}
    for label in classes:
        mask = y == label
        per_class[label] = {"n": int(mask.sum()), "recall": round(float((predicted[mask] == label).mean()), 3)}
    confusion = {a: {b: 0 for b in classes} for a in classes}
    for actual, pred in zip(y, predicted):
        confusion[actual][pred] += 1

    log["accuracy"] = round(accuracy, 3)
    log["baseline_majority"] = round(float(max(counts[c] for c in classes) / len(usable)), 3)
    log["per_class"] = per_class
    log["confusion_matrix"] = confusion
    log["confusion_note"] = ("rows are the declared goal, columns the content prediction; an asymmetric pair "
                             "(A read as B but B rarely as A) points at a direction of carry-over")

    # Both directions of every pair. Testing only a<b silently hides the asymmetry whenever the dominant direction
    # happens to run the other way round, which is what the first version of this did.
    asymmetry = []
    for a in classes:
        for b in classes:
            if a >= b:
                continue
            ab, ba = confusion[a][b], confusion[b][a]
            if ab + ba < 20:
                continue
            if (ab + 1) / (ba + 1) >= 2.0:
                asymmetry.append({"declared": a, "read_as": b, "this_way": ab, "other_way": ba,
                                  "ratio": round((ab + 1) / (ba + 1), 2)})
            elif (ba + 1) / (ab + 1) >= 2.0:
                asymmetry.append({"declared": b, "read_as": a, "this_way": ba, "other_way": ab,
                                  "ratio": round((ba + 1) / (ab + 1), 2)})
    log["asymmetries"] = sorted(asymmetry, key=lambda d: -d["ratio"])

    index = {d["id"]: i for i, d in enumerate(usable)}
    return {"ids": index, "proba": proba, "classes": classes, "accuracy": accuracy}


def scale_signal(diets, out_dir: Path, log: dict) -> dict:
    """Did the body actually move the way the declared goal implies, between this version and the previous one?"""
    measurements = collections.defaultdict(list)
    path = out_dir / "body_measurements.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                measurements[row["client_code"]].append(row)
    for rows in measurements.values():
        rows.sort(key=lambda r: r["date"])

    by_client = collections.defaultdict(list)
    for diet in diets:
        by_client[diet["meta"]["client_code"]].append(diet)
    for rows in by_client.values():
        rows.sort(key=lambda d: d["meta"]["diet_version"])

    verdicts: dict[str, dict] = {}
    counted = collections.Counter()
    for code, client_diets in by_client.items():
        readings = measurements.get(code, [])
        if len(readings) < 2:
            continue
        for previous, current in zip(client_diets, client_diets[1:]):
            goal = current["meta"].get("goal")
            if goal not in goal_taxonomy.DIRECTIONAL:
                counted["skipped_no_direction"] += 1
                continue
            start, end = previous["meta"].get("doc_date"), current["meta"].get("doc_date")
            if not start or not end:
                counted["skipped_no_dates"] += 1
                continue
            window = [r for r in readings if start <= r["date"] <= end]
            if len(window) < 2:
                counted["skipped_no_readings_in_window"] += 1
                continue
            expected = goal_taxonomy.DIRECTIONAL[goal]
            first, last = window[0], window[-1]
            observed = {}
            if first.get("weight_kg") and last.get("weight_kg"):
                observed["weight"] = last["weight_kg"] - first["weight_kg"]
            if first.get("fat_pct") and last.get("fat_pct"):
                observed["fat"] = last["fat_pct"] - first["fat_pct"]
            if not observed:
                counted["skipped_no_measures"] += 1
                continue
            disagreements = []
            for key, direction in expected.items():
                delta = observed.get(key)
                if delta is None or abs(delta) < (1.0 if key == "weight" else 1.0):
                    continue          # inside the noise band: no evidence either way
                if (delta > 0) != (direction > 0):
                    disagreements.append(key)
            counted["evaluated"] += 1
            if disagreements:
                counted["contradicted"] += 1
            verdicts[current["id"]] = {
                "goal": goal, "window_days": (np.datetime64(end) - np.datetime64(start)).astype(int),
                "observed": {k: round(v, 2) for k, v in observed.items()},
                "contradicts": disagreements,
            }
    log["scale_signal"] = {"pairs_evaluated": counted["evaluated"],
                           "pairs_contradicting_the_declared_goal": counted["contradicted"],
                           "skipped": {k: v for k, v in counted.items() if k.startswith("skipped")},
                           "note": ("only goals with an unambiguous direction take part; "
                                    f"excluded by design: {', '.join(goal_taxonomy.NON_DIRECTIONAL)}")}
    return verdicts


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    diets, items = _load(out_dir)
    log: dict = {"seed": SEED, "thresholds": {"p_declared_max": P_DECLARED_MAX, "p_other_min": P_OTHER_MIN}}

    model = classify(diets, items, log)
    scale_verdicts = scale_signal(diets, out_dir, log)

    # The gate: a classifier that cannot separate the goals it was trained on cannot testify about any single diet.
    usable_model = bool(model) and log.get("accuracy", 0) >= max(0.55, log.get("baseline_majority", 0) + 0.10)
    log["classifier_is_admissible"] = usable_model
    log["classifier_gate"] = ("a disagreement is only evidence if the classifier separates the goals at all; "
                              "the gate is accuracy >= max(0.55, majority baseline + 0.10)")

    marked = 0
    withheld: list[str] = []
    signals_hist = collections.Counter()
    by_version = collections.defaultdict(lambda: {"diets": 0, "suspect": 0})
    per_diet: dict[str, dict] = {}

    for diet in diets:
        diet_id = diet["id"]
        declared = diet["meta"].get("goal")
        evidence: list[str] = []
        predicted = None
        if usable_model and diet_id in model.get("ids", {}):
            row = model["proba"][model["ids"][diet_id]]
            classes = model["classes"]
            best = int(np.argmax(row))
            predicted = classes[best]
            if declared in classes:
                p_declared = float(row[classes.index(declared)])
                if p_declared <= P_DECLARED_MAX and float(row[best]) >= P_OTHER_MIN and predicted != declared:
                    evidence.append(f"content_classifier(p_declared={p_declared:.2f},p_{predicted}={row[best]:.2f})")
        verdict = scale_verdicts.get(diet_id)
        if verdict and verdict["contradicts"]:
            evidence.append("scale_trajectory(" + ",".join(verdict["contradicts"]) + ")")

        # A diet whose declared purpose the taxonomy cannot express (depurativa/detox, salud metabólica,
        # rendimiento: 99 / 260 / 79 diets) will look "incoherent" to a classifier trained on the eight labels,
        # because there is no label for what he actually wrote. That is a gap in the taxonomy, not a slip of his,
        # and folding the two together would inflate the suspect list with the wrong kind of case.
        uncovered = diet["meta"].get("goal_uncovered_purposes") or []
        suspect = len(evidence) >= 2 and not uncovered
        if len(evidence) >= 2 and uncovered:
            evidence.append("withheld: the declared purpose is outside the taxonomy (" + ",".join(uncovered) + ")")
            withheld.append(diet_id)
        per_diet[diet_id] = {
            "goal_declared": diet["meta"].get("goal_declared") or diet["meta"].get("goal_text") or "",
            "goal_content_predicted": predicted,
            "goal_suspect": suspect,
            "goal_evidence": evidence,
        }
        version = diet["meta"]["diet_version"]
        bucket = by_version[min(version, 5)]
        bucket["diets"] += 1
        if suspect:
            bucket["suspect"] += 1
            marked += 1
        signals_hist[len(evidence)] += 1

    # How much of the corpus each signal could speak about at all. Without this, "no diet had two signals" reads as
    # evidence against the hypothesis when it may only mean the two signals never looked at the same diet.
    classifier_domain = set(model.get("ids", {})) if usable_model else set()
    scale_domain = set(scale_verdicts)
    both = classifier_domain & scale_domain
    flagged_by_classifier = {i for i, v in per_diet.items()
                             if any(e.startswith("content_classifier") for e in v["goal_evidence"])}
    flagged_by_scale = {i for i, v in per_diet.items()
                        if any(e.startswith("scale_trajectory") for e in v["goal_evidence"])}
    log["signal_domains"] = {
        "diets_total": len(diets),
        "evaluable_by_classifier": len(classifier_domain),
        "evaluable_by_scale": len(scale_domain),
        "evaluable_by_both": len(both),
        "flagged_by_classifier_alone": len(flagged_by_classifier),
        "flagged_by_scale_alone": len(flagged_by_scale),
        "flagged_by_classifier_within_both": len(flagged_by_classifier & both),
        "flagged_by_scale_within_both": len(flagged_by_scale & both),
        "note": ("the AND rule can only mark a diet inside `evaluable_by_both`; read `marked_diets` against that "
                 "denominator, not against the corpus"),
    }

    log["marked_diets"] = marked
    log["withheld_because_the_purpose_is_outside_the_taxonomy"] = len(withheld)
    log["uncovered_purpose_counts"] = dict(collections.Counter(
        u for d in diets for u in (d["meta"].get("goal_uncovered_purposes") or [])).most_common())
    log["uncovered_note"] = ("depurativa/detox, salud metabolica and rendimiento are purposes the v2 taxonomy has "
                             "no label for. They are counted, never mapped onto the nearest existing goal, and a "
                             "diet that declares one is never marked suspect: the classifier cannot testify about "
                             "a label that does not exist")
    log["diets_by_signal_count"] = dict(sorted(signals_hist.items()))
    log["suspicion_by_version"] = {
        str(v): {**counts, "rate": round(counts["suspect"] / counts["diets"], 4) if counts["diets"] else 0.0}
        for v, counts in sorted(by_version.items())
    }
    log["version_note"] = ("F4.2: copy-and-forget can only happen on a version copied from something, so the rate "
                           "should rise from v1; a flat profile means noise from another cause")

    # The version test above is computed on the AND rule, and when that rule marks nothing it says nothing. Run it
    # again on each signal separately so the mechanism is actually testable rather than vacuously flat.
    def rate_by_version(flagged: set[str], population) -> dict:
        buckets: dict[int, dict] = collections.defaultdict(lambda: {"diets": 0, "flagged": 0})
        for diet in diets:
            if population is not None and diet["id"] not in population:
                continue
            bucket = buckets[min(diet["meta"]["diet_version"], 5)]
            bucket["diets"] += 1
            if diet["id"] in flagged:
                bucket["flagged"] += 1
        return {str(v): {**c, "rate": round(c["flagged"] / c["diets"], 4) if c["diets"] else 0.0}
                for v, c in sorted(buckets.items())}

    log["suspicion_by_version_per_signal"] = {
        "content_classifier": rate_by_version(flagged_by_classifier, classifier_domain),
        "scale_trajectory": rate_by_version(flagged_by_scale, scale_domain),
    }
    log["compound_goals"] = sum(1 for d in diets if d["meta"].get("goal_is_compound"))
    log["taxonomy"] = dict(collections.Counter(d["meta"].get("goal") for d in diets).most_common())

    # F4.2, the signature of the mechanism itself: two consecutive versions that keep the SAME declared goal while
    # the content of the later one moves away from that goal and towards another. That is what copy-and-forget
    # looks like from the inside, and unlike the marking rule it does not need the drift to be large enough to
    # flip a label.
    if usable_model:
        index, proba, classes = model["ids"], model["proba"], model["classes"]
        by_client = collections.defaultdict(list)
        for diet in diets:
            by_client[diet["meta"]["client_code"]].append(diet)
        drifts: list[dict] = []
        pairs = 0
        for client_diets in by_client.values():
            client_diets.sort(key=lambda d: d["meta"]["diet_version"])
            for previous, current in zip(client_diets, client_diets[1:]):
                goal = previous["meta"].get("goal")
                if goal != current["meta"].get("goal") or goal not in classes:
                    continue
                if previous["id"] not in index or current["id"] not in index:
                    continue
                pairs += 1
                column = classes.index(goal)
                before = float(proba[index[previous["id"]]][column])
                after = float(proba[index[current["id"]]][column])
                if before - after >= 0.25:
                    other = classes[int(np.argmax(proba[index[current["id"]]]))]
                    if other != goal:
                        drifts.append({"from": previous["id"], "to": current["id"], "declared": goal,
                                       "p_declared_before": round(before, 3), "p_declared_after": round(after, 3),
                                       "content_moves_towards": other})
        log["drift_test"] = {
            "consecutive_pairs_with_the_same_declared_goal": pairs,
            "pairs_drifting_away_from_it": len(drifts),
            "rate": round(len(drifts) / pairs, 4) if pairs else 0.0,
            "examples": drifts[:15],
            "note": ("F4.2 signature: same label kept, content moves towards another goal by at least 0.25 of "
                     "predicted probability"),
        }

    # Write the four F4.3 fields back into diets.jsonl.
    for diet in diets:
        diet["meta"].update(per_diet[diet["id"]])
    with open(out_dir / "diets.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for diet in diets:
            handle.write(json.dumps(diet, ensure_ascii=False) + "\n")

    (out_dir / "goal_audit.json").write_text(json.dumps(log, ensure_ascii=False, indent=1),
                                             encoding="utf-8", newline="\n")
    return log


def main() -> None:
    argparse.ArgumentParser(description="F4: audit the declared goal against the diet's content").parse_args()
    log = build()
    printable = {k: v for k, v in log.items() if k not in ("confusion_matrix",)}
    print(json.dumps(printable, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
