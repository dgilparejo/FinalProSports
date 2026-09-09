"""Where the data lives. The code repository (``TFM/code``) never contains data: the frozen dataset and the anonymised
client tree are located through two settings, ``FPS_DATA_DIR`` (the processed-data tree: ``_dataset/``, ``_meta/``,
``clientes/``) and ``FPS_DATASET_DIR`` (the frozen dataset itself), read from the environment or from the ``.env`` file at
the repository root. Relative values are resolved from the repository root; the defaults live in ``.env.example``, not here,
so no module of the code tree carries a path into the data tree (S0, tested by ``tests/architecture/test_no_legacy_paths.py``).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_ROOT_MARKERS = ("docker-compose.yml", "Makefile")


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """The directory that holds docker-compose.yml and the Makefile (``TFM/code``).

    ``FPS_REPO_ROOT`` gana cuando esta puesta, y existe por el CONTENEDOR: dentro de la imagen de la API no hay
    repositorio, hay una copia de lo que la API necesita en tiempo de ejecucion (``src/``, ``db/`` y el criterio
    versionado de ``pipeline/src/pipeline/data``), sin ``docker-compose.yml`` ni ``Makefile``. Buscar los marcadores
    hacia arriba desde ``/app/src/...`` no encuentra nada y la aplicacion no llegaba ni a importarse. La alternativa
    -- meter el compose y el Makefile en la imagen solo para que la busqueda tenga exito -- seria mentirle a la
    funcion sobre donde esta, y ademas metaria en el contenedor ficheros que no pinta nada tener ahi.
    """
    override = os.environ.get("FPS_REPO_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if all((parent / marker).exists() for marker in _ROOT_MARKERS):
            return parent
    raise RuntimeError("repository root not found (expected a directory with docker-compose.yml and Makefile, "
                       "or FPS_REPO_ROOT pointing at the deployed tree)")


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
        raise RuntimeError(f"{name} is not set: copy .env.example to .env at the repository root (the data tree lives outside the code tree)")
    path = Path(value).expanduser()
    return path if path.is_absolute() else (repo_root() / path).resolve()


def data_dir() -> Path:
    """Processed-data tree (``_dataset/``, ``_meta/``, ``clientes/``): FPS_DATA_DIR."""
    return _path_setting("FPS_DATA_DIR")


def dataset_dir() -> Path:
    """Frozen dataset (``diets.jsonl``, ``foods.json`` … and every evaluation artefact): FPS_DATASET_DIR."""
    return _path_setting("FPS_DATASET_DIR")


def docs_dir() -> Path:
    """Where the code writes its reports and figures (``docs/`` at the repository root).

    GENERATED OUTPUT, not part of the deliverable: the documentation of the project is the report (memoria), and `docs/`
    is ignored by git. The directory is created on demand by whoever runs the harness or the pipeline.
    """
    return repo_root() / "docs"
