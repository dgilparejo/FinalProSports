"""Strip absolute file-system paths out of the v3 JSON artefacts.

Several E1 tools record the path they were given in a ``source`` field. That is harmless on the reference machine
and not harmless in the dataset: the path here contains a first name that is also a client's, so the tree audit
found it in ``validated_rules.json`` and went red. It is the same class of leak as the converter stderr in F1 --
personal data arriving through a field nobody thinks of as text.

Paths are replaced by their base name, which is the only part that carries meaning for a reader anyway.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline_v3 import paths
else:
    from . import paths

# A whole string that is a file path. Matched against the WHOLE value, because these paths contain spaces and a
# search pattern stops at the first one, leaving the interesting half behind -- which is what the first version did.
# The trailing extension is required: without it "PERDER GRASA / DEFINIR" is a path too, and the rule rewrites a
# goal string into " DEFINIR". A cleaner that silently edits data it was not aimed at is worse than the leak it fixes.
_PATH_LIKE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]|\.{1,2}[\\/])?(?:[^\\/\n]*[\\/])+[^\\/\n]+\.[A-Za-z0-9]{1,5}$")


def _clean(value):
    if isinstance(value, str):
        if "\n" not in value and ("\\" in value or "/" in value) and _PATH_LIKE.match(value.strip()):
            return re.split(r"[\\/]", value.strip())[-1]
        return value
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or paths.dataset_dir_v3()
    changed: list[str] = []
    for path in sorted(out_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cleaned = _clean(data)
        if cleaned != data:
            path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            changed.append(path.name)
    return {"files_rewritten": changed, "count": len(changed)}


def main() -> None:
    argparse.ArgumentParser(description="strip absolute paths from the v3 artefacts").parse_args()
    print(json.dumps(build(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
