#!/usr/bin/env bash
# Monta el ÁRBOL PÚBLICO a partir de este repositorio: el mismo código, el criterio agregado, la base de casos
# sintética, y ni un dato personal. No toca nada de este árbol: escribe en el directorio de salida.
#
# Lo que hace, en este orden y sin sorpresas:
#   1. copia SOLO lo que git tiene versionado (nada de .venv, node_modules, .env ni artefactos)
#   2. quita el corpus real (`seed/dataset/`) y el expediente REAL del e2e
#   3. pone en su sitio `seed/dataset_public/` -> `seed/dataset/`, que es donde el compose lo busca
#   4. cambia el README por el público y deja `SYNTHETIC.json` a la vista
#   5. pasa LA PUERTA con FPS_PUBLIC_TREE=1: si encuentra un dato personal, aborta y borra la salida
#
# Uso:  ./tools/build_public_tree.sh [DESTINO]     (por defecto ../_public_tree)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/../_public_tree}"
PY="${PY:-$ROOT/backend/.venv/Scripts/python.exe}"
[[ -x "$PY" ]] || PY="$ROOT/backend/.venv/bin/python"

echo "== árbol público"
echo "   origen:  $ROOT"
echo "   destino: $OUT"

if [[ ! -f "$ROOT/seed/dataset_public/synthetic_params.json" || ! -f "$ROOT/seed/dataset_public/diets.jsonl" ]]; then
  echo "FALTA la base pública. Ejecuta antes: make public-dataset && make public-params && make public-synth" >&2
  exit 2
fi

# El destino se rehace desde cero, PERO conservando su `.git` si ya es un repositorio: así el montador sirve para
# ACTUALIZAR el árbol público (arreglas algo en el privado, remontas, commiteas encima) y no solo para crearlo. Sin
# esto, la primera actualización se llevaba por delante la historia y el remoto del repositorio publicado.
GITDIR=""
if [[ -d "$OUT/.git" ]]; then
  GITDIR="$(mktemp -d)/git"
  mv "$OUT/.git" "$GITDIR"
  echo "   (conservo el .git del destino: esto es una actualización, no un estreno)"
fi
rm -rf "$OUT"
mkdir -p "$OUT"
# El SELLO. El montador puede morir a mitad (una puerta que falla, un python que revienta) y entonces el destino
# queda medio copiado: un arbol sin `seed/dataset` ni `tools/`. Commitear eso publica un repositorio que no arranca,
# y ha pasado. El sello se escribe SOLO al final; si no esta, el arbol no se commitea.
STAMP="$OUT/.public-tree-ok"
if [[ -n "$GITDIR" ]]; then
  mv "$GITDIR" "$OUT/.git"
fi

# 1 · solo lo que git entregaría: versionado MÁS lo nuevo que no está ignorado. Se incluye lo nuevo a propósito,
#     para poder montar y auditar el árbol público ANTES de commitear; lo ignorado (.venv, node_modules, .env,
#     seed/dataset_public) no entra por definición.
( cd "$ROOT" && git ls-files -z --cached --others --exclude-standard ) | while IFS= read -r -d '' f; do
  mkdir -p "$OUT/$(dirname "$f")"
  cp -p "$ROOT/$f" "$OUT/$f"
done

# 2 · fuera el corpus real y el expediente real
rm -rf "$OUT/seed/dataset"
rm -f  "$OUT/backend/tests/e2e/fixtures/client_recurrent_volume.json"

# 3 · la base pública ocupa el sitio donde el compose busca los datos
mkdir -p "$OUT/seed/dataset"
cp -p "$ROOT/seed/dataset_public/." "$OUT/seed/dataset/" -r
# El log del cargador se escribe DENTRO del dataset cuando la carga corre desde el host, y no es corpus: es el parte de
# una ejecución concreta (fecha, filas, avisos). En el repositorio publicado solo genera commits de ruido.
rm -f "$OUT/seed/dataset/load_postgres_log.json" "$OUT/seed/dataset/embed_corpus_log.json"

