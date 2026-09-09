# -*- coding: utf-8 -*-
"""Acceptance tests of the reviewed synonym dictionary (pipeline/data/food_synonyms.json).

  * no synonym contains a unit word (cucharada, cazo, lata, loncha, perla, ...)
  * no synonym contains two stand-alone food heads of different families (compound fragment)
  * no normalised key is listed under two canonicals
  * no canonical's own key is listed as a synonym of another canonical
  * every merge across different head nouns is present in the reviewed list (pipeline/data/reviewed_merges.json)
  * every canonical has a family
Run with pytest or `python pipeline/tests/test_synonyms.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import REPO_ROOT, DATA_DIR  # noqa: E402
from pipeline.build_food_catalog import SYNONYMS_PATH, normalize_key  # noqa: E402
from pipeline.audit_synonyms import GENERIC, UNIT_WORDS, head  # noqa: E402

REVIEWED_MERGES = DATA_DIR / "reviewed_merges.json"


def load():
    data = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))
    return data["families"]


def all_entries():
    for fam, cmap in load().items():
        for canon, keys in cmap.items():
            yield fam, canon, [normalize_key(k) for k in keys]


def test_no_unit_word_in_synonyms():
    bad = [(canon, k) for fam, canon, keys in all_entries() for k in keys
           if any(t in UNIT_WORDS for t in k.replace("_", " ").split())]
    assert not bad, f"unit words inside synonyms: {bad[:10]}"


def test_no_compound_fragment_in_synonyms():
    families = load()
    single_family: dict[str, str] = {}
    for fam, cmap in families.items():
        for canon, keys in cmap.items():
            for k in [normalize_key(canon)] + [normalize_key(x) for x in keys]:
                if k and " " not in k and "_" not in k and k not in GENERIC:
                    single_family.setdefault(k, fam)
    allowed = set(json.loads(REVIEWED_MERGES.read_text(encoding="utf-8")).get("compound_names_allowed", []))
    bad = []
    for fam, canon, keys in all_entries():
        for k in keys:
            fams = {single_family[t] for t in k.replace("_", " ").split() if t in single_family}
            if len(fams) >= 2 and k not in allowed:
                bad.append((canon, k, sorted(fams)))
    assert not bad, f"two food heads of different families glued in a synonym: {bad[:10]}"


def test_no_key_under_two_canonicals():
    seen: dict[str, str] = {}
    dup = []
    for fam, canon, keys in all_entries():
        for k in [normalize_key(canon)] + keys:
            if not k:
                continue
            if k in seen and seen[k] != canon:
                dup.append((k, seen[k], canon))
            seen.setdefault(k, canon)
    assert not dup, f"keys listed under two canonicals: {dup}"


def test_no_canonical_listed_as_synonym_of_another():
    canon_keys = {normalize_key(canon): canon for fam, canon, _ in all_entries()}
    bad = [(canon, k, canon_keys[k]) for fam, canon, keys in all_entries() for k in keys
           if k in canon_keys and canon_keys[k] != canon]
    assert not bad, f"canonical listed as a synonym of another: {bad}"


def test_cross_head_merges_are_reviewed():
    reviewed = json.loads(REVIEWED_MERGES.read_text(encoding="utf-8"))["merges"]
    reviewed_pairs = {(m["canonical"], m["key"]) for m in reviewed}
    missing = []
    for fam, canon, keys in all_entries():
        ck = normalize_key(canon)
        for k in keys:
            if k and head(k) != head(ck) and head(ck) not in k.replace("_", " ").split() and (canon, k) not in reviewed_pairs:
                missing.append((canon, k))
    assert not missing, f"cross-head merges not in the reviewed list: {missing[:15]} (+{max(0, len(missing) - 15)})"


def test_every_canonical_has_a_family_and_unique_name():
    names = [canon for fam, canon, _ in all_entries()]
    assert len(names) == len(set(names)), "duplicate canonical names across families"
    assert all(fam for fam, _, _ in all_entries())


from pipeline import DATASET_DIR as _DATASET_DIR  # noqa: E402
from pipeline.build_food_catalog import EXCLUDED_PATH as _EXCLUDED_PATH  # noqa: E402

BRAND_MAP = json.loads((DATA_DIR / "brand_map.json").read_text(encoding="utf-8"))
BRAND_KEYS = {k for b in BRAND_MAP["brands"] for k in b["keys"]} | {k for b in BRAND_MAP["unmapped_brands"] for k in b["keys"]}
BRAND_NAMES = {b["brand"].lower() for b in BRAND_MAP["brands"]} | {b["brand"].lower() for b in BRAND_MAP["unmapped_brands"]}


def test_no_canonical_is_a_brand():
    """No canonical_name may be a commercial brand: brands map to their generic function (brand_map.json)."""
    families = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))["families"]
    canonicals = {c for fam in families.values() for c in fam}
    offenders = {c for c in canonicals if c in BRAND_KEYS or c in BRAND_NAMES or any(c == k or c.startswith(k + " ") for k in BRAND_KEYS)}
    assert not offenders, sorted(offenders)
    foods_json = _DATASET_DIR / "foods.json"
    if foods_json.exists():
        built = {f["canonical_name"] for f in json.loads(foods_json.read_text(encoding="utf-8"))["foods"]}
        assert not (built & (BRAND_KEYS | BRAND_NAMES)), sorted(built & (BRAND_KEYS | BRAND_NAMES))


def test_brand_keys_live_only_in_brand_map_and_generics_exist():
    families = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))["families"]
    in_synonyms = {k for fam in families.values() for keys in fam.values() for k in keys} & BRAND_KEYS
    assert not in_synonyms, sorted(in_synonyms)
    for b in BRAND_MAP["brands"]:
        assert b["generic"] in families.get(b["family"], {}), (b["brand"], b["generic"], b["family"])
        assert b["generic"].lower() not in BRAND_NAMES
    excluded = {k for s_ in json.loads(_EXCLUDED_PATH.read_text(encoding="utf-8"))["substances"] for k in s_["keys"]}
    mapped = {k for b in BRAND_MAP["brands"] for k in b["keys"]}
    assert not (mapped & excluded), sorted(mapped & excluded)              # genericising is not excluding: a mapped brand key is never excluded


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failed else 0)
