"""Sonda local de Docker; no consulta redes externas."""

from __future__ import annotations

import json
import logging
from http.client import HTTPConnection

from carrerags_embeddings.constants import DIMENSIONS, SPACE

logger = logging.getLogger(__name__)


def check() -> tuple[bool, str, None]:
    connection: HTTPConnection | None = None
    try:
        connection = HTTPConnection("127.0.0.1", 8081, timeout=3)
        connection.request("GET", "/health")
        response = connection.getresponse()
        body = json.loads(response.read())
        if response.status != 200 or body.get("resultado") is not True or body.get("salida", {}).get("space") != SPACE or body["salida"].get("dimensions") != DIMENSIONS:
            raise ValueError("Servicio sin disponibilidad o incompatible")
        return True, "ok", None
    except Exception as e:
        logger.error("Error en check: %s", e)
        return False, "Falló la sonda local", None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception as e:
                logger.error("Error en check al cerrar conexión: %s", e)
                return False, "No se pudo cerrar la conexión de la sonda", None


if __name__ == "__main__":
    success, _, _ = check()
    raise SystemExit(0 if success else 1)
