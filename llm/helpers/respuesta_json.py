"""Persistencia de la respuesta completa del endpoint en la carpeta JSON."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("uvicorn.error")
DIRECTORIO_JSON = Path(__file__).resolve().parents[1] / "JSON"


def guardar_respuesta_json(respuesta: dict[str, Any]) -> tuple[bool, str, str]:
    """Guarda JSON/AAAAMMDD-HHMMSS.json en UTF-8, con fecha y hora argentina."""
    try:
        fecha = datetime.now(timezone(timedelta(hours=-3)))
        archivo = DIRECTORIO_JSON / fecha.strftime("%Y%m%d-%H%M%S.json")
        contenido = json.dumps(respuesta, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        archivo.write_text(contenido, encoding="utf-8")
        logger.info("Respuesta JSON guardada en %s", archivo)
        return True, "ok", str(archivo)
    except Exception as e:
        logger.error("Error en guardar_respuesta_json: %s", e)
        return False, "No se pudo guardar la respuesta JSON", ""
