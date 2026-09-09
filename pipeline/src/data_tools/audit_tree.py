# -*- coding: utf-8 -*-
"""
Task B — Whole-tree anonymisation audit (permanent test). Acceptance criterion: ZERO.

Walks one or more roots (default: the code repository and the processed-data tree FPS_DATA_DIR) and checks
  * every directory name and file name for tokens of the real-name dictionary,
  * the content of every text file (.md .json .jsonl .txt .py .csv) for name tokens, e-mails, phones, DNI/NIE, IBAN.
The dictionary is the hashed one (_private/name_tokens_hashed.json) unless a plaintext map is given.
Prints counts only; masked token shapes at most. Exit code 1 when anything is found.
Excluded by default: .git/, __pycache__/, the private mapping id_map.json / client_files_map.json (they map to the
ORIGINAL file names on purpose) and the hashed dictionary itself.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import data_dir, dataset_dir, repo_root  # noqa: E402
from pii_common import DETECTORS, WORD_RE, load_name_set, mask, name_tokens_in, norm_token  # noqa: E402

TEXT_EXT = {".md", ".json", ".jsonl", ".txt", ".py", ".csv", ".yaml", ".yml", ".toml", ".cfg", ".ini"}
HARD = ("email", "phone", "dni", "nie", "iban")
DEFAULT_EXCLUDE = {"id_map.json", "client_files_map.json", "name_tokens_hashed.json", "reviewed_false_positives.json"}
PSEUDONYM_IN_TREE = re.compile(r"CLIENTE_\d+")        # para distinguir «árbol sin corpus» de «corpus sin diccionario»
SKIP_FILES = {"package-lock.json"}   # npm lockfile: third-party maintainer e-mails and package names, not project content
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".import_linter_cache", "node_modules", ".angular", "dist", ".idea", ".venv", "models", "hf_models"}   # .venv: third-party code, not project content (7.415 false positives)
WORK_AREAS = {"_work", "_originals"}   # docs/reference/_work|_originals: declared, git-ignored custody work areas — outside the criterion, COUNTED separately


def hits_in(text: str, name_set) -> list[str]:
    """Dictionary tokens in the text, minus those the data owner has reviewed and declared non-personal (common Spanish words
    that collide with a surname; the decision lives as a DIGEST in the private hashed dictionary, never as a literal)."""
    fp = getattr(name_set, "is_false_positive", None)
    return [t for t in name_tokens_in(text, name_set) if not (fp and fp(t))]


def audit(root: Path, name_set, exclude_files: set[str], reviewed: set[str] | None = None) -> dict:
    hits = Counter()
    shapes = Counter()
    where = Counter()
    n_files = n_dirs = 0
    work_files = 0
    for p in root.rglob("*"):
        if any(part in WORK_AREAS for part in p.parts):
            work_files += p.is_file()
            continue
        if any(part in SKIP_DIRS for part in p.parts) or p.name in SKIP_FILES:
            continue
        if p.is_dir():
            n_dirs += 1
            for t in hits_in(p.name, name_set):
                hits["name_in_dir_name"] += 1; shapes[mask(t)] += 1; where[str(p.parent.relative_to(root))] += 1
            continue
        n_files += 1
        for t in hits_in(p.name, name_set):
            hits["name_in_file_name"] += 1; shapes[mask(t)] += 1; where[str(p.parent.relative_to(root))] += 1
        if p.name in exclude_files or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        toks = hits_in(text, name_set)
        if toks:
            hits["name_in_content"] += len(toks); hits["files_with_name_in_content"] += 1
            where[str(p.relative_to(root))] += len(toks)
            for t in set(toks):
                shapes[mask(t)] += 1
        for det in HARD:
            n = len(DETECTORS[det].findall(text))
            if n:
                hits[f"{det}_in_content"] += n; where[str(p.relative_to(root))] += n
    return {"root": str(root.name), "dirs": n_dirs, "files": n_files, "work_area_files_excluded": work_files, "hits": dict(hits), "total_hits": sum(hits.values()),
            "masked_shapes_top": shapes.most_common(10), "locations_top": where.most_common(10)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, nargs="*", help="trees to audit (default: the code repository and FPS_DATA_DIR)")
    ap.add_argument("--hashed", type=Path, default=None, help="hashed name dictionary (default: FPS_DATASET_DIR/_private/name_tokens_hashed.json)")
    ap.add_argument("--name-map", type=Path, help="plaintext dictionary (custody) if available")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--exclude", nargs="*", default=sorted(DEFAULT_EXCLUDE))

    args = ap.parse_args()
    roots = args.root or [repo_root(), data_dir()]
    hashed = args.hashed or dataset_dir() / "_private" / "name_tokens_hashed.json"
    try:
        name_set = load_name_set(args.name_map, hashed)
    except FileNotFoundError:
        # SIN DICCIONARIO no se puede auditar por nombres, y aquí hay que decidir entre dos cosas muy distintas:
        #   * un árbol que NO lleva corpus (el repositorio público): la auditoría por nombres no aplica, porque no hay
        #     nombres contra los que comparar ni corpus del que provengan. Se dice y se sale con 0, nombrando la
        #     garantía que sí rige allí: `test_public_tree_has_no_personal_data.py`, que busca FORMAS.
        #   * un árbol que SÍ lleva corpus y ha perdido el diccionario: entonces la auditoría no puede hacer su
        #     trabajo y callarse sería lo peor de todo. Falla, y dice qué falta.
        # Antes reventaba con un FileNotFoundError en los dos casos, y en el público eso convertía un acierto en un
        # fallo. Lo encontró `verify_clean_clone` sobre un clon del árbol público.
        con_corpus = [str(r) for r in roots if any(
            PSEUDONYM_IN_TREE.search(f.read_text(encoding="utf-8", errors="ignore")[:200_000])
            for f in list(Path(r).rglob("diets.jsonl"))[:3])]
        if con_corpus:
            print(f"ABORTADO: hay corpus en {con_corpus} y falta el diccionario ({hashed}). La auditoría no puede correr.",
                  file=sys.stderr)
            return 2
        print(json.dumps({"skipped": "sin diccionario de nombres: este árbol no lleva corpus, así que la auditoría por "
                                     "NOMBRES no aplica", "roots": [str(r) for r in roots],
                          "the_gate_here_is": "backend/tests/architecture/test_public_tree_has_no_personal_data.py "
                                              "(busca FORMAS de dato personal, no nombres)"},
                         ensure_ascii=False, indent=1))
        return 0
    results = [audit(root, name_set, set(args.exclude)) for root in roots]
    for r in results:
        r["reviewed_false_positives"] = len(getattr(name_set, "false_positives", ()))
    print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=1))
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return 1 if any(r["total_hits"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
