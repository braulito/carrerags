"""Formato compartido de fecha y hora local para aplicación y servidor."""

import json
import logging
from logging.config import dictConfig
from pathlib import Path

logger = logging.getLogger(__name__)


def configurar_logs() -> tuple[bool, str, None]:
    """Aplica la misma configuración disponible para --log-config de Uvicorn."""
    try:
        ruta = Path(__file__).resolve().parents[1] / "log_config.json"
        configuracion = json.loads(ruta.read_text(encoding="utf-8"))
        dictConfig(configuracion)
        return True, "ok", None
    except Exception as e:
        logger.error("Error en configurar_logs: %s", e)
        return False, "No se pudo configurar el formato de los logs", None
