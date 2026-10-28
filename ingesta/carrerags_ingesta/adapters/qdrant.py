"""Qdrant REST: reconstruye una única colección física con nombre estable."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..domain import Constraints, Hit, Point, digest, matches, query_filter
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

    def health(self: QdrantStore) -> tuple[bool, str, dict[str, Any]]:
        try:
            return self.call("GET", "/collections")
        except Exception as e:
            logger.error("Error en QdrantStore.health: %s", e)
            return False, "Qdrant no disponible", {}

    def clear_previous(self: QdrantStore) -> tuple[bool, str, dict[str, Any]]:
        try:
            ok, message, response = self.call("GET", "/aliases")
            if not ok:
                return False, message, response
            aliases = response["result"]["aliases"]
            ok, message, response = self.call("GET", "/collections")
            if not ok:
                return False, message, response
            names = {item["name"] for item in response["result"]["collections"]}
            legacy_pattern = re.escape(self.namespace) + r"_g_[0-9a-f]{32}"
            managed = {name for name in names if name == self.namespace or re.fullmatch(legacy_pattern, name)}
            own_alias = False
            for alias in aliases:
                if alias["alias_name"] == self.namespace:
                    if alias["collection_name"] not in managed:
                        raise ValueError("El alias del catálogo apunta a una colección ajena al patrón administrado")
                    own_alias = True
                elif alias["collection_name"] in managed:
                    raise ValueError("Una colección del catálogo tiene otro alias; revisar su uso antes de reemplazarla")
            if own_alias:
                ok, message, response = self.call("POST", "/collections/aliases",
                    {"actions": [{"delete_alias": {"alias_name": self.namespace}}]})
                if not ok:
                    return False, message, response
                if response.get("result") is not True:
                    raise ValueError("Qdrant no confirmó la retirada del alias anterior")
            removed: list[str] = []
            for name in sorted(managed):
                ok, message, response = self.call("DELETE", "/collections/" + name)
                if not ok:
                    if response.get("http_status") == 404:
                        continue
                    return False, message, {**response, "removed_collections": removed}
                if response.get("result") is not True:
                    raise ValueError("Qdrant no confirmó la eliminación de una colección anterior")
                removed.append(name)
            return True, "ok", {"removed_collections": removed}
        except Exception as e:
            logger.error("Error en QdrantStore.clear_previous: %s", e)
            return False, "No se pudieron retirar las colecciones anteriores del catálogo: " + str(e), {}

    def replace(self: QdrantStore, points: list[Point], space: str, dimensions: int) -> tuple[bool, str, dict[str, Any]]:
        state = "preparing"
        try:
            if not space or dimensions <= 0 or len({point.id for point in points}) != len(points):
                raise ValueError("Espacio, dimensión o identificadores inválidos")
            for point in points:
                if len(point.vector) != dimensions or not any(point.vector) or not all(math.isfinite(value) for value in point.vector):
                    raise ValueError("Vector inválido")
            ok, message, space_hash = digest(space)
            if not ok:
                return False, message, {}
            vector_name = "v_" + space_hash[:24]
            collection = self.namespace
            state = "rebuilding"
            ok, message, cleanup = self.clear_previous()
            if not ok:
                return False, message, {**cleanup, "collection": collection, "publication_state": "incomplete"}
            logger.info("Creando la colección única del catálogo")
            ok, message, response = self.call("PUT", "/collections/" + collection,
                                               {"vectors": {vector_name: {"size": dimensions, "distance": "Cosine"}}})
            if not ok:
                return False, "No se pudo recrear el catálogo. " + message, {**response, "collection": collection, "publication_state": "incomplete"}
            if response.get("result") is not True:
                raise ValueError("Qdrant no confirmó la creación de la colección")
            for key in ("active", "eligible", "independent_entry", "modality", "management", "admission", "exams", "practices"):
                kind = "bool" if key in {"active", "eligible", "independent_entry"} else "keyword"
                ok, message, response = self.call("PUT", "/collections/" + collection + "/index?wait=true",
                                                  {"field_name": key, "field_schema": kind})
                if not ok:
                    return False, message, {**response, "collection": collection, "publication_state": "incomplete"}
            for start in range(0, len(points), 64):
                batch = [{"id": point.id, "vector": {vector_name: point.vector},
                          "payload": {**point.payload, "active": False}} for point in points[start:start + 64]]
                ok, message, response = self.call("PUT", "/collections/" + collection + "/points?wait=true", {"points": batch})
                if not ok:
                    return False, "La carga quedó incompleta; reejecutar la ingesta. " + message, {**response, "collection": collection, "publication_state": "incomplete"}
            ok, message, response = self.call("POST", "/collections/" + collection + "/points/count", {"exact": True})
            if not ok:
                return False, message, {**response, "collection": collection, "publication_state": "incomplete"}
            if response["result"]["count"] != len(points):
                raise ValueError("La cantidad cargada no coincide con el catálogo")
            ok, message, response = self.call("GET", "/collections")
            if not ok:
                return False, message, {**response, "collection": collection, "publication_state": "incomplete"}
            managed = {item["name"] for item in response["result"]["collections"]
                       if item["name"] == collection or re.fullmatch(re.escape(collection) + r"_g_[0-9a-f]{32}", item["name"])}
            if managed != {collection}:
                raise ValueError("No se pudo confirmar una única colección del catálogo")
            if points:
                ok, message, response = self.call("POST", "/collections/" + collection + "/points/payload?wait=true",
                                                   {"payload": {"active": True}, "filter": {}})
                if not ok:
                    return False, "No se pudo confirmar la activación; comprobar el catálogo antes de reintentar. " + message, {
                        **response, "collection": collection, "publication_state": "unknown"}
            return True, "ok", {"points": len(points), "collection": collection, "space": space,
                                 "removed_collections": cleanup["removed_collections"]}
        except Exception as e:
            logger.error("Error en QdrantStore.replace: %s", e)
            return False, "No se pudo completar el reemplazo del catálogo; reejecutar la ingesta", {
                "collection": self.namespace, "publication_state": state}

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

    def fetch(self: QdrantStore, ids: list[str]) -> tuple[bool, str, list[dict[str, Any]]]:
        try:
            if not ids:
                return True, "ok", []
            ok, message, response = self.call("POST", "/collections/" + self.namespace + "/points",
                                               {"ids": ids, "with_payload": True, "with_vector": False})
            if not ok:
                return False, message, []
            return True, "ok", [item["payload"] for item in response["result"]]
        except Exception as e:
            logger.error("Error en QdrantStore.fetch: %s", e)
            return False, "No se pudieron recuperar las ofertas", []
