"""Endpoints de estado del servicio llm."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["Estado"])


def obtener_estado() -> tuple[bool, str, dict[str, str]]:
    """Devuelve el estado básico del servicio."""
    try:
        return True, "ok", {"nombre": "llm", "estado": "ok"}
    except Exception as e:
        logger.error("Error en obtener_estado: %s", e)
        return False, "No se pudo obtener el estado del servicio", {}


@router.get("/", response_model=None)
def estado() -> JSONResponse:
    """Adapta el contrato interno a una respuesta HTTP."""
    try:
        resultado, mensaje, salida = obtener_estado()
        return JSONResponse(
            status_code=200 if resultado else 500,
            content={"resultado": resultado, "mensaje": mensaje, "salida": salida},
        )
    except Exception as e:
        logger.error("Error en estado: %s", e)
        return JSONResponse(
            status_code=500,
            content={"resultado": False, "mensaje": "Error interno del servicio", "salida": {}},
        )
