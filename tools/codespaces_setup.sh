#!/usr/bin/env bash
# Prepara un Codespace para servir la aplicación a alguien de fuera.
#
# El problema que resuelve: la aplicación está clavada a `localhost` en tres sitios, y en un Codespace el navegador
# del cliente entra por `https://<codespace>-4200.app.github.dev`.
#
#   1. `keycloak/realm-fps.json` declara `redirectUris` y `webOrigins` de `fps-frontend` como http://localhost:4200.
#      Con cualquier otro origen Keycloak corta el login con «Invalid parameter: redirect_uri».
#   2. `frontend/src/environments/environment.prod.ts` lleva `keycloakUrl: http://localhost:8080`, y esa URL la abre
#      el NAVEGADOR, no el contenedor.
#   3. El backend valida que el `iss` del token sea `KEYCLOAK_ISSUER`, que se acuña con el host del navegador.
#
# Nada de esto se corrige tocando los ficheros del repositorio: este script escribe un `.env` y un realm PARCHEADO
# en `.codespaces/` (ignorado por git), y `docker-compose.codespaces.yml` los usa. `docker compose up` en local
# sigue exactamente igual, que es un requisito de la entrega.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${CODESPACE_NAME:-}" ]]; then
  echo "Este script es SOLO para Codespaces: fuera de ahí sobrescribiría tu .env." >&2
  echo "CODESPACE_NAME no está definida. No se ha tocado nada." >&2
  exit 1
fi

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
WEB_URL="https://${CODESPACE_NAME}-4200.${DOMAIN}"
KC_URL="https://${CODESPACE_NAME}-8080.${DOMAIN}"

mkdir -p .codespaces

# Si el corpus no viaja en el repositorio, el bind mount del compose apuntaría a una ruta inexistente. El arranque
# YA contempla no tener base de casos (avisa y termina bien: la aplicación se navega y la propuesta da 422), pero
# necesita que el directorio exista para poder montarlo.
mkdir -p seed/dataset
if [[ ! -f seed/dataset/diets.jsonl ]]; then
  echo "  AVISO: no hay corpus en seed/dataset (falta diets.jsonl)."
  echo "         La aplicación arrancará y se podrá navegar, pero pedir una propuesta dará 422."
fi

# En un Codespace es `python3`; el respaldo existe para poder ejecutar este script en un Windows y comprobar el
# parcheo del realm sin levantar un Codespace entero.
PY_BIN="$(command -v python3 || command -v python || true)"
if [[ -z "$PY_BIN" ]]; then
  echo "No hay python disponible; no se puede parchear el realm." >&2
  exit 1
fi

# --- el realm, con el origen del Codespace AÑADIDO (no sustituido): así sigue valiendo localhost dentro del propio
#     Codespace, que es como se depura desde el navegador integrado.
"$PY_BIN" - "$WEB_URL" <<'PY'
import json, sys, pathlib
web = sys.argv[1]
realm = json.loads(pathlib.Path("keycloak/realm-fps.json").read_text(encoding="utf-8"))
for c in realm.get("clients", []):
    if c.get("clientId") != "fps-frontend":
        continue
    c["redirectUris"] = sorted(set(c.get("redirectUris", []) + [f"{web}/*"]))
    c["webOrigins"] = sorted(set(c.get("webOrigins", []) + [web]))
    c["rootUrl"] = web
    c["baseUrl"] = f"{web}/"
out = pathlib.Path(".codespaces/realm-fps.json")
out.write_text(json.dumps(realm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"  realm parcheado -> {out} (redirectUris += {web}/*)")
PY

# --- el `.env` que el compose lee. `iss` con el host del navegador; el JWKS se sigue pidiendo por la red interna.
cat > .env <<ENV
# Generado por tools/codespaces_setup.sh — NO editar a mano, se regenera en cada creación del Codespace.
KEYCLOAK_ISSUER=${KC_URL}/realms/fps
CODESPACE_WEB_URL=${WEB_URL}
CODESPACE_KEYCLOAK_URL=${KC_URL}
# Contraseñas: siguen siendo las de desarrollo. Los puertos de Postgres y de la API NO se publican en Codespaces
# (ver docker-compose.codespaces.yml), así que no dan a la red; aun así no uses esto como producción.
ENV

printf '  .env escrito\n    aplicación : %s\n    keycloak   : %s\n' "$WEB_URL" "$KC_URL"
echo
echo "  Siguiente paso: docker compose -f docker-compose.yml -f docker-compose.codespaces.yml up -d --build"
