#!/usr/bin/env bash
# Despliegue de la API, basado en embedding/install.sh. Bash 3.2 o posterior.
set -Eeuo pipefail

trap 'CARRERAGS_INSTALL_STATUS=$?; printf "ERROR: despliegue interrumpido en la línea %s (código %s).\n" "$LINENO" "$CARRERAGS_INSTALL_STATUS" >&2; printf "Para revisar: docker logs --tail 80 carrerags-api\n" >&2; exit "$CARRERAGS_INSTALL_STATUS"' ERR

CARRERAGS_INSTALL_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd -P)"
cd -- "$CARRERAGS_INSTALL_DIR"

# Compose no interpreta el .env: el Dockerfile lo incorpora en /app/.env.
export COMPOSE_DISABLE_ENV_FILE=1
unset COMPOSE_ENV_FILES

for CARRERAGS_INSTALL_REQUIRED in docker curl grep id; do
    if ! command -v "$CARRERAGS_INSTALL_REQUIRED" >/dev/null 2>&1; then
        printf 'ERROR: falta %s. Instalar las herramientas requeridas y repetir.\n' "$CARRERAGS_INSTALL_REQUIRED" >&2
        exit 1
    fi
done
if ! docker info >/dev/null 2>&1; then
    printf 'ERROR: Docker no responde. Iniciar Docker y repetir el comando.\n' >&2
    exit 1
fi
if [[ "$(docker info --format '{{.OSType}}')" != linux ]]; then
    printf 'ERROR: se necesita un motor Docker con contenedores Linux.\n' >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    printf 'ERROR: se necesita Docker Compose v2 o posterior.\n' >&2
    exit 1
fi
for CARRERAGS_INSTALL_FILE in Dockerfile compose.yaml requirements.txt main.py log_config.json healthcheck.py; do
    if [[ ! -f "$CARRERAGS_INSTALL_DIR/$CARRERAGS_INSTALL_FILE" ]]; then
        printf 'ERROR: falta %s; copiar o actualizar la carpeta llm completa.\n' "$CARRERAGS_INSTALL_FILE" >&2
        exit 1
    fi
done
# Usar los permisos del operador para escribir los JSON en el bind mount.
export CARRERAGS_API_UID="$(id -u)"
export CARRERAGS_API_GID="$(id -g)"
if [[ -d "$CARRERAGS_INSTALL_DIR/JSON" ]]; then
    export CARRERAGS_API_JSON_DIR="$CARRERAGS_INSTALL_DIR/JSON"
else
    export CARRERAGS_API_JSON_DIR="$CARRERAGS_INSTALL_DIR/json"
fi
mkdir -p -- "$CARRERAGS_API_JSON_DIR"

CARRERAGS_INSTALL_COMPOSE=(docker compose -p carrerags-api -f "$CARRERAGS_INSTALL_DIR/compose.yaml")

printf 'Validando Docker Compose...\n'
"${CARRERAGS_INSTALL_COMPOSE[@]}" config --quiet

printf 'Construyendo carrerags-api...\n'
"${CARRERAGS_INSTALL_COMPOSE[@]}" build api

printf 'Iniciando carrerags-api y esperando su healthcheck...\n'
"${CARRERAGS_INSTALL_COMPOSE[@]}" up -d --no-build --pull never --force-recreate --wait --wait-timeout 120
"${CARRERAGS_INSTALL_COMPOSE[@]}" ps

printf 'Comprobando el puerto 8021 del host...\n'
CARRERAGS_INSTALL_HEALTH="$(curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8021/)"
if ! printf '%s' "$CARRERAGS_INSTALL_HEALTH" | grep -Eq '"resultado"[[:space:]]*:[[:space:]]*true'; then
    printf 'ERROR: el puerto 8021 no confirmó el estado de la API.\n' >&2
    exit 1
fi

printf '\nDespliegue completado. Contenedor: carrerags-api.\n'
printf 'API: http://127.0.0.1:8021/\n'
printf 'Documentación: http://127.0.0.1:8021/docs\n'
printf 'Respuestas JSON: %s\n' "$CARRERAGS_API_JSON_DIR"
printf 'Logs: docker logs -f carrerags-api\n'
