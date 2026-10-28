"""Consulta Qdrant trasladada de ingesta; no incluye operaciones de escritura."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from .domain import Constraints, Hit, digest, matches, query_filter
from .http import HttpTransport

logger = logging.getLogger(__name__)


@dataclass
class QdrantStore:
    address: str
    namespace: str = "carrerags"
    api_key: str = field(default="", repr=False)
    transport: HttpTransport = field(default_factory=HttpTransport)

    def call(self: QdrantStore, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[bool, str, dict[str, Any]]:
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", self.namespace):
                raise ValueError("Nombre de catálogo inválido")
            if not self.address:
                raise ValueError("Falta configurar VECTORIAL")
            headers = {"api-key": self.api_key} if self.api_key else {}
            ok, message, response = self.transport.request(method, self.address.rstrip("/") + path, headers, body)
            if not ok:
                return False, "Qdrant (VECTORIAL): " + message, response
            content = response.get("body", {})
            if content.get("status") != "ok":
                raise ValueError("Qdrant no confirmó la operación")
            return True, "ok", {"http_status": response["http_status"], "result": content.get("result")}
        except Exception as e:
            logger.error("Error en QdrantStore.call: %s", e)
            return False, "No se pudo completar la operación con Qdrant", {}

    def search(self: QdrantStore, vector: list[float], constraints: Constraints, limit: int, space: str) -> tuple[bool, str, list[Hit]]:
        try:
            if not 1 <= limit <= 100 or not vector or not any(vector) or not all(math.isfinite(value) for value in vector):
                raise ValueError("Consulta inválida")
            ok, message, filters = query_filter(constraints)
            if not ok:
                return False, message, []
            ok, message, space_hash = digest(space)
            if not ok:
                return False, message, []
            vector_name = "v_" + space_hash[:24]
            ok, message, response = self.call("GET", "/collections/" + self.namespace)
            if not ok:
                return False, message, []
            definition = response["result"]["config"]["params"]["vectors"].get(vector_name)
            if not definition or definition["size"] != len(vector):
                raise ValueError("Cambió el modelo o la dimensión de embeddings; reconstruir el índice")
            ok, message, response = self.call("POST", "/collections/" + self.namespace + "/points/query",
                                               {"query": vector, "using": vector_name, "filter": filters, "limit": limit, "with_payload": True})
            if not ok:
                return False, message, []
            hits = [Hit(str(item["id"]), float(item["score"]), item["payload"]) for item in response["result"]["points"]]
            for hit in hits:
                ok, message, accepted = matches(hit.payload, constraints)
                if not ok or not accepted:
                    raise ValueError("El motor devolvió una oferta incompatible con los filtros")
            return True, "ok", hits
        except Exception as e:
            logger.error("Error en QdrantStore.search: %s", e)
            return False, "No se pudo buscar en Qdrant: " + str(e), []

