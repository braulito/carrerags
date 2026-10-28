"""Transporte HTTP JSON compartido; preserva el estado HTTP sin exponer cuerpos de error."""

from __future__ import annotations

import json
import logging
from http.client import HTTPConnection, HTTPSConnection
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


@dataclass
class HttpTransport:
    timeout: float = 60.0

    def request(self: HttpTransport, method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> tuple[bool, str, dict[str, Any]]:
        connection: HTTPConnection | None = None
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Dirección HTTP inválida")
            encoded = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            connection_type = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
            connection = connection_type(parsed.hostname, parsed.port, timeout=self.timeout)
            target = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
            connection.request(method, target, body=encoded, headers={"Content-Type": "application/json", **headers})
            response = connection.getresponse()
            # No seguir redirecciones ni devolver cuerpos de error que puedan contener secretos.
            if not 200 <= response.status < 300:
                logger.error("Error en HttpTransport.request: HTTP %s", response.status)
                return False, "La API respondió con HTTP " + str(response.status), {"http_status": response.status, "body": {}}
            content = json.loads(response.read())
            if not isinstance(content, dict):
                raise ValueError("Respuesta JSON inesperada")
            return True, "ok", {"http_status": response.status, "body": content}
        except Exception as e:
            logger.error("Error en HttpTransport.request: %s", e)
            return False, "No se pudo completar la llamada a la API", {"http_status": None, "body": {}}
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception as e:
                    logger.error("Error en HttpTransport.request al cerrar la conexión: %s", e)
                    return False, "No se pudo cerrar la conexión HTTP", {"http_status": None, "body": {}}
