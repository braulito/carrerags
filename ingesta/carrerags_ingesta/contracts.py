"""Contratos propios para módulos de embeddings y motores vectoriales."""

from __future__ import annotations

from typing import Any, Protocol

from .domain import Constraints, Hit, Point


class Embedder(Protocol):
    space: str
    dimensions: int

    def embed(self: Embedder, texts: list[str]) -> tuple[bool, str, list[list[float]]]: ...


class VectorStore(Protocol):
    """replace sustituye el catálogo completo y comunica fallos de publicación.

    El adaptador Qdrant mantiene una sola colección física con nombre estable:
    elimina la anterior y la reconstruye, con indisponibilidad durante la carga.
    Los puntos se cargan inactivos y se habilitan después de validar la cantidad.
    Un fallo no garantiza que la versión anterior siga disponible. Un timeout
    de activación debe informarse como resultado indeterminado.

    search debe aplicar todas las restricciones antes de limitar resultados.
    Un motor sin esa capacidad debe devolver error, nunca omitir filtros.
    """

    def health(self: VectorStore) -> tuple[bool, str, dict[str, Any]]: ...

    def replace(self: VectorStore, points: list[Point], space: str, dimensions: int) -> tuple[bool, str, dict[str, Any]]: ...

    def search(self: VectorStore, vector: list[float], constraints: Constraints, limit: int, space: str) -> tuple[bool, str, list[Hit]]: ...

    def fetch(self: VectorStore, ids: list[str]) -> tuple[bool, str, list[dict[str, Any]]]: ...
