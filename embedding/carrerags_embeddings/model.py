"""Carga única en CPU; ninguna descarga ni búsqueda remota al ejecutar."""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from .constants import DIMENSIONS, MODEL_ID, MODEL_PATH, REVISION, SPACE

logger = logging.getLogger(__name__)


@dataclass
class Embeddings:
    model: Any = field(repr=False)
    lock: Any = field(default_factory=Lock, repr=False)

    def encode(self: Embeddings, texts: list[str]) -> tuple[bool, str, list[list[float]]]:
        try:
            encoded = self.model.encode(texts, batch_size=16, normalize_embeddings=True,
                                        show_progress_bar=False, convert_to_numpy=True)
            vectors = encoded.tolist()
            if len(vectors) != len(texts):
                raise ValueError("Cantidad incorrecta de vectores")
            for vector in vectors:
                if len(vector) != DIMENSIONS or not all(type(v) in (int, float) and math.isfinite(v) for v in vector):
                    raise ValueError("Vector inválido")
                if not math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, abs_tol=1e-4):
                    raise ValueError("Vector sin normalizar")
            return True, "ok", vectors
        except Exception as e:
            logger.error("Error en Embeddings.encode: %s", e)
            return False, "No se pudieron generar los embeddings", []


def load_model(model_path: Path = Path(MODEL_PATH)) -> tuple[bool, str, Embeddings | None]:
    try:
        # Antes de importar HF/Transformers, incluso fuera del contenedor.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        os.environ["DO_NOT_TRACK"] = "1"
        manifest = json.loads((model_path / "carrerags-model.json").read_text(encoding="utf-8"))
        if manifest != {"model": MODEL_ID, "revision": REVISION, "space": SPACE, "dimensions": DIMENSIONS}:
            raise ValueError("Identidad del modelo local incompatible")
        if not (model_path / "model.safetensors").is_file():
            raise ValueError("Faltan los pesos locales")
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        model = SentenceTransformer(str(model_path.resolve()), device="cpu", local_files_only=True,
                                    token=False, trust_remote_code=False,
                                    model_kwargs={"use_safetensors": True})
        if model.get_sentence_embedding_dimension() != DIMENSIONS:
            raise ValueError("Dimensión incompatible")
        model.eval()
        return True, "ok", Embeddings(model)
    except Exception as e:
        logger.error("Error en load_model: %s", e)
        return False, "No se pudo cargar el modelo local; reconstruir la imagen", None
