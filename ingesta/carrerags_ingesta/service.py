"""Preparación de vectores mediante el módulo de embeddings configurado."""

from __future__ import annotations

import logging
import math
from typing import Any

from .contracts import Embedder
from .domain import Point, digest

logger = logging.getLogger(__name__)


def build_points(catalog: dict[str, Any], embedder: Embedder) -> tuple[bool, str, list[Point]]:
    try:
        entries = [entry for entry in catalog["offers"].values() if entry["active"]]
        missing: list[tuple[dict[str, Any], str]] = []
        for entry in entries:
            ok, message, text_hash = digest(entry["offer"]["text"])
            if not ok:
                return False, message, []
            cache = entry.get("vector_cache", {})
            vector = cache.get("vector", [])
            valid = cache.get("space") == embedder.space and cache.get("text_hash") == text_hash
            valid = valid and len(vector) == embedder.dimensions and any(vector) and all(isinstance(value, (float, int)) and math.isfinite(value) for value in vector)
            if not valid:
                missing.append((entry, text_hash))
        if missing:
            ok, message, vectors = embedder.embed([entry["offer"]["text"] for entry, text_hash in missing])
            if not ok:
                return False, message, []
            if len(vectors) != len(missing):
                raise ValueError("El proveedor devolvió una cantidad incorrecta de vectores")
            for (entry, text_hash), vector in zip(missing, vectors):
                if len(vector) != embedder.dimensions or not any(vector) or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
                    raise ValueError("El proveedor devolvió un vector inválido")
                entry["vector_cache"] = {"space": embedder.space, "text_hash": text_hash, "vector": vector}
        points = [Point(entry["offer"]["id"], entry["vector_cache"]["vector"],
                        {**entry["offer"], "active": True, "embedding_space": embedder.space,
                         "catalog_scope": "all_active_offers"}) for entry in entries]
        catalog["embedding_space"] = embedder.space
        catalog["report"]["embedded"] = len(missing)
        catalog["report"]["reused_vectors"] = len(entries) - len(missing)
        catalog["report"]["indexed"] = len(entries)
        return True, "ok", points
    except Exception as e:
        logger.error("Error en build_points: %s", e)
        return False, "No se pudieron preparar los vectores", []

