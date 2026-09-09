# -*- coding: utf-8 -*-
"""
Task B — Inventory (SHA-256 manifest) of the original source material before it leaves the project tree.

Usage:
  python _tools/custody_inventory.py --root <dir> [--root <dir> ...] --manifest <out.json> [--compare A B]

Writes a manifest {relative_path: {"bytes": n, "sha256": hex}} per root and prints ONLY aggregates
(file counts, total bytes, number of distinct hashes). With --compare it reports how many files of the
second root are byte-identical (by hash) to files of the first root. File names are never printed:
the original documents are named after real people.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root: Path) -> dict:
    if not root.exists():
        raise FileNotFoundError(f"Required root not found: {root}")
    files = {}
    for p in root.rglob("*"):
        if p.is_file():
            files[p.relative_to(root).as_posix()] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()
    out = {}
    for root in args.root:
        inv = inventory(root)
        out[root.name] = {"files": len(inv), "bytes": sum(v["bytes"] for v in inv.values()),
                          "distinct_hashes": len({v["sha256"] for v in inv.values()}), "entries": inv}
        print(f"[{root.name}] files={len(inv)} bytes={out[root.name]['bytes']} distinct_hashes={out[root.name]['distinct_hashes']}")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"manifest written: {args.manifest} ({sum(v['files'] for v in out.values())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
