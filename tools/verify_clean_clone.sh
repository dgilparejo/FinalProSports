#!/usr/bin/env bash
# verify_clean_clone.sh — the truth test of the repository (Fase 9): what git status says about a working copy proves
# nothing; the deliverable is what a stranger gets from `git clone`. This script clones the COMMITTED tree (current branch, HEAD) into
# an empty folder and runs the documented bootstrap there, end to end, against an ISOLATED database container, then reports PASS / FAIL
# per step. `make verify-clean-clone` runs it; so does the IntelliJ configuration "11 · Verificar clon limpio".
#
# What it needs from the machine: python (3.13) on PATH, node 22 + npm, docker, network for PyPI / npm (dependency traffic only: the
# data never leaves the PC), and the working copy's .env for FPS_DATA_DIR / FPS_DATASET_DIR (the data tree lives outside every clone).
#
#   VERIFY_DIR      destination (default: <TEMP>/fps_clean_clone; must be bracket-free — Karma — and is WIPED first)
#   VERIFY_BRANCH   branch to clone (default: the current one)
#   VERIFY_DB_PORT  host port of the throw-away PostgreSQL container fps-verify-db (default 5433: high ports such as 55432 fall into the
#                   Hyper-V excluded ranges on Windows and docker cannot bind them; `netsh int ipv4 show excludedportrange protocol=tcp`)
#   VERIFY_API_PORT port of the API smoke run (default 58000)
#   VERIFY_KEEP=1   keep the container and the clone after the run (default: container removed, clone kept for inspection)
#
# The database URL uses 127.0.0.1, not localhost: the container binds IPv4 only and psycopg tries ::1 first, which cost ~130 s per process.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
winpath() { (cd "$1" 2>/dev/null && { pwd -W 2>/dev/null || pwd; }); }     # git.exe needs Windows paths when MSYS path conversion is off (detached runs)
ROOT_W="$(winpath "$ROOT")"
BRANCH="${VERIFY_BRANCH:-$(git -C "$ROOT_W" rev-parse --abbrev-ref HEAD)}"
TMPBASE="${LOCALAPPDATA:+$LOCALAPPDATA/Temp}"; TMPBASE="${TMPBASE:-${TEMP:-${TMPDIR:-/tmp}}}"
command -v cygpath >/dev/null 2>&1 && TMPBASE="$(cygpath -u "$TMPBASE")"
DEST="${VERIFY_DIR:-$TMPBASE/fps_clean_clone}"
PORT="${VERIFY_DB_PORT:-5433}"
API_PORT="${VERIFY_API_PORT:-58000}"
CONTAINER="fps-verify-db"
KC_PORT="${VERIFY_KC_PORT:-5480}"
KC_CONTAINER="fps-verify-keycloak"
PY_SYS="${VERIFY_PYTHON:-python}"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"          # never let a node process eat the machine (incident 2026-08-26)

case "$DEST" in *"["*|*"]"*) echo "VERIFY_DIR must not contain brackets: $DEST"; exit 2;; esac

RESULTS=()
FAILED=0
API_PID=""
T0=$(date +%s)

