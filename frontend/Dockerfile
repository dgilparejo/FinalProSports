# Frontend en dos etapas: se COMPILA con node y se SIRVE con nginx.
#
# La imagen final no lleva node, ni node_modules, ni el código fuente: lleva el bundle y un nginx. Son ~50 MB en vez
# de ~1,5 GB, y sobre todo no hay un intérprete ni un gestor de paquetes en el contenedor que da la cara al navegador.
#
# `npm ci` y no `npm install`: instala EXACTAMENTE lo que dice package-lock.json y falla si el lock no cuadra con el
# package.json. En una imagen que se reconstruye en otra máquina, `install` podría resolver otras versiones y servir un
# frontend distinto del que se probó.
#
# `NODE_OPTIONS=--max-old-space-size=4096` por la misma razón que en el Makefile: una compilación de Angular sin techo
# de heap se comió 16 GB de RAM en este proyecto (incidente del 2026-08-26). Dentro de un contenedor el daño quedaría
# acotado, pero el techo es gratis y hace que el build falle rápido en vez de tumbar la máquina.
#
# La configuración `production` hace el reemplazo de fichero a `environment.prod.ts`, donde `apiBaseUrl` es **/api/v1**
# — RELATIVO. Ese es el punto: en el contenedor el mismo nginx sirve el SPA y hace de proxy hacia `api:8000`, así que
# navegador y API comparten origen. No hay CORS que negociar y el token no cruza orígenes. `keycloakUrl` sí es
# absoluto (`http://localhost:8080`) porque de esa URL no hace una petición el contenedor: navega el NAVEGADOR.
FROM node:22-alpine AS build
WORKDIR /app
ENV NODE_OPTIONS=--max-old-space-size=4096
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vacío por defecto: el build local no cambia. Se pasa solo desde docker-compose.codespaces.yml, donde el navegador
# del cliente llega por un dominio de GitHub y `http://localhost:8080` no existe para él. Se sustituye ANTES de
# compilar porque `keycloakUrl` entra en el bundle, y se imprime para que quede constancia de con qué se compiló.
ARG KEYCLOAK_PUBLIC_URL=""
RUN if [ -n "$KEYCLOAK_PUBLIC_URL" ]; then       sed -i "s|http://localhost:8080|$KEYCLOAK_PUBLIC_URL|g" src/environments/environment.prod.ts &&       echo "keycloakUrl horneado:" && grep keycloakUrl src/environments/environment.prod.ts;     fi
RUN npx ng build --configuration production

FROM nginx:1.29-alpine
# El builder `application` de Angular 21 escribe el bundle del navegador en dist/<proyecto>/browser.
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=10 CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
