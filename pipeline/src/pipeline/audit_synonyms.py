# -*- coding: utf-8 -*-
"""
Task A — Orthographic and semantic audit of the reviewed synonym dictionary (pipeline/data/food_synonyms.json).

Four problem classes, reported with corpus frequencies (from _dataset/parsed_items.jsonl):
  class 1  misspellings of the corpus: a key token at edit distance 1-2 from a token of the group's reference
           form (canonical name or most frequent key), e.g. cuharada -> cucharada, amilopeptina -> amilopectina
  class 2  candidate wrong merges: keys whose head noun differs from the canonical's head noun (manual review)
  class 3  unit words inside a synonym (cucharada, cazo, lata, loncha, perla ...): a parser/normaliser problem,
           never a synonym
  class 4  compound fragments: keys containing two distinct food head nouns (two foods glued together)

Cross-checks: a key mapped to two canonicals; a canonical's own key listed under another canonical;
high-volume assumptions (generic words such as "aceite", "carne", "proteina", "vitamina", "pescado").

Output: _dataset/synonym_audit.json + summary on stdout. Read-only: the dictionary is corrected by hand.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR  # noqa: E402
from pipeline.build_food_catalog import SYNONYMS_PATH, load_json, normalize_key  # noqa: E402

UNIT_WORDS = {"cucharada", "cucharadas", "cuharada", "cucharadita", "cazo", "cazos", "cazito", "scoop", "lata", "latas", "loncha",
              "lonchas", "punado", "diente", "dientes", "rebanada", "rebanadas", "chorrito", "taza", "tazas", "capsula", "capsulas",
              "caps", "perla", "perlas", "pastilla", "pastillas", "tableta", "tabletas", "dosis", "medida", "rodaja", "rodajas",
              "onza", "onzas", "vaso", "copa", "copas", "pieza", "piezas", "unidad", "filete", "filetes", "gr", "ml"}
GENERIC = {"aceite", "oliva", "carne", "proteina", "vitamina", "pescado", "batido", "cereal", "verdura", "fruta", "queso", "pan",
           "leche", "yogur", "aminoacido", "mineral", "legumbre", "ensalada", "zumo", "harina", "blanco", "azul", "integral"}


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def head(key: str) -> str:
    toks = key.replace("_", " ").split()
    return toks[0] if toks else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synonyms", type=Path, default=SYNONYMS_PATH)
    ap.add_argument("--parsed", type=Path, default=DATASET_DIR / "parsed_items.jsonl")
    ap.add_argument("--out", type=Path, default=DATASET_DIR / "synonym_audit.json")
    args = ap.parse_args()
    families = load_json(args.synonyms)["families"]
    rows = [json.loads(l) for l in args.parsed.read_text(encoding="utf-8").splitlines() if l.strip()]
    key_freq = Counter(normalize_key(r["food_text"]) for r in rows if r["food_text"] and not r["is_instruction"] and not r.get("is_noise"))

    # canonical head nouns (for class 4): head token of every canonical, minus generic words
    canon_heads: dict[str, str] = {}
    for fam, cmap in families.items():
        for canon in cmap:
            h = head(normalize_key(canon))
            if h and h not in GENERIC:
                canon_heads[h] = canon
    # also a few strong food heads that are keys but not canonical heads
    extra_heads = {"tomate": "tomate", "limon": "limón", "leche": "leche", "avena": "avena", "queso": "queso", "pan": "pan integral",
                   "soja": "bebida de soja", "pollo": "pollo", "pavo": "pavo", "atun": "atún", "arroz": "arroz", "patata": "patata"}
    heads = {**extra_heads, **canon_heads}

    # single-token canonical keys -> family (e.g. tomate -> verdura, aceite -> grasa)
    single_token_family: dict[str, str] = {}
    for fam, cmap in families.items():
        for canon, keys in cmap.items():
            for k in [normalize_key(canon)] + [normalize_key(x) for x in keys]:
                if k and " " not in k and "_" not in k and k not in GENERIC and k not in single_token_family:
                    single_token_family[k] = fam
    raw_of: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["food_text"] and not r["is_instruction"] and not r.get("is_noise"):
            k = normalize_key(r["food_text"])
            if len(raw_of[k]) < 2:
                raw_of[k].append(r["food_text"])
    seen_keys: dict[str, str] = {}
    duplicates, canon_as_synonym = [], []
    class1, class2, class3, class4 = [], [], [], []
    canon_key_of = {canon: normalize_key(canon) for cmap in families.values() for canon in cmap}
    for fam, cmap in families.items():
        for canon, keys in cmap.items():
            ck = canon_key_of[canon]
            norm_keys = [normalize_key(k) for k in keys]
            ck_tokens = set(ck.replace("_", " ").split())
            for raw_k, k in zip(keys, norm_keys):
                n_k = key_freq.get(k, 0)
                ref_tokens = set(ck_tokens)
                for other in norm_keys:
                    if other != k and key_freq.get(other, 0) > n_k:
                        ref_tokens |= set(other.replace("_", " ").split())
                if not k:
                    continue
                n = key_freq.get(k, 0)
                if k in seen_keys and seen_keys[k] != canon:
                    duplicates.append({"key": k, "canonicals": [seen_keys[k], canon]})
                seen_keys.setdefault(k, canon)
                if k != ck and k in canon_key_of.values() and canon_key_of.get(canon) != k:
                    other = [c for c, kk in canon_key_of.items() if kk == k and c != canon]
                    if other:
                        canon_as_synonym.append({"key": k, "listed_under": canon, "canonical_of": other})
                toks = k.replace("_", " ").split()
                # class 3
                units = [t for t in toks if t in UNIT_WORDS]
                if units:
                    class3.append({"canonical": canon, "key": k, "n": n, "unit_words": units})
                # class 1 (misspelling of a more frequent form, or a split word such as "pa vo")
                joined = "".join(toks)
                if len(toks) >= 2 and joined in ref_tokens:
                    class1.append({"canonical": canon, "key": k, "token": k, "close_to": joined, "n": n, "kind": "split_word"})
                for t in toks:
                    if len(t) >= 5 and t not in ref_tokens:
                        close = sorted((rt for rt in ref_tokens if len(rt) >= 5 and 0 < levenshtein(t, rt) <= 2),
                                       key=lambda rt: levenshtein(t, rt))
                        if close:
                            class1.append({"canonical": canon, "key": k, "token": t, "close_to": close[0], "n": n, "kind": "edit_distance"})
                            break
                # class 4: tokens that are stand-alone foods of DIFFERENT families glued in one key
                fams = {single_token_family[t] for t in toks if t in single_token_family}
                if len(fams) >= 2:
                    class4.append({"canonical": canon, "key": k, "n": n, "families": sorted(fams),
                                   "example": next((r for r in raw_of.get(k, [])), "")})
                # class 2 (different head noun, not class 1/3/4)
                if head(k) and head(ck) and head(k) != head(ck) and head(ck) not in toks:
                    class2.append({"canonical": canon, "family": fam, "key": k, "n": n})
    generic_assumptions = []
    for fam, cmap in families.items():
        for canon, keys in cmap.items():
            for k in keys:
                nk = normalize_key(k)
                if nk in GENERIC:
                    generic_assumptions.append({"generic_key": nk, "assumed_canonical": canon, "n": key_freq.get(nk, 0)})
    report = {
        "class1_misspellings": sorted(class1, key=lambda x: -x["n"]),
        "class2_different_head_noun": sorted(class2, key=lambda x: -x["n"]),
        "class3_unit_words": sorted(class3, key=lambda x: -x["n"]),
        "class4_compound_fragments": sorted(class4, key=lambda x: -x["n"]),
        "duplicate_keys": duplicates, "canonical_listed_as_synonym": canon_as_synonym,
        "generic_assumptions": sorted(generic_assumptions, key=lambda x: -x["n"]),
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print({k: len(v) for k, v in report.items()})
    for name in ("class1_misspellings", "class3_unit_words", "class4_compound_fragments", "duplicate_keys", "canonical_listed_as_synonym", "generic_assumptions"):
        print(f"\n== {name} ({len(report[name])}) ==")
        seen = set()
        for x in report[name]:
            key = json.dumps(x, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            if name in ("class3_unit_words", "class4_compound_fragments") and x["n"] == 0:
                continue
            print("  ", x)
    print("\n== class2_different_head_noun (n>=1) ==")
    for x in report["class2_different_head_noun"]:
        if x["n"] >= 1:
            print(f"   {x['n']:4d} {x['key']:32s} -> {x['canonical']} [{x['family']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
