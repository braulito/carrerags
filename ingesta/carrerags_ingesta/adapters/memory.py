"""Motor local de referencia para pruebas y desarrollo sin servicios."""

from __future__ import annotations

import copy
import logging
import math
from operator import attrgetter
from dataclasses import dataclass, field
from typing import Any

from ..domain import Constraints, Hit, Point, matches

logger = logging.getLogger(__name__)


@dataclass
class MemoryStore:
    points: list[Point] = field(default_factory=list)
    space: str = ""
    dimensions: int = 0

    def health(self: MemoryStore) -> tuple[bool, str, dict[str, Any]]:
        try:
            return True, "ok", {"engine": "memory", "persistent": False}
        except Exception as e:
            logger.error("Error en MemoryStore.health: %s", e)
            return False, "Motor de memoria no disponible", {}

    def replace(self: MemoryStore, points: list[Point], space: str, dimensions: int) -> tuple[bool, str, dict[str, Any]]:
        try:
            if not space or dimensions <= 0 or len({p.id for p in points}) != len(points):
                raise ValueError("Espacio, dimensión o identificadores inválidos")
            for point in points:
                if len(point.vector) != dimensions or not all(math.isfinite(value) for value in point.vector) or not any(point.vector):
                    raise ValueError("Vector inválido")
            replacement = copy.deepcopy(points)
            self.points, self.space, self.dimensions = replacement, space, dimensions
            return True, "ok", {"points": len(points)}
        except Exception as e:
            logger.error("Error en MemoryStore.replace: %s", e)
            return False, "No se pudo publicar el catálogo en memoria", {}

    def search(self: MemoryStore, vector: list[float], constraints: Constraints, limit: int, space: str) -> tuple[bool, str, list[Hit]]:
        try:
            if space != self.space or len(vector) != self.dimensions or not 1 <= limit <= 100:
                raise ValueError("Espacio, dimensión o límite incompatible")
            norm = math.sqrt(sum(value * value for value in vector))
            if not norm or not all(math.isfinite(value) for value in vector):
                raise ValueError("Vector de consulta inválido")
            hits: list[Hit] = []
            for point in self.points:
                ok, message, accepted = matches(point.payload, constraints)
                if not ok:
                    return False, message, []
                if accepted:
                    score = sum(a * b for a, b in zip(vector, point.vector)) / (norm * math.sqrt(sum(value * value for value in point.vector)))
                    hits.append(Hit(point.id, score, copy.deepcopy(point.payload)))
            hits.sort(key=attrgetter("score"), reverse=True)
            return True, "ok", hits[:limit]
        except Exception as e:
            logger.error("Error en MemoryStore.search: %s", e)
            return False, "No se pudo buscar en el motor de memoria", []

    def fetch(self: MemoryStore, ids: list[str]) -> tuple[bool, str, list[dict[str, Any]]]:
        try:
            return True, "ok", [copy.deepcopy(point.payload) for point in self.points if point.id in ids]
        except Exception as e:
            logger.error("Error en MemoryStore.fetch: %s", e)
            return False, "No se pudieron recuperar las ofertas", []
