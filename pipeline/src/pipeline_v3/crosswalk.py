"""Correspondence between v2 and v3 client pseudonyms, and the census of who is in which source.

The two datasets number their clients independently: ``CLIENTE_007`` in v2 and ``CLIENTE_007`` in v3 are almost never
the same person. Comparing them (F6) therefore needs a crosswalk, and the only shared key is the *original document
file name*, which the v2 private maps record per client and which still exists on disk under the sources root.

Everything this module writes is pseudonymous: v2 code, v3 code, counts. The file names it joins on are read from the
private maps, used as join keys in memory, and never emitted.

Written artefacts (private, alongside the other maps):
  ``_private/id_map_v2_v3.json``   v2 code <-> v3 code, with the evidence count behind each pair
Public:
  ``client_census.json``            who is in the sources, in v2, in the scale export, and in the v2 markdown tree
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import convert, identity, paths, scale
else:
    from . import convert, identity, paths, scale


_SHINGLE_N = 5
_TOKEN_RE = __import__("re").compile(r"[a-z0-9áéíóúñü]+")


def _shingles(text: str) -> set[str]:
    """Word 5-grams of the lower-cased text: a content fingerprint that survives conversion differences."""
    words = _TOKEN_RE.findall(text.lower())
    if len(words) < _SHINGLE_N:
        return set()
    return {" ".join(words[i:i + _SHINGLE_N]) for i in range(len(words) - _SHINGLE_N + 1)}


def _v2_client_shingles() -> dict[str, set[str]]:
    """v2 client code -> content fingerprint, taken from the v2 markdown tree.

    The v2 private maps turned out to record only the *processed* ``.md`` names on both sides, so there is no file
    name shared with the sources and no identifier to join on. What both versions do share is the documents
    themselves, so the crosswalk is built on content: word 5-grams of a client's own documents are distinctive
    enough (quantities, food lists, note wording) to identify the same person across the two extractions, and they
    are pseudonymous, which a name join would not have been.
    """
    tree = paths.client_tree()
    out: dict[str, set[str]] = {}
    if not tree.exists():
        return out
    for directory in sorted(p for p in tree.iterdir() if p.is_dir()):
        collected: set[str] = set()
        for md in directory.glob("*.md"):
            try:
                collected |= _shingles(md.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
        if collected:
            out[directory.name] = collected
    return out


def _v3_client_shingles(root: Path, registry) -> dict[str, set[str]]:
    out: dict[str, set[str]] = collections.defaultdict(set)
    manifest = paths.dataset_dir_v3() / "manifest.jsonl"
    if not manifest.exists():
        raise FileNotFoundError("run inventory.py first: the crosswalk reads manifest.jsonl")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        code, sha = row.get("client_code"), row.get("sha1")
        if not code or not sha or row.get("status") != "ok":
            continue
        out[code] |= _shingles(convert.cached_text(sha))
    return dict(out)


def build(out_dir: Path | None = None) -> dict:
    root = paths.sources_root()
    out_dir = out_dir or paths.dataset_dir_v3()
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = identity.load_or_build_registry(root)

    v2_shingles = _v2_client_shingles()
    v3_shingles = _v3_client_shingles(root, registry)

    # Inverted index over 5-grams that belong to exactly one v2 client: a shingle shared by several clients
    # (boilerplate, a note he repeats verbatim) carries no identity and is dropped rather than voting.
    holders: dict[str, set[str]] = collections.defaultdict(set)
    for code, shingles in v2_shingles.items():
        for shingle in shingles:
            holders[shingle].add(code)
    distinctive = {s: next(iter(codes)) for s, codes in holders.items() if len(codes) == 1}

    votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for v3_code, shingles in v3_shingles.items():
        counter = votes[v3_code]
        for shingle in shingles:
            owner = distinctive.get(shingle)
            if owner:
                counter[owner] += 1

    # Score by CONTAINMENT, not by raw overlap: a raw count rewards whoever has the most documents, so a prolific
    # client outbids the right one for shingles they happen to share. Containment asks what fraction of the v2
    # client's own distinctive material this v3 client reproduces, which is what identity actually means here.
    distinctive_size = collections.Counter(distinctive.values())
    MIN_EVIDENCE = 20              # 5-grams; below this the match is not credible whatever the ratio says
    MIN_MARGIN = 2.0               # below this the pair is kept but flagged as low confidence

    candidates: list[tuple[int, float, str, str]] = []
    for v3_code, counter in votes.items():
        for v2_code, hits in counter.items():
            if hits < MIN_EVIDENCE:
                continue
            candidates.append((hits, hits / max(1, distinctive_size.get(v2_code, 1)), v3_code, v2_code))
    candidates.sort(reverse=True)

    # Global greedy assignment on the evidence count, each side used at most once. A margin veto was tried first
    # and cost 27 correct pairs while tripling the conflicts: the competition it was trying to arbitrate is already
    # settled by the assignment being one-to-one. What the margin is good for is *flagging*, so a close second
    # becomes a confidence note on the pair rather than a reason to drop it.
    v3_to_v2: dict[str, str] = {}
    claimed: dict[str, str] = {}
    low_confidence: list[dict] = []
    conflicts: list[dict] = []
    for hits, score, v3_code, v2_code in candidates:
        if v3_code in v3_to_v2 or v2_code in claimed:
            continue
        runner_up = max((h for h, _s, c3, c2 in candidates if c3 == v3_code and c2 != v2_code), default=0)
        v3_to_v2[v3_code] = v2_code
        claimed[v2_code] = v3_code
        if runner_up and hits < MIN_MARGIN * runner_up:
            low_confidence.append({"v3": v3_code, "v2": v2_code, "evidence": hits, "runner_up": runner_up,
                                   "containment": round(score, 3),
                                   "reason": "a second v2 client matches comparably (shared or templated diets)"})
    for v3_code, counter in votes.items():
        if v3_code not in v3_to_v2 and counter:
            top, hits = counter.most_common(1)[0]
            conflicts.append({"v3": v3_code, "best_v2": top, "evidence": hits,
                              "reason": "below the evidence floor" if hits < MIN_EVIDENCE
                              else "its best v2 match was already claimed by a better-supported pair"})

    v2_all = sorted(set(v2_shingles))
    v2_profiles = {json.loads(line)["client_code"]
                   for line in (paths.dataset_dir_v2() / "profiles.jsonl").read_text(encoding="utf-8").splitlines()
                   if line.strip()}
    v3_all = sorted(set(registry.codes.values()))
    matched_v2 = set(v3_to_v2.values())

    # The scale export and the v2 markdown tree, for the same census.
    users, _history = scale._load(scale.scale_file(root))
    excluded = scale.professional_uuids(users, _history, registry)
    scale_map, scale_unmatched = scale.match_users_to_clients(
        [u for u in users if u.get("uuid") not in excluded], registry)
    tree = paths.client_tree()
    tree_codes = sorted(p.name for p in tree.iterdir() if p.is_dir()) if tree.exists() else []

    private = out_dir / "_private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "id_map_v2_v3.json").write_text(
        json.dumps({"v3_to_v2": v3_to_v2,
                    "evidence": {k: votes[k][v] for k, v in v3_to_v2.items()},
                    "score": {k: round(votes[k][v] / max(1, distinctive_size.get(v, 1)), 3) for k, v in v3_to_v2.items()},
                    "conflicts": conflicts, "low_confidence": low_confidence}, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")

    census = {
        "clients_in_sources_v3": len(v3_all),
        "clients_in_v2_private_maps": len(v2_all),
        "clients_in_v2_profiles": len(v2_profiles),
        "clients_in_v2_markdown_tree": len(tree_codes),
        "matched_v3_to_v2": len(v3_to_v2),
        "v3_without_a_v2_counterpart": sorted(set(v3_all) - set(v3_to_v2)),
        "v2_without_a_v3_counterpart": sorted(set(v2_profiles) - matched_v2),
        "v2_profiles_without_a_v3_counterpart_count": len(set(v2_profiles) - matched_v2),
        "crosswalk_conflicts": conflicts,
        "crosswalk_low_confidence": len(low_confidence),
        "crosswalk_low_confidence_detail": low_confidence,
        "scale_users_total": len(users),
        "scale_users_matched_to_a_source_folder": len(scale_map),
        "scale_users_without_a_source_folder": len(scale_unmatched),
        "note": (
            "v2 profiles without a v3 counterpart are the clients whose documents are not under the sources root. "
            "They are the 467-vs-301 gap; the v2 markdown tree still holds their converted text (plan B)."
        ),
    }
    (out_dir / "client_census.json").write_text(json.dumps(census, ensure_ascii=False, indent=1),
                                                encoding="utf-8", newline="\n")
    return census


def main() -> None:
    argparse.ArgumentParser(description="v2<->v3 client crosswalk and census").parse_args()
    census = build()
    printable = {k: v for k, v in census.items()
                 if k not in ("v3_without_a_v2_counterpart", "v2_without_a_v3_counterpart",
                              "crosswalk_conflicts", "crosswalk_low_confidence_detail")}
    print(json.dumps(printable, ensure_ascii=False, indent=1))
    print(f"\nv3 without v2: {len(census['v3_without_a_v2_counterpart'])}"
          f" | v2 without v3: {len(census['v2_without_a_v3_counterpart'])}"
          f" | conflicts: {len(census['crosswalk_conflicts'])}   (lists in client_census.json)")


if __name__ == "__main__":
    main()
