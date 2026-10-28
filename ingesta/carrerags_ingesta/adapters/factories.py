"""Factorías iniciales; los proveedores adicionales pueden vivir en otros paquetes."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from ..config import Settings
from ..contracts import VectorStore
from .http import HttpTransport

logger = logging.getLogger(__name__)


def qdrant(settings: Settings) -> tuple[bool, str, VectorStore | None]:
    try:
        from .qdrant import QdrantStore

        parsed = urlsplit(settings.vectorial)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("VECTORIAL debe ser una dirección HTTP con host y puerto")
        _ = parsed.port
        return True, "ok", QdrantStore(settings.vectorial, settings.namespace, settings.vector_key, HttpTransport(settings.timeout))
    except Exception as e:
        logger.error("Error en factories.qdrant: %s", e)
        return False, "Revisar VECTORIAL y la configuración de Qdrant", None


def memory(settings: Settings) -> tuple[bool, str, VectorStore | None]:
    try:
        from .memory import MemoryStore

        return True, "ok", MemoryStore()
    except Exception as e:
        logger.error("Error en factories.memory: %s", e)
        return False, "No se pudo crear el motor de memoria", None


