# -*- coding: utf-8 -*-
"""Punto de entrada del servicio `bootstrap`: deja la base de datos LISTA antes de que arranque la API.

Existe por un requisito de entrega: quien clone el repositorio tiene que poder levantar la aplicación entera con
`docker compose up` y encontrársela funcionando, sin ejecutar `make migrate`, ni `make load`, ni `make demo`. Hasta
ahora esos tres pasos se hacían a mano desde el host, y eso convierte «arranca la aplicación» en un procedimiento de
cuatro comandos que hay que leer en el README.

No vive en `backend/` ni en `pipeline/` a propósito: no es una capa del hexágono ni una etapa del ETL, es el guion de
arranque de una IMAGEN. Se limita a llamar, en orden, a las tres entradas que ya existen y que se siguen usando desde
el host; no duplica ninguna lógica.

  1. `alembic upgrade head`                        — el esquema
  2. `pipeline/load_postgres.py --apply --replace` — el corpus (la base de casos que el motor recupera)
  3. `cli.seed_demo`                               — los clientes ficticios de demostración

**Idempotente**, porque `docker compose up` se ejecuta muchas veces: cada paso se salta si ya está hecho. Sin eso, el
segundo arranque recargaría 50.000 componentes para nada y volvería a sembrar los clientes de demostración.

**Los embeddings NO se calculan.** No es un olvido: la estrategia de recuperación entregada es `attributes`, cuyo
`requires_embedding` es `False`, así que la columna `diets.embedding` no la lee nadie en la configuración que se
entrega. Calcularla obligaría a descargar 1,1 GB del modelo e5 desde Hugging Face en el primer arranque — varios
minutos y una dependencia de red — para llenar una columna que la aplicación no consulta. Se puede pedir con
`FPS_BOOTSTRAP_EMBED=1`, que es lo que hace falta para las estrategias `vector` e `hybrid` y para el arnés.

Falla ruidosamente y con el motivo escrito: un arranque que se rinde en silencio deja una aplicación vacía y una
pantalla sin explicación, que es peor que no arrancar.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("FPS_REPO_ROOT", "/app"))
BACKEND = ROOT / "backend"
LOADER = ROOT / "pipeline" / "src" / "pipeline" / "load_postgres.py"


def log(step: str, msg: str) -> None:
    print(f"[bootstrap] {step:<10} {msg}", flush=True)


def run(step: str, args: list[str], cwd: Path) -> None:
    log(step, "$ " + " ".join(args))
    r = subprocess.run(args, cwd=str(cwd))
    if r.returncode != 0:
        log(step, f"FALLO (codigo {r.returncode})")
        raise SystemExit(r.returncode)


def counts() -> dict[str, int]:
    """Qué hay ya en la base de datos. Se consulta con psycopg directamente: aquí todavía no hay aplicación que montar."""
    import psycopg
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    out = {}
    with psycopg.connect(url) as c, c.cursor() as cur:
        for name, sql in (("diets", "SELECT count(*) FROM diets"),
                          ("foods", "SELECT count(*) FROM foods"),
                          ("embeddings", "SELECT count(*) FROM diets WHERE embedding IS NOT NULL"),
                          ("portfolio", "SELECT count(*) FROM client_profiles WHERE NOT is_corpus_case")):
            try:
                cur.execute(sql)
                out[name] = int(cur.fetchone()[0])
            except Exception:                      # la tabla aún no existe: es el primer arranque
                c.rollback()
                out[name] = 0
    return out


def dataset_is_present() -> Path | None:
    """El dataset que se va a cargar, o None. `diets.jsonl` es el fichero sin el cual no hay base de casos."""
    raw = os.environ.get("FPS_DATASET_DIR")
    if not raw:
        return None
    d = Path(raw)
    return d if (d / "diets.jsonl").exists() else None


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        log("config", "DATABASE_URL no está definida")
        return 1

    # 1 · esquema. Alembic es idempotente por diseño: si ya está en head, no hace nada.
    run("migrate", [sys.executable, "-m", "alembic", "upgrade", "head"], BACKEND)

    before = counts()
    log("estado", f"dietas={before['diets']} alimentos={before['foods']} "
                  f"embeddings={before['embeddings']} cartera={before['portfolio']}")

    # 2 · corpus
    dataset = dataset_is_present()
    if before["diets"] > 0:
        log("corpus", f"ya cargado ({before['diets']} dietas): no se toca")
    elif dataset is None:
        log("corpus", "NO HAY BASE DE CASOS. FPS_DATASET_DIR no apunta a un dataset con diets.jsonl.")
        log("corpus", "La aplicación arrancará y se podrá navegar, pero pedir una propuesta dará 422:")
        log("corpus", "el motor es basado en casos y no hay casos que recuperar.")
    else:
        log("corpus", f"cargando desde {dataset}")
        run("corpus", [sys.executable, str(LOADER), "--apply", "--replace"], ROOT)

    # 3 · embeddings, solo si se piden (ver la cabecera de este fichero)
    if os.environ.get("FPS_BOOTSTRAP_EMBED") == "1":
        run("embed", [sys.executable, str(ROOT / "pipeline" / "src" / "pipeline" / "embed_corpus.py")], ROOT)
    else:
        log("embed", "omitido: la estrategia entregada es `attributes` y no lee `diets.embedding` "
                     "(FPS_BOOTSTRAP_EMBED=1 para calcularlos)")

    # 4 · clientes de demostración, solo si la cartera está vacía. Nunca `--reset`: borraría los del profesional.
    after = counts()
    if after["portfolio"] > 0:
        log("demo", f"la cartera ya tiene {after['portfolio']} clientes: no se siembra")
    elif after["diets"] == 0:
        log("demo", "omitido: sin base de casos no se les puede generar una dieta")
    else:
        run("demo", [sys.executable, "-m", "finalprosports.infrastructure.adapter.inbound.cli.seed_demo"], BACKEND)

    final = counts()
    log("listo", f"dietas={final['diets']} alimentos={final['foods']} cartera={final['portfolio']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
