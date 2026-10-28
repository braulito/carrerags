"""Verificación del puerto publicado; ejecutar en el Mac con Compose levantado."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def docker_command(arguments: list[str]) -> tuple[bool, str, str]:
    try:
        # Desactivar la búsqueda automática de .env de Compose. No imprimir el
        # entorno ni usar docker inspect completo: solo se solicitan puertos.
        result = subprocess.run(["docker", *arguments], cwd=Path(__file__).resolve().parents[1],
                                env={**os.environ, "COMPOSE_DISABLE_ENV_FILE": "1"},
                                capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            raise RuntimeError("Docker no pudo completar la comprobación de puertos")
        return True, "ok", result.stdout.strip()
    except Exception as e:
        logger.error("Error en docker_command: %s", e)
        return False, "No se pudo consultar Docker; comprobar que esté iniciado", ""


def verify() -> tuple[bool, str, dict[str, Any]]:
    connection: HTTPConnection | None = None
    try:
        ok, message, identifier = docker_command(["compose", "-f", "compose.yaml", "ps", "-q", "gateway"])
        if not ok:
            return False, message, {}
        if not identifier or len(identifier.splitlines()) != 1:
            raise ValueError("El servicio gateway no está iniciado")
        ok, message, raw_ports = docker_command(["inspect", "--format", "{{json .NetworkSettings.Ports}}", identifier])
        if not ok:
            return False, message, {}
        bindings = (json.loads(raw_ports) or {}).get("8081/tcp") or []
        if not any(binding.get("HostPort") == "8081" for binding in bindings):
            raise ValueError("El puerto 8081 está expuesto dentro del contenedor pero no publicado en el Mac")
        connection = HTTPConnection("127.0.0.1", 8081, timeout=10)
        connection.request("GET", "/health")
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("El puerto responde pero /health no devuelve HTTP 200")
        body = json.loads(response.read())
        if body.get("resultado") is not True or body.get("salida", {}).get("dimensions") != 384:
            raise ValueError("El endpoint publicado no devuelve un servicio de embeddings listo")
        return True, "ok", {"published_port": 8081, "health": True}
    except Exception as e:
        logger.error("Error en verify: %s", e)
        return False, "Falló la verificación desde el Mac: " + str(e), {}
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception as e:
                logger.error("Error en verify al cerrar la conexión: %s", e)
                return False, "No se pudo cerrar la conexión de verificación", {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success, message, data = verify()
    print(json.dumps({"resultado": success, "mensaje": message, "salida": data}, ensure_ascii=False))
    raise SystemExit(0 if success else 1)
