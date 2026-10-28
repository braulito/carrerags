#!/usr/bin/env bash
# Instalación en Mac Apple Silicon. Compatible con Bash 3.2 de macOS.
set -Eeuo pipefail

EMBED_INSTALL_MODE=auto
if [[ $# -gt 1 ]]; then
    printf 'Uso: bash install.sh [--rebuild|--offline|--help]\n' >&2
    exit 2
fi
case "${1:-}" in
    '') ;;
    --rebuild) EMBED_INSTALL_MODE=rebuild ;;
    --offline) EMBED_INSTALL_MODE=offline ;;
    --help|-h)
        cat <<'HELP'
Uso: bash install.sh [--rebuild|--offline]

Sin opciones: reutiliza las imágenes locales y prepara las que falten.
--rebuild: reconstruye la imagen del modelo con el código de este repositorio.
--offline: exige las dos imágenes locales; no construye ni descarga imágenes.

Requiere macOS Apple Silicon y Docker Desktop instalado e iniciado.
No carga archivos .env. Publica el servicio en el puerto 8081.
HELP
        exit 0
        ;;
    *)
        printf 'Opción desconocida. Usar bash install.sh --help\n' >&2
        exit 2
        ;;
esac

trap 'EMBED_INSTALL_STATUS=$?; printf "ERROR: instalación interrumpida en la línea %s (código %s).\n" "$LINENO" "$EMBED_INSTALL_STATUS" >&2; printf "Para revisar el servicio: COMPOSE_DISABLE_ENV_FILE=1 docker compose -f compose.yaml logs --tail 80 embeddings gateway\n" >&2; exit "$EMBED_INSTALL_STATUS"' ERR

EMBED_INSTALL_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd -P)"
cd -- "$EMBED_INSTALL_DIR"

# Impedir la carga automática de archivos de configuración por Compose.
export COMPOSE_DISABLE_ENV_FILE=1
unset COMPOSE_ENV_FILES

for EMBED_INSTALL_REQUIRED in docker curl uname; do
    if ! command -v "$EMBED_INSTALL_REQUIRED" >/dev/null 2>&1; then
        printf 'ERROR: falta %s. Instalar Docker Desktop para Apple Silicon y las herramientas indicadas.\n' "$EMBED_INSTALL_REQUIRED" >&2
        exit 1
    fi
done
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    printf 'ERROR: ejecutar desde una terminal nativa de macOS Apple Silicon (arm64).\n' >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    printf 'ERROR: Docker no responde. Abrir Docker Desktop, esperar que inicie y repetir el comando.\n' >&2
    exit 1
fi
EMBED_INSTALL_ENGINE="$(docker info --format '{{.OSType}}/{{.Architecture}}')"
case "$EMBED_INSTALL_ENGINE" in
    linux/arm64|linux/aarch64) ;;
    *)
        printf 'ERROR: Docker debe usar un motor Linux ARM64 nativo; revisar el contexto de Docker.\n' >&2
        exit 1
        ;;
esac
if ! docker compose version >/dev/null 2>&1; then
    printf 'ERROR: se necesita Docker Compose v2 o posterior, incluido en Docker Desktop.\n' >&2
    exit 1
fi
for EMBED_INSTALL_FILE in compose.yaml nginx.conf Dockerfile; do
    if [[ ! -f "$EMBED_INSTALL_DIR/$EMBED_INSTALL_FILE" ]]; then
        printf 'ERROR: falta %s; actualizar la carpeta embedding completa desde el repositorio.\n' "$EMBED_INSTALL_FILE" >&2
        exit 1
    fi
done

EMBED_INSTALL_COMPOSE=(docker compose -p carrerags-embeddings -f "$EMBED_INSTALL_DIR/compose.yaml")
EMBED_INSTALL_MODEL_IMAGE=carrerags-embeddings:arm64
EMBED_INSTALL_GATEWAY_IMAGE=nginx:1.30.6-alpine

printf 'Validando Docker Compose...\n'
"${EMBED_INSTALL_COMPOSE[@]}" config --quiet

EMBED_INSTALL_MODEL_ARCH="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$EMBED_INSTALL_MODEL_IMAGE" 2>/dev/null || true)"
EMBED_INSTALL_GATEWAY_ARCH="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$EMBED_INSTALL_GATEWAY_IMAGE" 2>/dev/null || true)"
if [[ "$EMBED_INSTALL_MODE" == offline ]]; then
    if [[ "$EMBED_INSTALL_MODEL_ARCH" != linux/arm64 || "$EMBED_INSTALL_GATEWAY_ARCH" != linux/arm64 ]]; then
        printf 'ERROR: --offline requiere las imágenes ARM64 locales del modelo y de NGINX. Ejecutar primero la instalación con Internet o importar ambas imágenes.\n' >&2
        exit 1
    fi
else
    if [[ "$EMBED_INSTALL_MODE" == rebuild || "$EMBED_INSTALL_MODEL_ARCH" != linux/arm64 ]]; then
        printf 'Construyendo el modelo ARM64. La primera construcción descarga dependencias y pesos.\n'
        "${EMBED_INSTALL_COMPOSE[@]}" build embeddings
    else
        printf 'Reutilizando la imagen local del modelo.\n'
    fi
    if [[ "$EMBED_INSTALL_GATEWAY_ARCH" != linux/arm64 ]]; then
        printf 'Descargando la imagen ARM64 de NGINX...\n'
        "${EMBED_INSTALL_COMPOSE[@]}" pull gateway
    fi
fi

printf 'Comprobando la configuración de NGINX...\n'
"${EMBED_INSTALL_COMPOSE[@]}" run --rm --no-deps --pull never --entrypoint nginx gateway -t -c /etc/nginx/nginx.conf

printf 'Levantando el modelo y la entrada HTTP; esperando los healthchecks...\n'
"${EMBED_INSTALL_COMPOSE[@]}" up -d --no-build --pull never --wait --wait-timeout 240
"${EMBED_INSTALL_COMPOSE[@]}" ps

printf 'Comprobando el puerto publicado en el Mac...\n'
"${EMBED_INSTALL_COMPOSE[@]}" port gateway 8081
EMBED_INSTALL_HEALTH="$(curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8081/health)"
if ! printf '%s' "$EMBED_INSTALL_HEALTH" | grep -Eq '"resultado"[[:space:]]*:[[:space:]]*true' || \
   ! printf '%s' "$EMBED_INSTALL_HEALTH" | grep -Eq '"dimensions"[[:space:]]*:[[:space:]]*384([[:space:]]*[,}])'; then
    printf 'ERROR: el puerto responde pero el servicio no confirma embeddings de 384 dimensiones.\n' >&2
    exit 1
fi

printf '\nInstalación completada. El modelo está cargado y el puerto 8081 responde.\n'
printf 'Desde Windows: curl.exe --fail-with-body http://macmini:8081/health\n'
printf 'Después ejecutar python run_e.py desde consultador.\n'
