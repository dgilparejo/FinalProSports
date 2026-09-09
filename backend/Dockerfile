# Imagen de la API **y del arranque**: el mismo contenido sirve al servicio `api` y al servicio `bootstrap`, que aplica
# las migraciones, carga el corpus y siembra los clientes de demostración. Una sola imagen y no dos porque el arranque
# no es otra aplicación: es la misma con otro punto de entrada, y dos imágenes se desincronizarían.
#
# El contexto de build es la RAÍZ DEL REPOSITORIO, no `backend/`, por dos motivos: la API lee criterio versionado que
# vive fuera de `backend/` (`pipeline/src/pipeline/data/*.json`, que carga `FilePlausibilityEnvelopeAdapter`), y el
# arranque necesita el cargador entero (`pipeline/src/pipeline/load_postgres.py`).
#
# El árbol de dentro ESPEJA el del repositorio (`/app/backend`, `/app/pipeline`) en vez de aplanar `src` en `/app`.
# Cuesta una línea más y evita el problema real: `load_postgres.py` resuelve `REPO_ROOT / "backend" / "db" / schema.sql`
# y Alembic espera `backend/alembic.ini`. Con el árbol aplanado habría que parchear rutas en el código para contentar a
# la imagen, que es exactamente al revés de como debe ir.
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Dentro de la imagen no hay repositorio: no existen docker-compose.yml ni Makefile, que es lo que `repo_root()` busca
# hacia arriba. Se le dice dónde está en vez de meter en el contenedor dos ficheros que no pintan nada ahí.
ENV FPS_REPO_ROOT=/app
COPY backend/pyproject.toml backend/setup.cfg backend/alembic.ini ./backend/
COPY backend/src ./backend/src
COPY backend/db ./backend/db
COPY pipeline/src ./pipeline/src
COPY docker/bootstrap.py ./docker/bootstrap.py
RUN pip install --no-cache-dir -e ./backend
EXPOSE 8000
CMD ["uvicorn", "finalprosports.main:app", "--host", "0.0.0.0", "--port", "8000"]