step() {  # step "<name>" <command...>   — runs in $DEST, records PASS / FAIL, prints the tail of the output on failure
  local name="$1"; shift
  local t=$(date +%s) out rc
  out=$(cd "$DEST" && "$@" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then
    RESULTS+=("PASS  $(printf '%-28s' "$name") $(( $(date +%s) - t ))s")
    echo "PASS  $name"
  else
    FAILED=1
    RESULTS+=("FAIL  $(printf '%-28s' "$name") $(( $(date +%s) - t ))s  (exit $rc)")
    echo "FAIL  $name (exit $rc)"; echo "$out" | tail -25 | sed 's/^/      /'
  fi
  return $rc
}

stop_api() {  # kill the process that LISTENS on the API port (the uvicorn child), not just the shell that started it: a killed subshell leaves the
  # server orphaned, holding the clone directory and the port. Windows (netstat/taskkill) and POSIX (lsof) variants.
  local pid
  if command -v taskkill >/dev/null 2>&1; then
    for pid in $(netstat -ano 2>/dev/null | awk -v p=":$API_PORT" '$2 ~ p"$" && /LISTENING/ {print $5}' | sort -u); do taskkill //F //PID "$pid" >/dev/null 2>&1; done
  elif command -v lsof >/dev/null 2>&1; then
    for pid in $(lsof -ti tcp:"$API_PORT" 2>/dev/null); do kill -9 "$pid" 2>/dev/null; done
  fi
  [ -n "$API_PID" ] && { kill "$API_PID" 2>/dev/null; wait "$API_PID" 2>/dev/null; }
  API_PID=""
}

cleanup() {
  stop_api
  if [ "${VERIFY_KEEP:-0}" != "1" ]; then docker rm -f "$CONTAINER" "$KC_CONTAINER" >/dev/null 2>&1; fi
}
trap cleanup EXIT

# ------------------------------------------------------------------------------------------------------------ 0. data paths
read_env() { grep -E "^$1=" "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d '\015'; }
# El CR se borra con '\015' (el escape OCTAL que interpreta `tr`) y no con '\r': entre comillas simples
# `\r` son dos caracteres y `tr -d '"\r'` acaba borrando también las letras r de las rutas.
abs() { local p="$1"; case "$p" in /*|[A-Za-z]:*) ;; *) p="$ROOT/$p";; esac; (cd "$p" 2>/dev/null && { pwd -W 2>/dev/null || pwd; }); }
# DONDE ESTAN LOS DATOS, y hay dos mundos:
#   * arbol PRIVADO: el corpus vive FUERA de todo clon y se localiza por `.env` (FPS_DATA_DIR / FPS_DATASET_DIR). Es
#     el caso de siempre y sigue exigiendo ese `.env`, porque sin el no hay nada que cargar.
#   * arbol PUBLICO: la base de casos viaja DENTRO del repositorio (`seed/dataset`), que es lo que permite que un
#     desconocido ejecute un comando y tenga la aplicacion con datos. Ahi pedir un `.env` seria pedirle justo lo que
#     el propio README dice que no hace falta, asi que se usa el dataset QUE TRAE EL CLON.
if [ -f "$ROOT/.env" ]; then
  DATA_DIR="$(abs "$(read_env FPS_DATA_DIR)")"; DATASET_DIR="$(abs "$(read_env FPS_DATASET_DIR)")"
  [ -f "$DATASET_DIR/diets.jsonl" ] || { echo "dataset not found at $DATASET_DIR"; exit 2; }
elif [ -f "$ROOT/seed/dataset/diets.jsonl" ]; then
  DEST_M="$(cygpath -m "$DEST" 2>/dev/null || echo "$DEST")"
  DATA_DIR="$DEST_M/seed/dataset"; DATASET_DIR="$DATA_DIR"
  echo "no .env: this tree carries its own case base, so the clone's own seed/dataset is used"
else
  echo "no .env and no seed/dataset: there is nothing to load (a private tree needs FPS_DATASET_DIR)"; exit 2
fi
EMB_REV="$(grep -E '^EMBEDDING_MODEL_REVISION=' "$ROOT/.env.example" | cut -d= -f2)"

echo "clean-clone verification · branch $BRANCH · $(git -C "$ROOT_W" rev-parse --short HEAD) · dest $DEST · db :$PORT · api :$API_PORT"

# ------------------------------------------------------------------------------------------------------------ 1. clone
rm -rf "$DEST"; mkdir -p "$DEST"
step "clone (committed tree only)" git clone --quiet --branch "$BRANCH" "$ROOT_W" . || exit 1
DEST_W="$(winpath "$DEST")"
echo "      HEAD in clone: $(git -C "$DEST_W" rev-parse --short HEAD); tracked files: $(git -C "$DEST_W" ls-files | wc -l | tr -d ' ')"

# ------------------------------------------------------------------------------------------------------------ 2. configuration
cat > "$DEST/.env" <<EOF
POSTGRES_DB=finalprosports
POSTGRES_USER=finalprosports
POSTGRES_PASSWORD=verify
POSTGRES_PORT=$PORT
DATABASE_URL=postgresql+psycopg://finalprosports:verify@127.0.0.1:$PORT/finalprosports
PROFESSIONAL_ID=prof_001
PROFESSIONAL_BRAND="Final Pro Sports"
PROFESSIONAL_CONTACT=
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_MODEL_REVISION=$EMB_REV
API_PORT=$API_PORT
KEYCLOAK_PORT=$KC_PORT
KEYCLOAK_ISSUER=http://localhost:$KC_PORT/realms/fps
KEYCLOAK_AUDIENCE=fps-backend
KEYCLOAK_REQUIRED_ROLE=entrenador
FPS_DATA_DIR="$DATA_DIR"
FPS_DATASET_DIR="$DATASET_DIR"
EOF
set -a; . "$DEST/.env"; set +a
RESULTS+=("PASS  $(printf '%-28s' 'configuration (.env)') 0s"); echo "PASS  configuration (.env)"

# ------------------------------------------------------------------------------------------------------------ 3. Python environment
step "python venv" "$PY_SYS" -m venv backend/.venv || exit 1
if [ -x "$DEST/backend/.venv/Scripts/python.exe" ]; then VPY="$DEST/backend/.venv/Scripts/python.exe"; LINT="$DEST/backend/.venv/Scripts/lint-imports.exe"
else VPY="$DEST/backend/.venv/bin/python"; LINT="$DEST/backend/.venv/bin/lint-imports"; fi
step "pip install (requirements.lock + backend[dev,eval])" "$VPY" -m pip install --quiet --disable-pip-version-check -r backend/requirements.lock -e "backend[dev,eval]" || exit 1

# ------------------------------------------------------------------------------------------------------------ 4. frontend dependencies
step "npm ci" bash -c 'cd frontend && npm ci --no-audit --no-fund --loglevel=error'

# ------------------------------------------------------------------------------------------------------------ 5. isolated database
IMAGE="$(grep -oE 'image: *[^ ]+' "$DEST/docker-compose.yml" | head -1 | awk '{print $2}')"
docker rm -f "$CONTAINER" >/dev/null 2>&1
step "database container ($IMAGE)" docker run -d --name "$CONTAINER" -p "127.0.0.1:$PORT:5432" -e POSTGRES_DB=finalprosports -e POSTGRES_USER=finalprosports -e POSTGRES_PASSWORD=verify "$IMAGE" || exit 1
# `pg_isready` over the unix socket says YES during initdb, while TCP is still closed and the database is
# the template one: the next step then fails with "vector type not found in the database". Wait for a real
# query OVER TCP, which is how the application connects.
for i in $(seq 1 90); do docker exec "$CONTAINER" psql -h 127.0.0.1 -U finalprosports -d finalprosports -c 'select 1' >/dev/null 2>&1 && break; sleep 1; done
step "database ready (real query over TCP)" docker exec "$CONTAINER" psql -h 127.0.0.1 -U finalprosports -d finalprosports -c 'select 1' || exit 1

# v2: the identity provider, isolated like the database. The realm comes from the CLONE, so this also
# proves that a clean checkout carries realm, role and users with no manual step.
KC_IMAGE="$(grep -oE 'image: *quay.io/keycloak/keycloak[^ ]+' "$DEST/docker-compose.yml" | head -1 | awk '{print $2}')"
docker rm -f "$KC_CONTAINER" >/dev/null 2>&1
step "keycloak container ($KC_IMAGE)" docker run -d --name "$KC_CONTAINER" -p "127.0.0.1:$KC_PORT:8080"   -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin -e KC_HEALTH_ENABLED=true -e KC_HTTP_ENABLED=true   -v "$DEST_W/keycloak/realm-fps.json:/opt/keycloak/data/import/realm-fps.json:ro"   -v "$DEST_W/keycloak/themes:/opt/keycloak/themes:ro"   "$KC_IMAGE" start-dev --import-realm --http-port=8080 || exit 1
# `curl -s -o /dev/null` exits 0 on a 404 as well, so waiting on "did curl work" breaks out before the
# realm is imported. Require a 200. The issuer is minted from the HOST the request used, so ask through
# localhost: that is the name the token will carry and the one KEYCLOAK_ISSUER expects.
for i in $(seq 1 90); do [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$KC_PORT/realms/fps/.well-known/openid-configuration")" = "200" ] && break; sleep 2; done
step "keycloak realm imported (fps)" bash -c "curl -s http://localhost:$KC_PORT/realms/fps/.well-known/openid-configuration | grep -q '\"issuer\":\"http://localhost:$KC_PORT/realms/fps\"'"
step "keycloak refuses the password grant (OAuth 2.1)" bash -c "curl -s -X POST http://localhost:$KC_PORT/realms/fps/protocol/openid-connect/token -d 'grant_type=password&client_id=fps-frontend&username=entrenador&password=entrenador' | grep -q unauthorized_client"

# ------------------------------------------------------------------------------------------------------------ 6. schema and data
step "migrate (alembic upgrade head)" bash -c "cd backend && '$VPY' -m alembic upgrade head"
step "load-check (dry run vs schema.sql)" bash -c "cd backend && '$VPY' ../pipeline/src/pipeline/load_postgres.py --dry-run | grep -q '\"problems\": \[\]'"
step "load (corpus -> postgres)" bash -c "cd backend && '$VPY' ../pipeline/src/pipeline/load_postgres.py --apply --replace"
step "embed (multilingual-e5-base)" bash -c "cd backend && '$VPY' ../pipeline/src/pipeline/embed_corpus.py"

# ------------------------------------------------------------------------------------------------------------ 7. backend quality
step "tests without dependencies" bash -c "fail=0; n=0; for t in backend/tests/architecture/test_*.py backend/tests/domain/test_*.py backend/tests/application/test_*.py backend/tests/evaluation/test_*.py pipeline/tests/test_*.py; do out=\$(cd backend && '$VPY' \"../\$t\" 2>&1) || { echo \"\$out\" | tail -5; fail=1; }; echo \"\$out\" | grep -E '^(FAIL|ERROR)' && fail=1; n=\$((n + \$(echo \"\$out\" | grep -c '^PASS'))); done; echo \"PASS count: \$n\"; [ \$fail = 0 ]"
step "import-linter contracts" bash -c "cd backend && '$LINT'"
step "pytest infrastructure (db)" bash -c "cd backend && '$VPY' -m pytest tests/infrastructure -q -p no:cacheprovider"
step "golden model diets" bash -c "cd backend && '$VPY' -m pytest tests/golden -q -p no:cacheprovider"
# LA PUERTA DE DATOS PERSONALES, y cual aplica depende del arbol: con corpus y diccionario, la auditoria por
# NOMBRES y su criterio 0; sin diccionario --el arbol publico no lo lleva porque no lleva corpus-- esa
# auditoria no puede decir nada, y la garantia alli es la que busca FORMAS de dato personal. Antes este paso
# fallaba en el publico por pedirle a la auditoria una cifra que no puede dar.
if [ -d "$DATASET_DIR/_private" ]; then
  step "audit (PII criterion 0, name dictionary)" bash -c "cd backend && '$VPY' ../pipeline/src/data_tools/audit_tree.py | grep -E '\"total_hits\"' | grep -vq '\"total_hits\": [1-9]'"
else
  step "public-tree gate (no dictionary: personal data by SHAPE)" bash -c "cd backend && FPS_PUBLIC_TREE=1 '$VPY' ./tests/architecture/test_public_tree_has_no_personal_data.py"
fi

# LA IDENTIDAD DEL PROFESIONAL, que es un dato distinto del de sus clientes y por eso necesita su propia puerta.
# El 2026-09-09 el repositorio publico llevaba su nombre y su marca en texto plano DENTRO del detector de datos
# personales (`pii_common`, `sanitize`, `test_dataset`): un detector con el dato dentro lo publica cada vez que se
# publica el codigo, y ninguna de las otras puertas lo veia (la de nombres compara con los CLIENTES del corpus; la
# de formas busca filas por persona). Los patrones viven ahora en la custodia y este paso se la pasa: sin ella la
# comprobacion lo diria y no fingiria, pero aqui la hay, asi que tiene dientes.
# Y como el paso anterior, cual aplica depende del arbol -- con una rama mas, porque aqui hay TRES situaciones y
# solo una es un descuido. Los patrones viven en `_private/`, que por diseno no sale del arbol de datos: en el
# arbol PUBLICO el fichero no puede existir jamas, asi que fallar alli no denuncia nada, solo hace que la
# verificacion que el README documenta termine en BROKEN por un paso imposible. Se distingue por
# `seed/dataset/SYNTHETIC.json`, que el montador deja a la vista precisamente para decir «esta base es inventada».
# En el arbol del titular no cambia nada: sin custodia sigue siendo FAIL, porque alli si es un olvido.
CUSTODIA="${FPS_PII_PATTERNS:-$DATASET_DIR/_private/pii_patterns.json}"
if [ -f "$CUSTODIA" ]; then
  step "professional identity is nowhere in the tree (custody patterns)" bash -c "cd backend && FPS_PII_PATTERNS='$CUSTODIA' '$VPY' ./tests/architecture/test_no_professional_identity_in_the_tree.py"
elif [ -f "$DATASET_DIR/SYNTHETIC.json" ]; then
  step "professional identity: NO APLICA en el arbol publico (los patrones son custodia privada)" bash -c "echo 'arbol publico (seed/dataset/SYNTHETIC.json): los patrones viven en _private/ y no viajan; la garantia aqui es la puerta por FORMAS, que ya paso'; exit 0"
else
  step "professional identity: NO CUSTODY PATTERNS (cannot check)" bash -c "echo 'sin $CUSTODIA no hay patrones que buscar'; exit 1"
fi

# ------------------------------------------------------------------------------------------------------------ 8. application: demo + API
step "demo seed (three fictitious clients, by name)" bash -c "cd backend && '$VPY' -m finalprosports.infrastructure.adapter.inbound.cli.seed_demo --reset"
(cd "$DEST/backend" && "$VPY" -m uvicorn finalprosports.main:app --host 127.0.0.1 --port "$API_PORT" > "$DEST/api.log" 2>&1) &
API_PID=$!
for i in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$API_PORT/docs" && break; sleep 1; done
step "api /health (the only open route)" bash -c "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$API_PORT/health | grep -q 200"
step "api /docs" bash -c "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$API_PORT/docs | grep -q 200"
step "api WITHOUT a token is 401" bash -c "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$API_PORT/api/v1/clients | grep -q 401"

# Two real tokens, through the full Authorization Code + PKCE flow (there is no password grant to fall
# back on). They come back on STDOUT, one per line: writing them to a file would need a Windows path here
# and a POSIX one in bash, and that mismatch is exactly what broke the first run.
TOKENS="$(cd "$DEST/backend" && KEYCLOAK_BASE_URL="http://localhost:$KC_PORT" "$VPY" -c "
import sys; sys.path.insert(0, '.')
from tests.security.pkce_login import TRAINER, NO_ROLE, access_token
print(access_token(*TRAINER)); print(access_token(*NO_ROLE))
" 2>"$DEST/token.err")"
TOKEN="$(printf '%s
' "$TOKENS" | sed -n 1p)"
NOROLE="$(printf '%s
' "$TOKENS" | sed -n 2p)"
step "token via Authorization Code + PKCE" bash -c "[ -n '$TOKEN' ] && [ -n '$NOROLE' ] || { cat '$DEST/token.err'; false; }"

step "api with a valid token WITHOUT the role is 403" bash -c "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer $NOROLE' http://127.0.0.1:$API_PORT/api/v1/clients | grep -q 403"
# La cartera se compara con el TAMAÑO DE LA LISTA DEL SEMBRADOR, no con un 3 escrito aquí. Antes contaba los nombres
# que casan «Ficticio/a Demo» y exigía tres: cuando la lista pasó de 3 a 16 clientes el paso siguió en verde por
# casualidad —solo tres de los dieciséis llevan esas dos palabras— mientras la cartera tenía otra cosa dentro. Y de
# paso se comprueba que TODOS los nombres dicen que son de demostración, que es la propiedad que de verdad importa.
DEMO_N="$("$VPY" -c "import sys; sys.path.insert(0, 'backend/src'); from finalprosports.infrastructure.adapter.inbound.cli.seed_demo import DEMO_CLIENTS; print(len(DEMO_CLIENTS))" 2>/dev/null || echo 0)"
step "api GET /clients ($DEMO_N demo clients, all of them by name)" bash -c "curl -s -H 'Authorization: Bearer $TOKEN' http://127.0.0.1:$API_PORT/api/v1/clients > clients.json; n=\$(grep -o '\"id\":\"' clients.json | wc -l); d=\$(grep -o '\"full_name\":\"[^\"]*Demo\"' clients.json | wc -l); [ \"\$n\" = \"$DEMO_N\" ] && [ \"\$d\" = \"$DEMO_N\" ]"
step "api POST /diets/propose (real proposal for the first demo client, by its UUID)" bash -c "id=\$(curl -s -H 'Authorization: Bearer $TOKEN' http://127.0.0.1:$API_PORT/api/v1/clients | grep -o '\"id\":\"[0-9a-f-]*\"' | head -1 | cut -d'\"' -f4); curl -s -o propose.json -w '%{http_code}' -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d \"{\\\"client_id\\\":\\\"\$id\\\",\\\"goal\\\":\\\"definicion_grasa\\\"}\" http://127.0.0.1:$API_PORT/api/v1/diets/propose | grep -q 200 && grep -q '\"meals\"' propose.json"
# FPS_REQUIRE_LIVE=1: the fixtures skip when Keycloak or the API are unreachable, and a skipped suite
# exits 0 — the verification would report PASS for tests that never ran. Here a missing service is a FAILURE.
step "security suite (the eight rejection cases)" bash -c "cd backend && FPS_REQUIRE_LIVE=1 FPS_API_URL=http://127.0.0.1:$API_PORT KEYCLOAK_BASE_URL=http://localhost:$KC_PORT '$VPY' -m pytest tests/security -q -m security -p no:cacheprovider"
rm -f "$DEST/token.err"
stop_api

# ------------------------------------------------------------------------------------------------------------ 9. frontend
step "web-lint (eslint + stylelint + prettier)" bash -c 'cd frontend && npm run -s lint'
step "web-build production" bash -c 'cd frontend && npx ng build 2>&1 | grep -q "Application bundle generation complete"'
step "web-build development" bash -c 'cd frontend && npx ng build --configuration development 2>&1 | grep -q "Application bundle generation complete"'
step "web-test (karma, 49 specs)" bash -c 'cd frontend && npx ng test --watch=false 2>&1 | tr "\r" "\n" | grep -q "TOTAL: [0-9]* SUCCESS"'

# ------------------------------------------------------------------------------------------------------------ summary
echo; echo "================ clean-clone verification · $(( $(date +%s) - T0 ))s · $DEST"
printf '%s\n' "${RESULTS[@]}"
if [ $FAILED -eq 0 ]; then echo "RESULT: the committed tree bootstraps from a clean clone"; else echo "RESULT: BROKEN — at least one step failed from a clean clone"; fi
exit $FAILED
