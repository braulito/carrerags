"""Prueba con pesos reales dentro de la imagen ARM64, ejecutada por el usuario.

Entrada estándar mediante docker run --network none; bloquea además conexiones Python.
"""

from __future__ import annotations

import json
import logging
import math
import platform
from typing import Any
from unittest.mock import patch

from carrerags_embeddings.constants import DIMENSIONS, SPACE
from carrerags_embeddings.model import load_model

logger = logging.getLogger(__name__)


def verify() -> tuple[bool, str, dict[str, Any]]:
    try:
        if platform.machine() not in {"aarch64", "arm64"}:
            raise ValueError("Se requiere ARM64 nativo")
        with patch("socket.socket.connect", side_effect=AssertionError("Conexión de red prohibida")), \
             patch("socket.create_connection", side_effect=AssertionError("Conexión de red prohibida")):
            ok, message, engine = load_model()
            if not ok or engine is None:
                return False, message, {}
            texts = ["¿Dónde estudiar ingeniería?", "日本語の文章", "¿Dónde estudiar ingeniería?"]
            ok, message, first = engine.encode(texts)
            if not ok:
                return False, message, {}
            ok, message, second = engine.encode(list(reversed(texts[:2])))
            if not ok:
                return False, message, {}
            assert len(first) == 3 and all(len(v) == DIMENSIONS for v in first)
            assert all(math.isclose(math.sqrt(sum(x*x for x in v)), 1.0, abs_tol=1e-4) for v in first)
            assert max(abs(x-y) for x, y in zip(first[0], first[2])) < 1e-5
            assert max(abs(x-y) for x, y in zip(first[0], second[1])) < 1e-5
            assert max(abs(x-y) for x, y in zip(first[1], second[0])) < 1e-5
        return True, "ok", {"space": SPACE, "dimensions": DIMENSIONS, "offline": True, "order": True}
    except Exception as e:
        logger.error("Error en verify: %s", e)
        return False, "Falló la verificación ARM64 sin red: " + str(e), {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success, message, data = verify()
    print(json.dumps({"resultado": success, "mensaje": message, "salida": data}, ensure_ascii=False))
    raise SystemExit(0 if success else 1)