# 3b · el informe de evaluación, sin sus filas por caso. `results.json` es agregado salvo `failures.worst`: veinte
#      filas con el identificador de la dieta (aunque enmascarado, lleva el NÚMERO DE VERSIÓN: «::v42» dice que esa
#      persona tiene cuarenta y dos dietas), su sexo, su tramo de edad y su objetivo. Nadie puede ponerle nombre, pero
#      es la única granularidad por persona que quedaba y en abierto no hace falta: `failures.summary`, que es lo que
#      cita la memoria, se queda intacto. En el árbol privado la lista sigue estando, que es donde sirve para depurar.
python - "$OUT/docs/evaluation/results.json" <<'EOF'
import io, json, sys
p = sys.argv[1]
d = json.load(io.open(p, encoding="utf-8"))
n = len((d.get("failures") or {}).pop("worst", []) or [])
d.setdefault("failures", {})["worst_withheld"] = {
    "n": n,
    "why": ("Las filas por caso (identificador con número de versión, sexo, tramo de edad, objetivo) se retiran del "
            "árbol público: son la única granularidad por persona del informe y no hacen falta en abierto. El resumen "
            "agregado de esas veinte consultas está en `failures.summary`."),
}
io.open(p, "w", encoding="utf-8", newline=chr(10)).write(json.dumps(d, ensure_ascii=False, indent=1))
print(f"   results.json: retiradas {n} filas por caso; queda failures.summary")
EOF

# 3b-bis · en el árbol público la documentación SÍ se versiona. El `.gitignore` del privado ignora `/docs/*` porque
#          allí los documentos de trabajo viven fuera del repositorio; si esa regla viaja, el público publica un README
#          que cita informes que no están. Una afirmación sin su evidencia al lado no vale nada.
python - "$OUT/.gitignore" <<'EOF'
import io, sys
p = sys.argv[1]
fuera = ("/docs/*", "!/docs/evaluation/", "/docs/evaluation/*", "!/docs/evaluation/results.json")
lineas = [l for l in io.open(p, encoding="utf-8").read().splitlines() if l.strip() not in fuera]
cabecera = ["# En el arbol PUBLICO los documentos SI se versionan (el README cita el informe de calidad y la",
            "# justificacion de la separacion). Las reglas que ignoraban /docs/* son convenio del arbol privado.",
            "",
            "# El sello que escribe el montador al TERMINAR BIEN. Vive en el arbol de salida, no en el repositorio.",
            "/.public-tree-ok"]
io.open(p, "w", encoding="utf-8", newline=chr(10)).write(chr(10).join(cabecera + lineas) + chr(10))
print("   .gitignore: la documentacion se versiona en el arbol publico")
EOF

# 3c · los dos documentos que el README público CITA. Van aparte porque el árbol privado ignora `/docs/*` (los
#      documentos de trabajo viven fuera del repositorio), y aun así estos dos tienen que viajar: son la evidencia de
#      lo que el README afirma. Los dos son agregados sin ninguna persona dentro.
for doc in "docs/evaluation/SYNTHETIC_QUALITY.md" "docs/data/PUBLIC_RELEASE.md"             "docs/evaluation/RESULTS.md" "docs/evaluation/DISCUSSION.md"; do
  if [[ -f "$ROOT/$doc" ]]; then
    mkdir -p "$OUT/$(dirname "$doc")"
    cp -p "$ROOT/$doc" "$OUT/$doc"
    echo "   documento publicado: $doc"
  else
    echo "   AVISO: falta $doc (el README lo cita). Ejecuta \`make public-quality\`." >&2
  fi
done

