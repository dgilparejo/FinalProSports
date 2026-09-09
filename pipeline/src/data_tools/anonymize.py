# -*- coding: utf-8 -*-
"""
Phase 2 — Anonymisation of identifiers and metadata (+ English field names).

Inputs (originals, NEVER modified):
  --chunks        _meta/chunks_dietas.jsonl
  --diets         _meta/dietas_estructuradas.json
  --meal-chunks   _meta/chunks_comidas.jsonl              (optional)
  --name-map      _dataset/_private/name_map.json         (dictionary for the sweep only)
  --profiles      _meta/perfiles.json                     (optional; free-text sweep only)
  --substitute    _dataset/_private/text_substitutions.json (optional; tokens -> [NOMBRE])
  --false-positives _dataset/_private/reviewed_false_positives.json (optional)

Outputs:
  <out-dir>/diet_chunks.jsonl        new ids, no meta.archivo, English meta fields
  <out-dir>/structured_diets.json    no archivo, English fields, new id
  <out-dir>/meal_chunks.jsonl        new ids, no meta.archivo (if --meal-chunks)
  <private-dir>/id_map.json          new_id -> original file name (+client, version, index)
  <private-dir>/text_sweep.json      MASKED contexts of possible names in free text
  <private-dir>/anonymize_log.json   transformation counts

New identifier:  CLIENTE_NNN::vVV   (known diet_version, at least 2 digits)
                 CLIENTE_NNN::sSS   (no version: stable ordinal by order of appearance
                                     among the versionless diets of the same client)
Collisions (same client and version): suffix -2, -3, ... assigned by alphabetical
order of the original file name within the group. Deterministic: depends only on
the input file content, never on the file system or a random seed.

Field renaming (Spanish -> English) follows FIELD_RENAME in pii_common; the raw
"OBJETIVO:" line read from the document becomes `goal_text` to distinguish it
from the classified `goal`. Data values stay in Spanish.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pii_common import (  # noqa: E402
    DETECTORS, FIELD_RENAME, HEALTH_FIELDS_ES, PROFILE_FREE_TEXT_ES, WORD_RE, load_name_tokens,
    load_records, load_reviewed_false_positives, mask, name_tokens_in, norm_token, require_file,
    write_json, write_jsonl,
)

ID_RE = re.compile(r"^CLIENTE_\d{3}::(v\d{2,}|s\d{2,})(-\d+)?$")


# --------------------------------------------------------------------------- #
# Identifiers                                                                  #
# --------------------------------------------------------------------------- #

def build_id_map(chunks: list[dict]) -> tuple[dict[int, str], dict]:
    """Return {chunk_index: new_id} plus statistics. Deterministic."""
    stats = Counter()
    versionless_ord: dict[str, int] = defaultdict(int)
    groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(chunks):
        code = r["meta"]["cliente"]
        v = r["meta"].get("version_dieta")
        if v is None:
            versionless_ord[code] += 1
            base = f"{code}::s{versionless_ord[code]:02d}"
            stats["without_version"] += 1
        else:
            base = f"{code}::v{int(v):02d}"
            stats["with_version"] += 1
        groups[base].append(i)
    new_id: dict[int, str] = {}
    for base, idxs in groups.items():
        if len(idxs) == 1:
            new_id[idxs[0]] = base
            continue
        stats["collision_groups"] += 1
        stats["chunks_in_collisions"] += len(idxs)
        ordered = sorted(idxs, key=lambda i: (chunks[i]["meta"]["archivo"], i))
        for k, i in enumerate(ordered, start=1):
            new_id[i] = base if k == 1 else f"{base}-{k}"
    assert len(set(new_id.values())) == len(chunks), "new ids are not unique"
    assert all(ID_RE.match(x) for x in new_id.values()), "unexpected id format"
    return new_id, dict(stats)


# --------------------------------------------------------------------------- #
# Free-text sweep (masked contexts only)                                       #
# --------------------------------------------------------------------------- #

def masked_context(s: str, token_norm: str, name_set: set[str], width: int = 45) -> str:
    """Context around the first occurrence of the token, with EVERY dictionary
    token masked (not only the searched one)."""
    pos = None
    for m in WORD_RE.finditer(s):
        if norm_token(m.group(0)) == token_norm:
            pos = m
            break
    if pos is None:
        return ""
    a, b = max(0, pos.start() - width), min(len(s), pos.end() + width)
    frag = s[a:b].replace("\n", " ⏎ ")
    frag = WORD_RE.sub(lambda m: mask(m.group(0)) if norm_token(m.group(0)) in name_set else m.group(0), frag)
    frag = DETECTORS["full_date"].sub("[FECHA]", frag)
    return ("…" if a > 0 else "") + frag + ("…" if b < len(s) else "")


def sweep(chunks, new_id, name_set, fp_set, profiles):
    by_tok: dict[str, dict] = defaultdict(lambda: {"masked_token": "", "length": 0, "chunks": 0, "ids": [], "contexts": []})
    for i, r in enumerate(chunks):
        for t in set(name_tokens_in(r["text"], name_set, use_stop=True, extra_stop=fp_set)):
            cell = by_tok[t]
            cell["masked_token"], cell["length"] = mask(t), len(t)
            cell["chunks"] += 1
            if len(cell["ids"]) < 12:
                cell["ids"].append(new_id[i])
            if len(cell["contexts"]) < 3:
                cell["contexts"].append(masked_context(r["text"], t, name_set))
        intol = r["meta"].get("intolerancias")
        if intol:
            for t in set(name_tokens_in(intol, name_set, use_stop=True, extra_stop=fp_set)):
                cell = by_tok[t]
                cell["masked_token"], cell["length"] = mask(t), len(t)
                cell["in_meta_intolerances"] = cell.get("in_meta_intolerances", 0) + 1
                if len(cell["contexts"]) < 3:
                    cell["contexts"].append("[meta.intolerances] " + masked_context(intol, t, name_set))
    years = []
    for i, r in enumerate(chunks):
        for m in DETECTORS["birth_year"].finditer(r["text"]):
            a, b = max(0, m.start() - 40), min(len(r["text"]), m.end() + 40)
            frag = r["text"][a:b].replace("\n", " ⏎ ")
            frag = WORD_RE.sub(lambda mm: mask(mm.group(0)) if norm_token(mm.group(0)) in name_set else mm.group(0), frag)
            frag = re.sub(r"(?<!\d)(19[3-9]\d|200\d)(?!\d)", "[AÑO]", frag)
            years.append({"id": new_id[i], "context": frag})
    profile_hits = []
    if profiles:
        for p in profiles:
            for k in PROFILE_FREE_TEXT_ES:
                v = p.get(k)
                if not v:
                    continue
                for t in set(name_tokens_in(v, name_set, use_stop=True, extra_stop=fp_set)):
                    profile_hits.append({"client_code": p["code"], "field": FIELD_RENAME.get(k, k),
                                         "masked_token": mask(t), "length": len(t),
                                         "context": masked_context(v, t, name_set, width=30) if k not in HEALTH_FIELDS_ES else "<TEXTO_MEDICO omitted>"})
    tokens_out = []
    for t, cell in sorted(by_tok.items(), key=lambda kv: -kv[1]["chunks"]):
        c = dict(cell)
        c["_private_normalized_token"] = t  # stays in _private/, never on stdout
        tokens_out.append(c)
    return {"tokens_in_text": tokens_out, "years_in_text": years, "profile_free_text": profile_hits}


# --------------------------------------------------------------------------- #
# Optional token substitution in text                                          #
# --------------------------------------------------------------------------- #

import unicodedata as _ud
_RTF_HEX = re.compile(r"\'([0-9a-fA-F]{2})")


def normalize_text(s: str) -> str:
    """Unicode NFC + decoding of RTF hex escapes ('f1 -> ñ): decomposed or escaped characters split words
    (a decomposed ñ breaks a word in two fragments) and create false name hits downstream."""
    s = _ud.normalize("NFC", s)
    return _RTF_HEX.sub(lambda m: bytes.fromhex(m.group(1)).decode("latin-1"), s)


def make_substituter(tokens_norm: set[str]):
    if not tokens_norm:
        return lambda s: (normalize_text(s), 0)

    def sub(s: str) -> tuple[str, int]:
        n = 0
        s = normalize_text(s)

        def rep(m):
            nonlocal n
            if norm_token(m.group(0)) in tokens_norm:
                n += 1
                return "[NOMBRE]"
            return m.group(0)
        return WORD_RE.sub(rep, s), n
    return sub


def rename_meta(meta: dict) -> dict:
    return {FIELD_RENAME.get(k, k): v for k, v in meta.items() if k != "archivo"}


# --------------------------------------------------------------------------- #
# main                                                                         #
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--diets", required=True, type=Path)
    ap.add_argument("--meal-chunks", type=Path)
    ap.add_argument("--name-map", required=True, type=Path)
    ap.add_argument("--profiles", type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--private-dir", required=True, type=Path)
    ap.add_argument("--substitute", type=Path, help="JSON list of normalised tokens to replace by [NOMBRE] in text")
    ap.add_argument("--false-positives", type=Path, help="private JSON list of reviewed non-personal dictionary hits")
    args = ap.parse_args()

    chunks = load_records(require_file(args.chunks))
    diets = load_records(require_file(args.diets))
    name_set = load_name_tokens(args.name_map)
    fp_set = load_reviewed_false_positives(args.false_positives)
    profiles = load_records(args.profiles) if args.profiles else None
    subs = set()
    if args.substitute:
        subs = {norm_token(t) for t in json.loads(require_file(args.substitute).read_text(encoding="utf-8"))}
    substitute = make_substituter(subs)

    if len(chunks) != len(diets):
        raise SystemExit(f"chunks ({len(chunks)}) and diets ({len(diets)}) differ in record count")
    for r, d in zip(chunks, diets):
        if r["meta"]["archivo"] != d["archivo"] or r["meta"]["cliente"] != d["cliente"]:
            raise SystemExit("chunks and structured diets are not aligned record by record")

    new_id, id_stats = build_id_map(chunks)
    key_to_new = {(r["meta"]["cliente"], r["meta"]["archivo"]): new_id[i] for i, r in enumerate(chunks)}
    text_sweep = sweep(chunks, new_id, name_set, fp_set, profiles)

    log = Counter()
    out_chunks, id_map = [], {}
    for i, r in enumerate(chunks):
        meta = rename_meta(r["meta"])
        text, n = substitute(r["text"]); log["substitutions_chunk_text"] += n
        if meta.get("intolerances"):
            meta["intolerances"], n2 = substitute(meta["intolerances"]); log["substitutions_meta_intolerances"] += n2
        out_chunks.append({"id": new_id[i], "text": text, "meta": meta})
        id_map[new_id[i]] = {"original_file": r["meta"]["archivo"], "client_code": r["meta"]["cliente"],
                             "diet_version": r["meta"].get("version_dieta"), "source_index": i, "original_id": r["id"]}
    log["diet_chunks"] = write_jsonl(args.out_dir / "diet_chunks.jsonl", out_chunks)

    out_diets = []
    for i, d in enumerate(diets):
        nd = {"id": new_id[i]}
        for k, v in d.items():
            if k == "archivo":
                continue
            if k == "objetivo":
                v, n = substitute(v); log["substitutions_goal_text"] += n
                nd["goal_text"] = v
                continue
            if k == "notas":
                nv = []
                for s in v:
                    s2, n = substitute(s); log["substitutions_notes"] += n; nv.append(s2)
                v = nv
            elif k == "comidas":
                nv = {}
                for mk, items in v.items():
                    ni = []
                    for s in items:
                        s2, n = substitute(s); log["substitutions_meals"] += n; ni.append(s2)
                    nv[mk] = ni
                v = nv
            nd[FIELD_RENAME.get(k, k)] = v
        out_diets.append(nd)
    write_json(args.out_dir / "structured_diets.json", out_diets)
    log["structured_diets"] = len(out_diets)

    if args.meal_chunks:
        mc = load_records(require_file(args.meal_chunks))
        out_mc, missing = [], 0
        for r in mc:
            base = key_to_new.get((r["meta"]["cliente"], r["meta"]["archivo"]))
            if base is None:
                missing += 1
                continue
            slot = r["meta"].get("comida") or r["id"].rsplit("::", 1)[-1]
            meta = rename_meta(r["meta"])
            meta.pop("comida", None); meta["meal_slot"] = slot
            text, n = substitute(r["text"]); log["substitutions_meal_text"] += n
            if meta.get("intolerances"):
                meta["intolerances"], _ = substitute(meta["intolerances"])
            out_mc.append({"id": f"{base}::{slot}", "text": text, "meta": meta})
        if missing:
            raise SystemExit(f"{missing} meal chunks without a matching diet")
        log["meal_chunks"] = write_jsonl(args.out_dir / "meal_chunks.jsonl", out_mc)
        log["meal_chunks_unique_ids"] = len(set(r["id"] for r in out_mc))

    write_json(args.private_dir / "id_map.json", id_map)
    write_json(args.private_dir / "text_sweep.json", text_sweep)
    log.update({f"id_{k}": v for k, v in id_stats.items()})
    log["unique_ids"] = len(set(new_id.values()))
    log["substitution_tokens_configured"] = len(subs)
    log["reviewed_false_positives"] = len(fp_set)
    write_json(args.private_dir / "anonymize_log.json", dict(log))

    print("== Identifiers ==")
    for k, v in id_stats.items():
        print(f"  {k}: {v}")
    print(f"  unique ids: {log['unique_ids']} / {len(chunks)}")
    print("== Written ==")
    for k in ("diet_chunks", "structured_diets", "meal_chunks", "meal_chunks_unique_ids"):
        if k in log:
            print(f"  {k}: {log[k]}")
    print("== Text substitutions ==", {k: v for k, v in log.items() if k.startswith("substitutions")})
    print(f"\n== Free-text sweep: {len(text_sweep['tokens_in_text'])} candidate tokens (masked) ==")
    for c in text_sweep["tokens_in_text"]:
        print(f"  {c['masked_token']:12s} len={c['length']:2d} chunks={c['chunks']:4d}"
              + (f" meta.intolerances={c['in_meta_intolerances']}" if c.get("in_meta_intolerances") else ""))
        for ctx in c["contexts"]:
            print(f"      · {ctx}")
    print(f"\n== Years 19xx/200x in text: {len(text_sweep['years_in_text'])} ==")
    for a in text_sweep["years_in_text"]:
        print(f"  {a['id']}: {a['context']}")
    print(f"\n== Profiles: name tokens in free text: {len(text_sweep['profile_free_text'])} ==")
    for h in text_sweep["profile_free_text"]:
        print(f"  {h['client_code']} [{h['field']}] {h['masked_token']} len={h['length']}: {h['context']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
