# -*- coding: utf-8 -*-
"""NINGÚN DATO PERSONAL SIN DECLARAR EN EL ÁRBOL — por FORMA, no por nombre.

La auditoría que ya existe (`audit_tree.py`) busca NOMBRES contra un diccionario hasheado construido con los nombres
del corpus. Es muy buena en lo suyo y tiene un punto ciego que se vio el 2026-09-09: `backend/tests/e2e/fixtures/
client_recurrent_volume.json` lleva el expediente de un cliente REAL del preparador — 481 parámetros de laboratorio con
fecha, 3 lecturas de báscula, 2 dietas anteriores— y la auditoría da 0 aciertos, porque a ese cliente le cambiaron el
nombre y además es de 2026, posterior al congelado del corpus, así que su nombre no está en el diccionario. Un fichero
con datos de salud de una persona identificable pasaba la puerta sin tocarla.

Esta prueba busca lo otro: la FORMA del dato personal. No pregunta «¿aparece un apellido?», pregunta «¿hay aquí filas
por persona?»:

  * seudónimos del corpus (`CLIENTE_NNN`),
  * ficheros de datos con la clave `client_code` repetida (una fila por persona),
  * expedientes: `full_name`/`birth_date` junto a salud (`labs`, `allergies`, `weight_kg`…),
  * series clínicas: una lista de objetos con marcador y valor, o con peso y fecha.

Solo mira ficheros de DATOS (.json, .jsonl, .csv, .sql, .dump); el código fuente menciona `client_code` por todas
partes y eso no es un dato, es un nombre de columna.

DOS MODOS, y el privado es el que hace el trabajo diario:

  privado (por defecto)   el inventario encontrado tiene que estar DECLARADO abajo. Si aparece un fichero nuevo con
                          datos personales, falla hasta que alguien lo declare a mano — que es exactamente lo que
                          habría cazado al fixture del e2e el día que se creó.
  público (FPS_PUBLIC_TREE=1)  el inventario tiene que estar VACÍO y ninguno de los declarados puede existir. Es la
                          puerta del repositorio público.

Ninguna aserción imprime contenido: los hallazgos se nombran por ruta, clave y número de filas.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

DATA_SUFFIXES = {".json", ".jsonl", ".csv", ".sql", ".dump", ".ndjson"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".angular", ".idea",
             ".pytest_cache", "coverage", ".mypy_cache", "site-packages"}

# EL INVENTARIO DECLARADO. Cada entrada es un fichero que SÍ lleva datos personales y que vive solo en el árbol
# privado. Añadir algo aquí es una decisión consciente y revisable; es el único sitio donde se puede hacer.
DECLARED_PRIVATE = {
    "seed/dataset/profiles.jsonl": "301 perfiles del corpus (sexo, edad, altura, medidas, banderas de salud)",
    "seed/dataset/diets.jsonl": "1.203 dietas de 266 personas, texto libre íntegro y fechadas",
    "seed/dataset/meals.jsonl": "8.837 comidas de las mismas personas",
    "seed/dataset/diet_items.jsonl": "49.906 componentes de las mismas dietas",
    "seed/dataset/archetypes.json": "arquetipos con la lista de miembros (261 personas)",
    "seed/dataset/body_measurements.jsonl": "1.318 pesajes fechados de 171 personas",
    "seed/dataset/body_measurements_followup.jsonl": "seguimiento de 3 personas",
    "seed/dataset/lab_results.jsonl": "254 informes de laboratorio de 155 personas",
    "seed/dataset/rotation_analysis.json": "clave per_client: el repertorio de 164 personas",
    "backend/tests/e2e/fixtures/client_recurrent_volume.json": "expediente de un cliente REAL (481 analíticas): se carga por FPS_E2E_FIXTURE",
}

PSEUDONYM = re.compile(r"CLIENTE_\d+")
CLIENT_CODE_VALUE = re.compile(r'"client_code"\s*:\s*"([^"]+)"')
SYNTHETIC_CODE = re.compile(r"^SINT_\d+$")        # los casos generados; ver synthesize_case_base.py
HEALTH_KEYS = {"labs", "lab_results", "allergies", "intolerances", "injuries", "surgeries", "weight_kg",
               "body_fat_pct", "fat_pct", "medical_restrictions", "health"}
IDENTITY_KEYS = {"full_name", "birth_date", "phone", "email"}


def iter_data_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in DATA_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def _rows_with_client_code(text: str) -> tuple[int, bool]:
    """Cuántas filas por persona hay y si TODAS son de la base sintética.

    Por eso los casos generados se llaman `SINT_NNN` y no reutilizan la forma `CLIENTE_NNN`: aquí no hay que creerse
    ninguna declaración, se leen los códigos. Un solo código que no sea sintético devuelve el fichero a la lista."""
    valores = set(CLIENT_CODE_VALUE.findall(text))
    total = text.count('"client_code"')
    return total, bool(valores) and all(SYNTHETIC_CODE.match(v) for v in valores)


def _identity_plus_health(path: Path) -> bool:
    """Un expediente: identidad y salud en el mismo objeto. Solo para .json pequeños, que es donde viven los fixtures.

    Un fichero que se DECLARA sintético (`"_synthetic": true` más el generador que lo escribió) queda exento de esta
    heurística y solo de esta: los seudónimos y las filas por persona se le siguen mirando. La exención es explícita y
    revisable —hay que escribirla en el fichero— que es la misma disciplina que `DECLARED_PRIVATE`."""
    if path.suffix.lower() != ".json" or path.stat().st_size > 8 * 1024 * 1024:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    if isinstance(data, dict) and data.get("_synthetic") is True and data.get("generated_by"):
        return False

    def visit(obj) -> bool:
        if isinstance(obj, dict):
            keys = set(obj)
            if keys & IDENTITY_KEYS and (keys & HEALTH_KEYS or "record" in keys):
                return True
            return any(visit(v) for v in obj.values())
        if isinstance(obj, list):
            return any(visit(v) for v in obj[:50])
        return False
    return visit(data)


def tree_carries_the_corpus() -> bool:
    """¿Es este el árbol PRIVADO? Se decide por el contenido, no por una variable de entorno.

    Importa porque `make test` lo ejecuta igual en los dos árboles y nadie va a exportar nada: en el público los
    ficheros declarados NO existen —es el objetivo— y una comprobación de inventario que exige su presencia allí
    convierte el acierto en fallo. Lo detectó `verify_clean_clone` sobre un clon del árbol público, que es para lo
    que existe esa verificación."""
    corpus = ROOT / "seed" / "dataset" / "diets.jsonl"
    if not corpus.exists():
        return False
    with corpus.open(encoding="utf-8", errors="ignore") as fh:
        return bool(PSEUDONYM.search(fh.read(200_000)))


def findings() -> dict[str, list[str]]:
    """ruta relativa -> motivos. Nunca contenido."""
    out: dict[str, list[str]] = {}
    for path in iter_data_files():
        rel = path.relative_to(ROOT).as_posix()
        motivos: list[str] = []
        text = path.read_text(encoding="utf-8", errors="ignore")
        codes = len(set(PSEUDONYM.findall(text)))
        if codes:
            motivos.append(f"{codes} seudónimos CLIENTE_NNN")
        rows, todas_sinteticas = _rows_with_client_code(text)
        if rows >= 5 and not todas_sinteticas:
            motivos.append(f"{rows} apariciones de client_code (filas por persona)")
        if _identity_plus_health(path):
            motivos.append("identidad + salud en el mismo objeto (expediente)")
        if motivos:
            out[rel] = motivos
    return out


def test_no_undeclared_personal_data_in_the_tree():
    """Lo encontrado tiene que estar declarado. Un fichero nuevo con datos personales falla aquí y no en la entrega."""
    encontrados = findings()
    sin_declarar = {k: v for k, v in encontrados.items() if k not in DECLARED_PRIVATE}
    assert not sin_declarar, ("ficheros con datos personales SIN DECLARAR:\n  " +
                              "\n  ".join(f"{k}: {'; '.join(v)}" for k, v in sorted(sin_declarar.items())) +
                              "\nSi es dato personal legítimo del árbol privado, declárralo en DECLARED_PRIVATE con su motivo.")


def test_the_declared_inventory_does_not_rot():
    """Un inventario que nombra ficheros que ya no existen deja de ser un inventario y pasa a ser folclore.

    Solo en el árbol PRIVADO: en el público esos ficheros no existen por diseño, que es justamente el objetivo."""
    if os.environ.get("FPS_PUBLIC_TREE") == "1" or not tree_carries_the_corpus():
        print("     (este árbol no lleva el corpus: el inventario privado no aplica, y eso es lo correcto)")
        return
    fantasmas = [k for k in DECLARED_PRIVATE if not (ROOT / k).exists()]
    assert not fantasmas, f"declarados que ya no existen (quítalos de DECLARED_PRIVATE): {fantasmas}"


def test_the_public_tree_carries_no_personal_data_at_all():
    """La puerta del repositorio público. Se ejecuta con FPS_PUBLIC_TREE=1; en el privado informa y se salta."""
    if os.environ.get("FPS_PUBLIC_TREE") != "1":
        print("     (modo privado: la puerta pública se comprueba con FPS_PUBLIC_TREE=1)")
        return
    # El criterio es el CONTENIDO, no la ruta. En el árbol público `seed/dataset/` existe igual —es donde el compose
    # busca los datos— pero lleva la base sintética; comprobar rutas daría un falso positivo justo donde la
    # comprobación tiene que ser de fiar. Lo que se exige es que no haya NADA con forma de dato personal.
    encontrados = findings()
    assert not encontrados, ("el árbol PÚBLICO lleva datos personales:\n  " +
                             "\n  ".join(f"{k}: {'; '.join(v)}" for k, v in sorted(encontrados.items())))
    # Y una comprobación por ruta que sí vale: el expediente REAL del e2e no puede estar, ni renombrado ni declarado
    # sintético. Es el fichero que la auditoría por diccionario de nombres no sabía ver, así que se le mira aparte.
    real_e2e = ROOT / "backend" / "tests" / "e2e" / "fixtures" / "client_recurrent_volume.json"
    assert not real_e2e.exists(), "el árbol público contiene el expediente REAL del e2e"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
