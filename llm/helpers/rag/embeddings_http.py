"""Embeddings HTTP sin dependencias ML; verifica identidad, orden y normalización."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .config import DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_REVISION, Settings
from .http import HttpTransport

logger = logging.getLogger(__name__)
DIMENSIONS = 384
SPACE = f"sentence-transformers:{DEFAULT_EMBEDDING_MODEL}:{DEFAULT_EMBEDDING_REVISION}:normalized-v1:{DIMENSIONS}"


@dataclass
class HttpEmbeddings:
    address: str
    transport: HttpTransport = field(default_factory=HttpTransport)
    space: str = SPACE
    dimensions: int = DIMENSIONS

    def embed(self: HttpEmbeddings, texts: list[str]) -> tuple[bool, str, list[list[float]]]:
        try:
            if not isinstance(texts, list) or any(not isinstance(t, str) or not t.strip() or len(t) > 16000 for t in texts):
                raise ValueError("Se requieren textos no vacíos de hasta 16000 caracteres")
            vectors: list[list[float]] = []
            # El núcleo puede entregar todo el catálogo. Dividir sin cambiar el orden.
            for start in range(0, len(texts), 15):
                batch = texts[start:start + 15]
                ok, message, response = self.transport.request("POST", self.address + "/embeddings", {}, {"texts": batch})
                if not ok:
                    return False, "Servicio de embeddings (EMBEDDING_URL): " + message, []
                body = response["body"]
                data = body.get("salida", {})
                if body.get("resultado") is not True or body.get("mensaje") != "ok":
                    raise ValueError("La API de embeddings informó un fallo")
                if not isinstance(data, dict) or data.get("space") != self.space or data.get("dimensions") != self.dimensions:
                    raise ValueError("Espacio de embeddings incompatible")
                output = data.get("vectors")
                if not isinstance(output, list) or len(output) != len(batch):
                    raise ValueError("Cantidad incorrecta de vectores")
                for vector in output:
                    if not isinstance(vector, list) or len(vector) != self.dimensions or not all(type(v) in (int, float) and math.isfinite(v) for v in vector):
                        raise ValueError("Vector remoto inválido")
                    if not math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, abs_tol=1e-4):
                        raise ValueError("Vector remoto sin normalizar")
                    vectors.append([float(v) for v in vector])
            return True, "ok", vectors
        except Exception as e:
            logger.error("Error en HttpEmbeddings.embed: %s", e)
            return False, "Respuesta inválida del servicio de embeddings", []


def create(settings: Settings, transport: HttpTransport | None = None) -> tuple[bool, str, HttpEmbeddings | None]:
    try:
        if settings.embedding_model != DEFAULT_EMBEDDING_MODEL or settings.embedding_revision not in {"", DEFAULT_EMBEDDING_REVISION} or settings.dimensions not in {None, DIMENSIONS}:
            raise ValueError("El servicio HTTP requiere el modelo, revisión y dimensión de carrerags")
        address = settings.embedding_url.rstrip("/")
        parsed = urlsplit(address)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("EMBEDDING_URL debe ser una dirección HTTP sin credenciales ni ruta")
        _ = parsed.port
        transport = transport if transport is not None else HttpTransport(settings.timeout)
        ok, message, response = transport.request("GET", address + "/health", {})
        if not ok:
            return False, "Servicio de embeddings (EMBEDDING_URL): " + message, None
        body = response["body"]
        data = body.get("salida", {})
        if body.get("resultado") is not True or body.get("mensaje") != "ok" or not isinstance(data, dict):
            raise ValueError("El servicio de embeddings no está listo")
        if data.get("space") != SPACE or data.get("dimensions") != DIMENSIONS or data.get("model") != DEFAULT_EMBEDDING_MODEL or data.get("revision") != DEFAULT_EMBEDDING_REVISION:
            raise ValueError("Identidad remota incompatible")
        return True, "ok", HttpEmbeddings(address, transport)
    except Exception as e:
        logger.error("Error en embeddings_http.create: %s", e)
        return False, "No se pudo conectar con un servicio de embeddings compatible", None
