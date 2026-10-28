"""Comprueba que la API responde, sin consultar LLM, embeddings ni Qdrant."""

import json
import logging
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def comprobar_api() -> tuple[bool, str, None]:
    """Consulta el estado local sin cargar configuración o secretos."""
    try:
        with urlopen("http://127.0.0.1:8021/", timeout=3) as respuesta:
            contenido = json.load(respuesta)
        if contenido.get("resultado") is not True or contenido.get("salida", {}).get("nombre") != "llm":
            raise ValueError("La API no confirmó su estado")
        return True, "ok", None
    except Exception as e:
        logger.error("Error en comprobar_api: %s", e)
        return False, "La API no está disponible", None


if __name__ == "__main__":
    resultado, mensaje, _ = comprobar_api()
    raise SystemExit(0 if resultado else 1)
