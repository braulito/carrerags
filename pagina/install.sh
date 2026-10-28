#!/usr/bin/env bash
# Despliegue de CarreRAGs página. Requiere Bash 3.2 o posterior.
set -Eeuo pipefail

trap 'CARRERAGS_PAGINA_STATUS=$?; printf "ERROR: despliegue interrumpido en la línea %s (código %s).\n" "$LINENO" "$CARRERAGS_PAGINA_STATUS" >&2; printf "Para revisar: docker logs --tail 80 carrerags-pagina\n" >&2; exit "$CARRERAGS_PAGINA_STATUS"' ERR

CARRERAGS_PAGINA_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd -P)"
cd -- "$CARRERAGS_PAGINA_DIR"

# Deshabilitar la interpolación implícita del .env. Compose conserva el env_file
# explícito del servicio para inyectar URL_API al iniciar el contenedor.
export COMPOSE_DISABLE_ENV_FILE=1
unset COMPOSE_ENV_FILES

for CARRERAGS_PAGINA_REQUIRED in docker curl grep; do
    if ! command -v "$CARRERAGS_PAGINA_REQUIRED" >/dev/null 2>&1; then
        printf 'ERROR: falta %s. Instalar las herramientas requeridas y repetir.\n' "$CARRERAGS_PAGINA_REQUIRED" >&2
        exit 1
    fi
done
if ! docker info >/dev/null 2>&1; then
    printf 'ERROR: Docker no responde. Iniciar Docker y repetir.\n' >&2
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
for CARRERAGS_PAGINA_FILE in Dockerfile compose.yaml requirements.txt requirements-docker.txt app.py wsgi.py; do
    if [[ ! -f "$CARRERAGS_PAGINA_DIR/$CARRERAGS_PAGINA_FILE" ]]; then
        printf 'ERROR: falta %s; copiar o actualizar la carpeta pagina completa.\n' "$CARRERAGS_PAGINA_FILE" >&2
        exit 1
    fi
done
for CARRERAGS_PAGINA_FOLDER in templates static; do
    if [[ ! -d "$CARRERAGS_PAGINA_DIR/$CARRERAGS_PAGINA_FOLDER" ]]; then
        printf 'ERROR: falta la carpeta %s.\n' "$CARRERAGS_PAGINA_FOLDER" >&2
        exit 1
    fi
done

CARRERAGS_PAGINA_COMPOSE=(docker compose -f "$CARRERAGS_PAGINA_DIR/compose.yaml")

printf 'Validando Docker Compose...\n'
"${CARRERAGS_PAGINA_COMPOSE[@]}" config --quiet

printf 'Construyendo carrerags-pagina...\n'
"${CARRERAGS_PAGINA_COMPOSE[@]}" build pagina

printf 'Iniciando carrerags-pagina y esperando su healthcheck...\n'
"${CARRERAGS_PAGINA_COMPOSE[@]}" up -d --no-build --pull never --force-recreate --wait --wait-timeout 120 pagina
"${CARRERAGS_PAGINA_COMPOSE[@]}" ps

CARRERAGS_PAGINA_ID="$("${CARRERAGS_PAGINA_COMPOSE[@]}" ps -q pagina)"
if [[ -z "$CARRERAGS_PAGINA_ID" ]] || [[ "$(docker inspect --format '{{.Name}}' "$CARRERAGS_PAGINA_ID")" != /carrerags-pagina ]]; then
    printf 'ERROR: el contenedor desplegado debe llamarse carrerags-pagina.\n' >&2
    exit 1
fi

CARRERAGS_PAGINA_BIND="$("${CARRERAGS_PAGINA_COMPOSE[@]}" port pagina 8080)"
# Si Compose informa IPv4 e IPv6, usar el primer mapeo; conservar el puerto público.
CARRERAGS_PAGINA_BIND="${CARRERAGS_PAGINA_BIND%%$'\n'*}"
CARRERAGS_PAGINA_PORT="${CARRERAGS_PAGINA_BIND##*:}"
if [[ ! "$CARRERAGS_PAGINA_PORT" =~ ^[0-9]+$ ]]; then
    printf 'ERROR: no se pudo determinar el puerto público de la página.\n' >&2
    exit 1
fi

printf 'Comprobando el puerto %s del host...\n' "$CARRERAGS_PAGINA_PORT"
CARRERAGS_PAGINA_HEALTH="$(curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:$CARRERAGS_PAGINA_PORT/health")"
if ! printf '%s' "$CARRERAGS_PAGINA_HEALTH" | grep -Eq '"resultado"[[:space:]]*:[[:space:]]*true' \
    || ! printf '%s' "$CARRERAGS_PAGINA_HEALTH" | grep -Eq '"nombre"[[:space:]]*:[[:space:]]*"carrerags-pagina"'; then
    printf 'ERROR: el puerto publicado no confirmó el estado de carrerags-pagina.\n' >&2
    exit 1
fi

printf '\nDespliegue completado. Contenedor: carrerags-pagina.\n'
printf 'Página: http://127.0.0.1:%s/\n' "$CARRERAGS_PAGINA_PORT"
printf 'Estado: http://127.0.0.1:%s/health\n' "$CARRERAGS_PAGINA_PORT"
printf 'Logs: docker logs -f carrerags-pagina\n'