# 3d · los .md publicados, sin seudónimos del corpus. `RESULTS.md` trae la misma tabla de las veinte peores consultas
#      que se retiró de `results.json`, y ahí el identificador lleva el NÚMERO DE VERSIÓN: «::v42» dice que esa persona
#      tiene cuarenta y dos dietas. Se enmascara el código y se deja caer la versión; los números de la evaluación no
#      los toca nadie. En el árbol privado los identificadores siguen intactos, que es donde sirven.
python - "$OUT/docs" <<'EOF'
import io, re, sys
from pathlib import Path
raiz = Path(sys.argv[1])
codigo = re.compile(r"CLIENTE_(\d+)(::v\d+)?")
for md in sorted(raiz.rglob("*.md")):
    texto = md.read_text(encoding="utf-8")
    vistos: dict[str, str] = {}
    def sustituye(m):
        clave = m.group(1)
        vistos.setdefault(clave, f"CASO_{len(vistos) + 1:02d}")
        return vistos[clave]
    nuevo = codigo.sub(sustituye, texto)
    if nuevo != texto:
        io.open(md, "w", encoding="utf-8", newline=chr(10)).write(nuevo)
        print(f"   {md.name}: {len(vistos)} seudonimos enmascarados (y sin numero de version)")
EOF

# 4 · README público
if [[ -f "$OUT/README.public.md" ]]; then
  mv -f "$OUT/README.public.md" "$OUT/README.md"
fi
# CLAUDE.md es el cuaderno de trabajo del árbol privado (habla del corpus, de la custodia y de las rutas del titular):
# no pinta nada en el público y se queda fuera.
rm -f "$OUT/CLAUDE.md" "$OUT/backend/CLAUDE.md"

# 5 · la puerta, sobre el árbol de salida
echo "== la puerta (FPS_PUBLIC_TREE=1)"
if ! ( cd "$OUT/backend" && FPS_PUBLIC_TREE=1 PYTHONUTF8=1 "$PY" ./tests/architecture/test_public_tree_has_no_personal_data.py ); then
  echo "ABORTADO: el árbol público lleva datos personales. No se entrega nada." >&2
  rm -rf "$OUT"
  exit 3
fi

# 6 · sus propias instantáneas doradas. Las del árbol privado son de propuestas hechas con el corpus REAL; con otra
#     base de casos el motor entrega otra dieta, así que aquí se regeneran CONTRA LA BASE SINTÉTICA. Se hace dentro
#     del árbol de salida (nunca en el privado, donde son la referencia medida) y solo si hay base de datos: sin
#     DATABASE_URL el árbol se entrega sin instantáneas nuevas y se avisa.
if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "== instantáneas doradas del árbol público (contra su base sintética)"
  ( cd "$OUT/backend" && FPS_DATASET_DIR="$OUT/seed/dataset" PYTHONUTF8=1 "$PY" -m pytest tests/golden -q       -p no:cacheprovider --update-snapshots 2>&1 | tail -2 )
  echo "== y ahora en verde, sin actualizar nada"
  ( cd "$OUT/backend" && FPS_DATASET_DIR="$OUT/seed/dataset" PYTHONUTF8=1 "$PY" -m pytest tests/golden -q       -p no:cacheprovider 2>&1 | tail -2 )
else
  echo "== AVISO: sin DATABASE_URL no se regeneran las instantáneas doradas; las que van son del corpus privado"
fi

echo "== auditoría PII sobre el árbol público"
( cd "$ROOT" && PYTHONUTF8=1 "$PY" pipeline/src/data_tools/audit_tree.py --root "$OUT" 2>/dev/null || true ) | tail -5

# los restos de pytest no son del repositorio
find "$OUT" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$OUT/backend/.pytest_cache" "$OUT/.pytest_cache" 2>/dev/null || true

{ date -u +"built %Y-%m-%dT%H:%M:%SZ"; echo "from $(cd "$ROOT" && git rev-parse --short HEAD 2>/dev/null || echo '?')"; } > "$STAMP"
echo "== hecho"
du -sh "$OUT" 2>/dev/null || true
echo "   ficheros: $(find "$OUT" -type f | wc -l)"
echo "   sello: $(cat "$STAMP")"
echo "   siguiente paso: cd $OUT && git add -A && git commit    (solo si existe .public-tree-ok)"
