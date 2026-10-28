"""Conversión de valores de configuración. No abre archivos por sí misma."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBEDDING_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


@dataclass
class Settings:
    vectorial: str = ""
    vector_provider: str = "qdrant"
    namespace: str = "carrerags"
    embedding_provider: str = "local"
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_revision: str = ""
    embedding_url: str = "http://macmini:8081"
    dimensions: int | None = None
    timeout: float = 60.0
    vector_key: str = field(default="", repr=False)


def read_settings(values: Mapping[str, str] | None = None) -> tuple[bool, str, Settings | None]:
    try:
        source = os.environ if values is None else values
        address = source.get("VECTORIAL", "").strip()
        if address and "://" not in address:
            address = "http://" + address
        if address:
            parsed = urlsplit(address)
            if parsed.username or parsed.password:
                raise ValueError("VECTORIAL no admite credenciales; usar VECTORIAL_API_KEY")
        dimensions = source.get("EMBEDDING_DIMENSIONS", "").strip()
        timeout = source.get("HTTP_TIMEOUT", "60")
        if (dimensions and not re.fullmatch(r"[0-9]{1,6}", dimensions)) or not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,3})?", timeout):
            raise ValueError("Dimensión o timeout no numéricos")
        settings = Settings(
            vectorial=address.rstrip("/"), vector_provider=source.get("VECTORIAL_PROVIDER", "qdrant"),
            namespace=source.get("VECTORIAL_NAMESPACE", "carrerags"),
            embedding_provider=source.get("EMBEDDING_PROVIDER", "local").strip(),
            embedding_model=source.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            embedding_revision=source.get("EMBEDDING_REVISION", ""),
            embedding_url=source.get("EMBEDDING_URL", "http://macmini:8081").strip(),
            dimensions=int(dimensions) if dimensions else None, timeout=float(timeout),
            vector_key=source.get("VECTORIAL_API_KEY", ""),
        )
        if (settings.dimensions is not None and settings.dimensions <= 0) or not 0 < settings.timeout <= 300:
            raise ValueError("Dimensión o timeout fuera de rango")
        return True, "ok", settings
    except Exception as e:
        logger.error("Error en read_settings: %s", e)
        return False, "Configuración inválida: revisar VECTORIAL, EMBEDDING_DIMENSIONS y HTTP_TIMEOUT", None
