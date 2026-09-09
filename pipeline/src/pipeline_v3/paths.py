"""Locations for the v3 rebuild.

Same contract as ``pipeline.paths`` (``FPS_DATA_DIR`` / ``FPS_DATASET_DIR`` from the environment or the root ``.env``),
plus the two directories the rebuild owns and the location of the raw sources.

Nothing here writes inside ``FPS_DATASET_DIR``: the frozen v2 dataset is read-only for the whole rebuild.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_ROOT_MARKERS = ("docker-compose.yml", "Makefile")


@lru_cache(maxsize=1)
def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if all((parent / marker).exists() for marker in _ROOT_MARKERS):
            return parent
    raise RuntimeError("repository root not found (expected a directory with docker-compose.yml and Makefile)")


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    path = repo_root() / ".env"
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _path_setting(name: str) -> Path:
    value = os.environ.get(name) or _dotenv().get(name)
    if not value:
        raise RuntimeError(f"{name} is not set: copy .env.example to .env at the repository root")
    path = Path(value).expanduser()
    return path if path.is_absolute() else (repo_root() / path).resolve()


def data_dir() -> Path:
    return _path_setting("FPS_DATA_DIR")


def dataset_dir_v2() -> Path:
    """The frozen v2 dataset. READ ONLY for the whole rebuild.

    Deliberately NOT ``FPS_DATASET_DIR``. That setting names whichever dataset is *active*, so the moment v3 is
    activated it stops pointing at v2 and every comparison, guard and byte-for-byte check in this package would
    quietly start comparing v3 against itself. The frozen dataset has a fixed location; only the active one moves.
    """
    value = os.environ.get("FPS_DATASET_V2_DIR") or _dotenv().get("FPS_DATASET_V2_DIR")
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (repo_root() / path).resolve()
    return data_dir() / "_dataset"


def active_dataset_dir() -> Path:
    """Whatever ``FPS_DATASET_DIR`` currently names: v2 before activation, v3 after."""
    return _path_setting("FPS_DATASET_DIR")


def dataset_dir_v3() -> Path:
    """Where v3 is built: a sibling of the frozen dataset, never the active one."""
    value = os.environ.get("FPS_DATASET_V3_DIR") or _dotenv().get("FPS_DATASET_V3_DIR")
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (repo_root() / path).resolve()
    return data_dir() / "_dataset_v3"


def work_dir() -> Path:
    """Converted plain text and other intermediates.

    MUST live outside both audited trees (the repository and ``FPS_DATA_DIR``). Rule 6 of `las reglas de manejo de datos personales de la memoria` holds the
    project tree to zero real names, and converted source text is exactly the material that would break it: the first
    version of this rebuild defaulted the cache inside ``FPS_DATA_DIR`` and the PII audit went red with 127 hits
    (names, e-mails and phones) before a line of it was committed. The default is therefore a sibling of the processed
    tree, and :func:`assert_work_dir_is_outside_audited_trees` refuses to run if that ever stops being true.

    The text written here is anonymised first (see :mod:`pipeline_v3.identity`); the location is the second line of
    defence, not the first.
    """
    value = os.environ.get("FPS_V3_WORK_DIR") or _dotenv().get("FPS_V3_WORK_DIR")
    if value:
        path = Path(value).expanduser()
        path = path if path.is_absolute() else (repo_root() / path).resolve()
    else:
        path = data_dir().parent / "_v3_work"
    assert_work_dir_is_outside_audited_trees(path)
    return path


def assert_work_dir_is_outside_audited_trees(path: Path) -> None:
    """Fail loudly rather than write converted source text where the PII audit demands zero."""
    for audited in (repo_root(), data_dir()):
        try:
            path.resolve().relative_to(audited.resolve())
        except ValueError:
            continue
        raise RuntimeError(
            f"the v3 work directory ({path}) is inside an audited tree ({audited}): converted source text carries "
            "real names, e-mails and phones and must never be written there (DATA_HANDLING_RULES.md rule 6, criterion zero)"
        )


def sources_root() -> Path:
    """``TFM/PREPARACIONES``: the raw documents. Read only, never modified."""
    value = os.environ.get("FPS_SOURCES_DIR") or _dotenv().get("FPS_SOURCES_DIR")
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (repo_root() / path).resolve()
    return data_dir().parent.parent / "PREPARACIONES"


def client_tree() -> Path:
    """The ``clientes`` subtree of ``FPS_DATA_DIR``: the v2 markdown tree (fallback source, plan B)."""
    return data_dir() / "clientes"


def docs_dir() -> Path:
    return repo_root() / "docs"
