# -*- coding: utf-8 -*-
"""
Task B — Rebuild `clientes/` without real names in file names or content.

Source: the ORIGINAL per-client tree (moved to the encrypted custody; path given with --source, never hard-coded).
Target: $FPS_DATA_DIR/clientes/CLIENTE_NNN/ with files renamed to
  DIETA__vNN.md / DIETA__sNN.md   (the diet id suffix of _private/id_map.json when the file produced a diet;
                                    DIETA__xNN.md for diet files the original parser discarded, ordinal by name)
  ENTRENO__nNN.md, DATOS__nNN.md, ANALITICA__nNN.md, OTRO__nNN.md (ordinal per type, alphabetical by original name)
  PERFIL.md                        (kept)
Content: the first line "# <TYPE> CLIENTE_NNN vN: <original descriptor>" carried the original file name -> rewritten;
the four reviewed third-party tokens (custody text_substitutions.json) -> [NOMBRE]; any residual token of the name
dictionary (plaintext map from custody when available, hashed otherwise) -> [NOMBRE] and counted.
Updates _private/id_map.json (file_on_disk) and writes _private/client_files_map.json for the non-diet files
(new name -> original name; the original names ARE personal data, hence _private).
Prints aggregates only.
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
    DETECTORS, STOPWORDS, WORD_RE, load_name_set, norm_token, require_file, write_json,
)

TYPES = ("DIETA", "ENTRENO", "DATOS", "ANALITICA", "OTRO")
HEADER_RE = re.compile(r"^# (DIETA|ENTRENO|DATOS|ANALITICA|OTRO) (CLIENTE_\d{3})\b.*$")   # legacy header carried the original file name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, type=Path, help="original clientes/ tree (custody)")
    ap.add_argument("--target", required=True, type=Path, help="new clientes/ tree inside FPS_DATA_DIR")
    ap.add_argument("--id-map", required=True, type=Path)
    ap.add_argument("--name-map", type=Path, help="plaintext name_map.json (custody) if available")
    ap.add_argument("--hashed", type=Path, help="_private/name_tokens_hashed.json")
    ap.add_argument("--substitutions", type=Path, help="custody text_substitutions.json (tokens -> [NOMBRE])")
    ap.add_argument("--files-map", required=True, type=Path, help="output: _private/client_files_map.json")
    args = ap.parse_args()

    src = require_file(args.source)
    id_map = json.loads(require_file(args.id_map).read_text(encoding="utf-8"))
    name_set = load_name_set(args.name_map, args.hashed)
    hashed_fp = getattr(name_set, "is_false_positive", None)
    subs = set()
    if args.substitutions and args.substitutions.exists():
        subs = {norm_token(t) for t in json.loads(args.substitutions.read_text(encoding="utf-8"))}
    # original file name -> new diet id suffix (per client)
    by_orig: dict[tuple[str, str], str] = {}
    for new_id, v in id_map.items():
        by_orig[(v["client_code"], v["original_file"])] = new_id.split("::", 1)[1]

    log = Counter()
    files_map: dict[str, dict] = {}
    residual_tokens: Counter = Counter()
    args.target.mkdir(parents=True, exist_ok=True)
    for cdir in sorted(p for p in src.iterdir() if p.is_dir()):
        code = cdir.name
        out_dir = args.target / code
        out_dir.mkdir(exist_ok=True)
        per_type: dict[str, list[Path]] = defaultdict(list)
        for f in sorted(cdir.iterdir()):
            if not f.is_file():
                continue
            if f.name == "PERFIL.md":
                per_type["PERFIL"].append(f)
                continue
            t = f.name.split("__", 1)[0]
            per_type[t if t in TYPES else "OTRO"].append(f)
        counters: Counter = Counter()
        for t, files in per_type.items():
            for f in files:
                if t == "PERFIL":
                    new_name = "PERFIL.md"
                elif t == "DIETA" and (code, f.name) in by_orig:
                    new_name = f"DIETA__{by_orig[(code, f.name)]}.md"
                    log["diet_files_with_id"] += 1
                else:
                    counters[t] += 1
                    prefix = "x" if t == "DIETA" else "n"
                    new_name = f"{t}__{prefix}{counters[t]:02d}.md"
                    log[f"{t.lower()}_files_ordinal"] += 1
                text = f.read_text(encoding="utf-8", errors="ignore")
                lines = text.split("\n")
                m = HEADER_RE.match(lines[0]) if lines else None
                if m:
                    lines[0] = f"# {m.group(1)} {code} {new_name[:-3].split('__', 1)[-1] if '__' in new_name else ''}".rstrip()   # e.g. "# DIETA CLIENTE_016 v05"
                    log["headers_rewritten"] += 1
                body = "\n".join(lines)
                # known third-party tokens -> [NOMBRE]
                n_sub = 0

                def rep(mo):
                    nonlocal n_sub
                    w = norm_token(mo.group(0))
                    is_name = (w in name_set and w not in STOPWORDS and not (hashed_fp and hashed_fp(w))
                               and not w.startswith("CLIENTE"))
                    if w in subs or is_name:
                        n_sub += 1
                        residual_tokens[w[0] + "*" * (len(w) - 1)] += 1
                        return "[NOMBRE]"
                    return mo.group(0)
                body = WORD_RE.sub(rep, body)
                # name tokens are checked with the dictionary + STOPWORDS filter (rep above masks any dictionary hit,
                # so re-run the audit-grade check to count what would have survived)
                log["tokens_masked_in_content"] += n_sub
                for det, marker in (("email", "[EMAIL]"), ("phone", "[TEL]"), ("iban", "[IBAN]"), ("nie", "[DNI]"), ("dni", "[DNI]")):
                    body, n_det = DETECTORS[det].subn(marker, body)
                    if n_det:
                        log[f"masked_{det}"] += n_det
                (out_dir / new_name).write_text(body, encoding="utf-8", newline="\n")
                log["files_written"] += 1
                if new_name != "PERFIL.md":
                    files_map[f"{code}/{new_name}"] = {"original_file": f.name, "type": t}
        log["clients"] += 1
    # id_map: file on disk
    for new_id, v in id_map.items():
        v["file_on_disk"] = f"{v['client_code']}/DIETA__{new_id.split('::', 1)[1]}.md"
    write_json(args.id_map, id_map)
    write_json(args.files_map, {"_doc": "new file name -> original file name of the non-diet documents (original names are personal data)",
                                "files": files_map})
    summary = {"counts": dict(log), "masked_token_shapes_top": residual_tokens.most_common(15)}
    write_json(args.target.parent / "_dataset" / "client_tree_log.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
