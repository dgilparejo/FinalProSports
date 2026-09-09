"""Location of the data tree for the offline pipeline and the data tools.

Mirror of ``finalprosports.infrastructure.config.paths`` kept inside the pipeline component so that the ETL does not depend
on the backend's infrastructure layer. ``FPS_DATA_DIR`` (processed-data tree) and ``FPS_DATASET_DIR`` (frozen dataset) come
from the environment or from the ``.env`` file at the repository root; relative values are resolved from the repository root.
The defaults live in ``.env.example`` — never in code (S0).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_ROOT_MARKERS = ("docker-compose.yml", "Makefile")


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Igual que ``finalprosports.infrastructure.config.paths.repo_root``, incluida la salida por ``FPS_REPO_ROOT``.

    Este modulo es un ESPEJO declarado del otro para que el ETL no dependa de la capa de infraestructura del backend.
    Un espejo que se comporta distinto es peor que no tenerlo: dentro del contenedor no hay `docker-compose.yml` ni
    `Makefile`, asi que sin la salida el cargador del corpus fallaria justo donde el backend ya funciona.
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
    return _path_setting("FPS_DATA_DIR")


def dataset_dir() -> Path:
    return _path_setting("FPS_DATASET_DIR")


def docs_dir() -> Path:
    return repo_root() / "docs"


def backend_src() -> Path:
    """``backend/src``: lets the pipeline import the domain model without installing the backend package."""
    return repo_root() / "backend" / "src"
