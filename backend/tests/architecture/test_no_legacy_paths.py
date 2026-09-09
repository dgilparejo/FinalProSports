# -*- coding: utf-8 -*-
"""S0: the code tree carries no path into the data tree nor into the pre-S0 layout.

The data lives outside the repository and is reached only through FPS_DATA_DIR / FPS_DATASET_DIR (paths.py); the defaults
are in .env.example, never in code. This test scans every source and configuration file of the three components for
absolute paths, references to the data tree and references to the old single-folder layout.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # TFM/code
SCAN_DIRS = ("backend/src", "backend/tests", "backend/db", "pipeline/src", "pipeline/tests", "frontend/src", "docker", ".idea/runConfigurations")
SCAN_FILES = ("Makefile", "docker-compose.yml", "backend/alembic.ini", "backend/pyproject.toml", "backend/setup.cfg", "backend/Dockerfile",
              "pipeline/pyproject.toml", "frontend/package.json", "frontend/angular.json")
EXTENSIONS = {".py", ".ts", ".html", ".sass", ".scss", ".css", ".json", ".toml", ".cfg", ".ini", ".yml", ".yaml", ".xml", ".sql"}
SKIP_PARTS = {"node_modules", ".venv", "__pycache__", ".angular", "dist"}
FORBIDDEN = re.compile(r"_TFM_PROCESADO|Dietas[/\\]|[A-Za-z]:[\\/]Users|/home/|/Users/|finalprosports[/\\](src|tests|docs|web|db|\.venv)|\.\./Dietas")


def files():
    for d in SCAN_DIRS:
        for p in (ROOT / d).rglob("*"):
            if p.is_file() and p.suffix in EXTENSIONS and not (set(p.parts) & SKIP_PARTS) and p.name != Path(__file__).name:
                yield p
    for f in SCAN_FILES:
        p = ROOT / f
        if p.exists():
            yield p


def test_no_path_into_the_data_tree_or_the_old_layout():
    hits = []
    for p in files():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{i}")
    assert not hits, "paths into the data tree / old layout found (use FPS_DATA_DIR / FPS_DATASET_DIR):\n" + "\n".join(hits[:40])


def test_env_example_declares_the_data_settings():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "FPS_DATA_DIR=" in text and "FPS_DATASET_DIR=" in text


def test_the_three_components_are_recognisable():
    assert (ROOT / "backend" / "pyproject.toml").exists()
    assert (ROOT / "pipeline" / "pyproject.toml").exists()
    assert (ROOT / "frontend" / "package.json").exists()
    assert len(list((ROOT / ".idea" / "runConfigurations").glob("*.xml"))) == 11


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
