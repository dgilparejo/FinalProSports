# -*- coding: utf-8 -*-
"""Fase 9: the repository must deliver what the working copy has. Two real failures motivated this test:
an unanchored `models/` pattern (meant for model weights) silently kept 44 files of frontend/src/app/models/ out of every commit
since S8, and inline `# comments` on pattern lines (not allowed by git) made two guard patterns inert.

Checks (all through git itself, so they see exactly what git sees):
  1. .gitignore files carry no inline comment (a `#` after a pattern is part of the pattern, not a comment);
  2. every ignore pattern that names a directory is either a known data / tooling guard or anchored;
  3. no file under the source, test, docs, schema or run-configuration trees is ignored (only caches and build output may be);
  4. sentinel paths: a frontend model file is not ignored; the data guards still fire.
Skipped silently when git is not available (the test needs the .git directory of the checkout).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # TFM/code
# `docs/` NO esta en esta lista, y es deliberado: la documentacion del proyecto es la memoria, y lo que el codigo
# escribe en `docs/` (informes del pipeline, figuras del arnes) es SALIDA GENERADA. Por eso el `.gitignore` la ignora
# entera y este test no puede exigir que sus ficheros esten versionados.
SOURCE_TREES = ("backend/src", "backend/tests", "backend/db", "pipeline/src", "pipeline/tests", "frontend/src", ".idea/runConfigurations",
                ".githooks", "tools")
IGNORABLE = re.compile(r"(^|/)(__pycache__/|.*\.pyc$|\.pytest_cache/|\.import_linter_cache/|coverage/|\.angular/|dist/|node_modules/|[^/]*\.egg-info/)")   # build output
# Unanchored directory patterns that are DELIBERATELY global: data guards (values are Spanish, identifiers English, so they cannot
# collide with source folders) and language / tool caches. Anything else that names a directory must be anchored or path-qualified.
GLOBAL_GUARDS = {"_dataset/", "_meta/", "clientes/", "PREPARACIONES-*/", "db_*/", "__pycache__/", ".pytest_cache/", ".import_linter_cache/",
                 "*.egg-info/", ".sass-cache/", ".idea/", ".c9/", ".settings/"}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def have_git() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def ignore_files():
    yield ROOT / ".gitignore"
    fe = ROOT / "frontend" / ".gitignore"
    if fe.exists():
        yield fe


def test_no_inline_comments_in_gitignore():
    offenders = []
    for f in ignore_files():
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s and not s.startswith("#") and " #" in s:
                offenders.append(f"{f.relative_to(ROOT)}:{n}: {s}")
    assert not offenders, "inline comments are part of the pattern in git: " + "; ".join(offenders)


def test_directory_patterns_are_anchored_or_known_guards():
    loose = []
    for f in ignore_files():
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("!"):
                continue
            if s.endswith("/") and "/" not in s[:-1] and not s.startswith("/") and s not in GLOBAL_GUARDS:
                loose.append(f"{f.relative_to(ROOT)}:{n}: {s}")
    assert not loose, "unanchored directory pattern (would match that name ANYWHERE, e.g. under src/): " + "; ".join(loose)


def test_no_source_file_is_ignored():
    if not have_git():
        return
    out = git("ls-files", "-o", "-i", "--exclude-standard", "--", *SOURCE_TREES)
    assert out.returncode == 0, out.stderr
    swallowed = [p for p in out.stdout.splitlines() if p and not IGNORABLE.search(p)]
    assert not swallowed, f"{len(swallowed)} file(s) under the source trees are ignored and therefore never committed: {swallowed[:10]}"


def test_sentinel_paths():
    if not have_git():
        return
    assert git("check-ignore", "-q", "frontend/src/app/models/client/index.ts").returncode == 1, "frontend/src/app/models must be versioned"
    assert git("check-ignore", "-q", "backend/src/finalprosports/domain/model/rule.py").returncode == 1
    # `docs/` es salida generada en el árbol PRIVADO (la documentación de trabajo vive fuera del repositorio) y
    # contenido versionado en el PÚBLICO, donde el README cita los informes y una afirmación sin su evidencia al lado
    # no vale nada. Así que los dos centinelas de documentación solo aplican donde esa regla existe; el resto —el
    # dataset, el árbol de clientes, `.env`, los modelos— aplican siempre. Lo detectó `verify_clean_clone` sobre un
    # clon del árbol público: allí este test fallaba por hacer lo correcto.
    docs_ignored = git("check-ignore", "-q", "docs/anything.md").returncode == 0
    guards = ["_dataset/diets.jsonl", "clientes/CLIENTE_001/x.md", ".env", "models/e5.bin"]
    if docs_ignored:
        guards += ["docs/evaluation/RESULTS.md", "docs/anything.md"]
    else:
        print("     (este árbol versiona docs/: los centinelas de documentación no aplican)")
    for guard in guards:
        assert git("check-ignore", "-q", guard).returncode == 0, f"guard no longer fires: {guard}"
    # La excepcion declarada del `.gitignore`: `docs/` es salida generada MENOS este fichero, que es la fuente de
    # todas las cifras de la evaluacion y la memoria lo cita. Si un dia la negacion se rompe (basta con excluir el
    # directorio entero en vez de su contenido), el fichero desaparece del repositorio sin que nadie lo note.
    assert git("check-ignore", "-q", "docs/evaluation/results.json").returncode == 1,         "docs/evaluation/results.json debe estar VERSIONADO: es la fuente de las cifras que cita la memoria"
    if not docs_ignored:      # en el árbol público, además, los informes que el README cita tienen que estar
        for informe in ("docs/evaluation/RESULTS.md", "docs/evaluation/SYNTHETIC_QUALITY.md"):
            assert git("check-ignore", "-q", informe).returncode == 1, f"{informe} debe estar versionado en el árbol público"


def test_no_source_file_carries_a_stray_control_character():
    """A control character in source is never intentional, and one of them was a live bug.

    ``anonymize_client_tree.HEADER_RE`` was committed with a literal BACKSPACE where a word boundary belonged, so
    the header pattern could not match anything and its rewrite branch was dead from S0 onwards. It came from a
    shell heredoc collapsing the escape while the file was being edited -- silent, invisible in every editor and
    in ``git diff``, and impossible to spot by reading. The class is cheap to exclude outright: TAB and newline
    are the only control characters a source file has any business containing.
    """
    offenders = []
    for tree in SOURCE_TREES:
        for path in (ROOT / tree).rglob("*"):
            if not path.is_file() or path.suffix not in (".py", ".ts", ".html", ".sql", ".json", ".sh", ".cfg", ".toml", ".md", ".xml"):
                continue
            if IGNORABLE.search(path.relative_to(ROOT).as_posix()):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            found = sorted({ord(c) for c in text if ord(c) < 32 and c not in (chr(10), chr(9))})
            if found:
                offenders.append((path.relative_to(ROOT).as_posix(), found))
    assert not offenders, offenders[:10]



def test_no_test_is_defined_after_its_own_runner_block():
    """A test defined below `if __name__ == "__main__":` is never executed by the standalone runner.

    The runner collects `globals()` at the moment it runs, so anything defined further down the file does not exist
    yet. Appending to a test file is the natural way to add a test, which makes this a trap that costs nothing to
    fall into and shows no symptom: the suite reports OK, with fewer tests than it has. It happened in
    `pipeline/tests/test_pipeline_v3.py`, where five tests -- including one that was ALREADY there and failing --
    sat dormant until the block was moved to the end.
    """
    import ast
    offenders = []
    for tree_name in ("backend/tests", "pipeline/tests"):
        for path in (ROOT / tree_name).rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            main_line = None
            for node in tree.body:
                if isinstance(node, ast.If) and isinstance(node.test, ast.Compare)                         and getattr(node.test.left, "id", "") == "__name__":
                    main_line = node.lineno
                if main_line is not None and isinstance(node, ast.FunctionDef)                         and node.name.startswith("test_") and node.lineno > main_line:
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}::{node.name}")
    assert not offenders, offenders

if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
