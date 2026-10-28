"""Selección de factorías por nombre o por especificación paquete.modulo:funcion."""

from __future__ import annotations

import importlib
import logging
import re
from typing import Any

from .config import Settings

logger = logging.getLogger(__name__)
FACTORIES = {
    "vector": {"qdrant": "carrerags_ingesta.adapters.factories:qdrant", "memory": "carrerags_ingesta.adapters.factories:memory"},
    "embedding": {"local": "carrerags_ingesta.adapters.local:create",
                  "http": "carrerags_ingesta.adapters.embeddings_http:create"},
}
METHODS = {"vector": ("health", "replace", "search", "fetch"), "embedding": ("embed",)}


def create_adapter(role: str, name: str, settings: Settings) -> tuple[bool, str, Any]:
    try:
        if role not in FACTORIES:
            raise ValueError("Tipo de adaptador desconocido")
        if role == "embedding" and not name:
            return False, "Configurar EMBEDDING_PROVIDER=paquete.modulo:factoria para generar vectores", None
        spec = FACTORIES[role].get(name, name)
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", spec):
            raise ValueError("Proveedor desconocido; usar nombre registrado o paquete.modulo:factoria")
        module_name, function_name = spec.split(":")
        factory = getattr(importlib.import_module(module_name), function_name)
        result = factory(settings)
        if not isinstance(result, tuple) or len(result) != 3 or not isinstance(result[0], bool):
            raise ValueError("La factoría no respeta el contrato de tres valores")
        ok, message, adapter = result
        if not ok:
            return False, message, None
        if any(not callable(getattr(adapter, method, None)) for method in METHODS[role]):
            raise ValueError("Adaptador incompleto")
        if role == "embedding" and (not isinstance(adapter.space, str) or not adapter.space or not isinstance(adapter.dimensions, int) or adapter.dimensions <= 0):
            raise ValueError("El adaptador de embeddings debe declarar espacio y dimensión")
        if role == "embedding" and settings.dimensions is not None and adapter.dimensions != settings.dimensions:
            raise ValueError("La dimensión del módulo configurado no coincide con EMBEDDING_DIMENSIONS")
        return True, "ok", adapter
    except Exception as e:
        logger.error("Error en create_adapter: %s", e)
        return False, "No se pudo crear el adaptador " + role, None
