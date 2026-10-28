"""Embeddings locales de Sentence Transformers; sin servicio ni API key."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from ..config import DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_REVISION, Settings
from ..contracts import Embedder

logger = logging.getLogger(__name__)


@dataclass
class LocalEmbeddings:
    space: str
    dimensions: int
    model: Any = field(repr=False)

    def embed(self: LocalEmbeddings, texts: list[str]) -> tuple[bool, str, list[list[float]]]:
        try:
            if not texts:
                return True, "ok", []
            if any(not isinstance(text, str) or not text.strip() for text in texts):
                raise ValueError("Se requieren textos no vacíos")
            encoded = self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                        show_progress_bar=False, convert_to_numpy=True)
            vectors = encoded.tolist()
            if len(vectors) != len(texts):
                raise ValueError("Cantidad incorrecta de vectores")
            for vector in vectors:
                if len(vector) != self.dimensions or not any(vector) or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
                    raise ValueError("Vector inválido o incompatible")
            return True, "ok", [[float(value) for value in vector] for vector in vectors]
        except Exception as e:
            logger.error("Error en LocalEmbeddings.embed: %s", e)
            return False, "No se pudieron generar los embeddings locales", []


def create(settings: Settings) -> tuple[bool, str, Embedder | None]:
    try:
        from sentence_transformers import SentenceTransformer

        if not settings.embedding_model.strip():
            raise ValueError("Falta el nombre del modelo local")
        logger.info("Cargando modelo local de embeddings; la primera ejecución puede descargar sus pesos")
        revision = settings.embedding_revision or (DEFAULT_EMBEDDING_REVISION if settings.embedding_model == DEFAULT_EMBEDDING_MODEL else None)
        model = SentenceTransformer(settings.embedding_model, device="cpu", token=False,
                                    trust_remote_code=False, revision=revision)
        dimensions = model.get_sentence_embedding_dimension()
        if not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("El modelo no declara una dimensión válida")
        if settings.dimensions is not None and dimensions != settings.dimensions:
            raise ValueError("EMBEDDING_DIMENSIONS no coincide con el modelo local")
        space = "sentence-transformers:" + settings.embedding_model + ":" + (revision or "main") + ":normalized-v1:" + str(dimensions)
        return True, "ok", LocalEmbeddings(space, dimensions, model)
    except ModuleNotFoundError as e:
        logger.error("Error en local.create, dependencia faltante: %s", e)
        return False, "Instalar dependencias con python -m pip install -r reqs.txt", None
    except Exception as e:
        logger.error("Error en local.create: %s", e)
        return False, "No se pudo cargar el modelo local; revisar el modelo, su dimensión y el acceso a sus pesos", None
