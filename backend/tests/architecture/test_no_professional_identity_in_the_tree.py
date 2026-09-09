# -*- coding: utf-8 -*-
"""EL NOMBRE DEL PROFESIONAL NO ESTÁ EN NINGÚN FICHERO DEL ÁRBOL. Ni en el código, ni en un test, ni en un nombre de
fichero.

Existe por un incidente del 2026-09-09: el repositorio PÚBLICO llevaba el nombre y la marca comercial del preparador
en texto plano, y los llevaba **dentro del detector de datos personales** — `pii_common.DETECTORS`, `sanitize.py` y
`test_dataset.py` tenían los patrones escritos como literales. Un detector que lleva el dato dentro lo publica cada
vez que se publica el código, y ninguna de las puertas anteriores lo veía: la auditoría por diccionario compara con
los nombres del CORPUS —los clientes—, y el preparador no es un cliente; la puerta de formas busca filas por persona,
y esto era una constante en un fichero de código.

Cómo funciona sin volver a publicar lo que protege: los patrones se leen de la CUSTODIA
(`pii_common.custody_patterns`: `FPS_PII_PATTERNS`, o `$FPS_DATASET_DIR/_private/pii_patterns.json`). Este fichero no
contiene ninguno, y los hallazgos se imprimen ENMASCARADOS (primera letra y asteriscos), como manda la regla 1 de
manejo de datos.

Sin custodia no puede comprobar nada y lo DICE (no pasa en verde en silencio). En la máquina del titular la custodia
está, así que la comprobación tiene dientes; en el clon de un desconocido no hay nada que proteger, porque el árbol ya
está limpio — y de eso responde la ejecución de la puerta en `verify_clean_clone.sh`, que sí le pasa la custodia.

La segunda mitad del fichero no necesita ningún secreto: prohíbe FORMAS de identidad de contacto en los ficheros
propios —un correo que no sea de prueba, un teléfono español— y esa parte vale igual en cualquier árbol.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src" / "data_tools"))

from pii_common import DETECTORS, custody_patterns  # noqa: E402

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".angular", ".idea",
             ".pytest_cache", "coverage", ".mypy_cache", "site-packages", "_private"}
# Ficheros de terceros: `package-lock.json` lleva las URLs del registro npm y los correos de los autores de cada
# dependencia. No son datos nuestros y no se pueden limpiar sin romper la instalación reproducible.
THIRD_PARTY = {"package-lock.json", "requirements.lock"}
TEXT_SUFFIXES = {".py", ".ts", ".js", ".html", ".json", ".jsonl", ".md", ".yml", ".yaml", ".sh", ".sql", ".cfg",
                 ".toml", ".ini", ".txt", ".sass", ".scss", ".css", ".env", ".example", ".xml", ".properties", ""}

# LOS PATRONES SON LOS DE LA CASA (`pii_common.DETECTORS`), no unos nuevos escritos aquí. Escribí los míos y me
# comieron dos falsos positivos que los suyos ya tenían resueltos: los dígitos dentro de un sha1 («6f3a9…») se leen
# como un móvil de nueve cifras si no se excluyen las fronteras hexadecimales, y una tasa decimal
# («0.3496932515337423») también. Dos detectores del mismo dato divergen en la primera corrección; este usa el que
# ya está medido contra el corpus.
PHONE = DETECTORS["phone"]
EMAIL_ANY = DETECTORS["email"]
# Las direcciones de la demostración viven bajo el TLD reservado `.invalid` (RFC 2606) y se ensamblan en ejecución.
EMAIL_OK = re.compile(r"@(?:demo\.invalid|example\.(?:com|org)|localhost)", re.I)


def mask(s: str) -> str:
    return s[0] + "*" * (len(s) - 1) if s else s


def _git_delivered() -> list[Path] | None:
    """Lo que git ENTREGARÍA: versionado más lo nuevo no ignorado. `None` si aquí no hay git."""
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [ROOT / f for f in out.stdout.split(chr(0)) if f]


def files_to_scan():
    """Los ficheros QUE PUEDEN VIAJAR, no los que hay en disco.

    La diferencia no es teórica: mi primera versión recorría el disco y señaló `.env`, donde el titular tiene el
    contacto comercial real del profesional — y ahí es donde debe estar, porque `.env` está ignorado y no sale de su
    máquina. Un test que exige limpiar eso obliga a romper la configuración local para poner una puerta en verde, que
    es la forma más rápida de que alguien la desactive. El criterio correcto es el mismo que usa el montador del
    árbol público: lo que git entrega."""
    entregados = _git_delivered()
    candidatos = entregados if entregados is not None else [p for p in ROOT.rglob("*") if p.is_file()]
    for path in candidatos:
        if not path.is_file():
            continue
        partes = path.relative_to(ROOT).parts
        if any(p in SKIP_DIRS for p in partes) or path.name in THIRD_PARTY:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def find(regex: re.Pattern[str], check_names: bool = True) -> list[str]:
    """[ruta:línea  literal enmascarado]. Nunca imprime el literal."""
    out = []
    for path in files_to_scan():
        rel = path.relative_to(ROOT).as_posix()
        if check_names and (m := regex.search(path.name)):
            out.append(f"{rel}  [NOMBRE DE FICHERO]  {mask(m.group(0))}")
        try:
            texto = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n, linea in enumerate(texto.splitlines(), 1):
            if m := regex.search(linea):
                out.append(f"{rel}:{n}  {mask(m.group(0))}")
    return out


def test_the_professionals_name_and_brand_are_nowhere_in_the_tree():
    """La comprobación del incidente. Con custodia tiene dientes; sin ella, lo dice y no finge."""
    patrones = custody_patterns()
    if not patrones:
        print("     (sin patrones de custodia: no se puede comprobar la identidad del profesional. "
              "Se leen de FPS_PII_PATTERNS o de $FPS_DATASET_DIR/_private/pii_patterns.json)")
        return
    regex = re.compile("|".join(re.escape(p) for p in patrones), re.I)
    hallazgos = find(regex)
    assert not hallazgos, (f"el nombre o la marca del profesional aparecen en {len(hallazgos)} sitio(s) del árbol "
                           f"(literales enmascarados):\n  " + "\n  ".join(hallazgos[:30]) +
                           "\nLos patrones NO se escriben en el código: se leen de la custodia "
                           "(pii_common.custody_patterns).")


def test_no_real_e_mail_address_in_our_own_files():
    """Un correo que no sea de prueba. Los de la demostración viven bajo el TLD reservado `.invalid` (RFC 2606)."""
    hallazgos = [h for h in find(EMAIL_ANY, check_names=False) if not EMAIL_OK.search(h)]
    assert not hallazgos, ("correos que no son de prueba (enmascarados):\n  " + "\n  ".join(hallazgos[:30]) +
                           "\nLos de la demostración se ensamblan en ejecución bajo `.invalid`.")


def test_no_spanish_phone_number_in_our_own_files():
    hallazgos = find(PHONE, check_names=False)
    assert not hallazgos, ("teléfonos con forma española real (enmascarados):\n  " + "\n  ".join(hallazgos[:30]) +
                           "\nLos de la demostración usan el prefijo 000, que ningún número español tiene.")


def test_the_check_is_not_vacuous():
    """Que el barrido MIRE de verdad: si no recorre ficheros, las tres comprobaciones de arriba son decorativas."""
    n = sum(1 for _ in files_to_scan())
    assert n > 200, f"el barrido solo ve {n} ficheros: algo excluye demasiado"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
