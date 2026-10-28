"""Endpoints de preparación de preguntas para el RAG."""

import logging
from time import perf_counter_ns
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr

# USO OPEN AI
#from helpers.llm_openai import crea_prompt_pre_rag, genera_respuesta_usuario

#USO QWEN
from helpers.llm_qewn import crea_prompt_pre_rag, genera_respuesta_usuario

#USO PHI
#from helpers.llm_phi import crea_prompt_pre_rag, genera_respuesta_usuario

from helpers.buscador_rag import buscar_ofertas
from helpers.contratos_llm import ConsumoTokens
from helpers.respuesta_json import guardar_respuesta_json

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/llmrag", tags=["llmrag"])


class SolicitudTitulos(BaseModel):
    """Pregunta recibida en el body JSON."""

    pregunta: StrictStr


@router.post("/armador", response_model=None)
def armador(solicitud: SolicitudTitulos) -> JSONResponse:
    """Normaliza, busca ofertas y genera la respuesta humana para el usuario."""
    salida: dict[str, Any] = {}
    rendimiento: dict[str, Any] = {
        "tiempo_total_segundos": None,
        "tiempos_etapas_segundos": {"normalizacion": None, "rag": None, "respuesta_usuario": None},
        "llamadas_llm": {},
    }
    inicio_total = perf_counter_ns()
    try:
        inicio_etapa = perf_counter_ns()
        try:
            resultado, mensaje, salida = crea_prompt_pre_rag(solicitud.pregunta)
        finally:
            rendimiento["tiempos_etapas_segundos"]["normalizacion"] = (perf_counter_ns() - inicio_etapa) / 1_000_000_000
        salida = dict(salida)
        if "rendimiento" in salida:
            rendimiento["llamadas_llm"]["normalizacion"] = salida.pop("rendimiento")
        consumos: dict[str, dict[str, int | None]] = {}
        if "consumo_tokens" in salida:
            consumos["normalizacion"] = dict(salida["consumo_tokens"])
            salida["consumos_llm"] = dict(consumos)
        if resultado:
            campos = ("carrera", "nivel_educativo", "institucion", "ubicacion", "modalidad")
            consulta = {campo: salida[campo] for campo in campos}
            logger.info("Inicio de llamada al RAG")
            inicio_etapa = perf_counter_ns()
            try:
                resultado, mensaje, ofertas = buscar_ofertas(consulta)
            finally:
                rendimiento["tiempos_etapas_segundos"]["rag"] = (perf_counter_ns() - inicio_etapa) / 1_000_000_000
                logger.info("Fin de llamada al RAG")
            salida = {**salida, **ofertas}
            if resultado:
                inicio_etapa = perf_counter_ns()
                try:
                    resultado, mensaje, respuesta_usuario = genera_respuesta_usuario(
                        solicitud.pregunta, salida["ofertas"],
                    )
                finally:
                    rendimiento["tiempos_etapas_segundos"]["respuesta_usuario"] = (perf_counter_ns() - inicio_etapa) / 1_000_000_000
                respuesta_usuario = dict(respuesta_usuario)
                if "rendimiento" in respuesta_usuario:
                    rendimiento["llamadas_llm"]["respuesta_usuario"] = respuesta_usuario.pop("rendimiento")
                if "consumo_tokens" in respuesta_usuario:
                    consumos["respuesta_usuario"] = dict(respuesta_usuario["consumo_tokens"])
                salida = {**salida, **respuesta_usuario, "consumos_llm": dict(consumos)}
                if consumos:
                    salida["consumo_tokens"] = {
                        campo: (
                            None if any(consumo[campo] is None for consumo in consumos.values())
                            else sum(consumo[campo] for consumo in consumos.values())
                        )
                        for campo in ConsumoTokens.model_fields
                    }
        codigo_http = 200 if resultado else salida.get("http_status", 500)
        if not resultado and (type(codigo_http) is not int or not 400 <= codigo_http <= 599):
            codigo_http = 500
    except Exception as e:
        logger.error("Error en armador: %s", e)
        resultado = False
        mensaje = "Error interno del servicio"
        codigo_http = 500
    finally:
        rendimiento["tiempo_total_segundos"] = (perf_counter_ns() - inicio_total) / 1_000_000_000

    try:
        cuerpo = {
            "resultado": resultado,
            "pregunta": solicitud.pregunta,
            "mensaje": mensaje,
            "rendimiento": rendimiento,
            "salida": {
                clave: valor for clave, valor in salida.items() if clave not in {"ofertas", "cantidad"}
            } if isinstance(salida, dict) else {},
        }
        guardado, mensaje_guardado, _ = guardar_respuesta_json(cuerpo)
        if not guardado:
            cuerpo["resultado"] = False
            cuerpo["mensaje"] = mensaje_guardado
            codigo_http = 500
        return JSONResponse(status_code=codigo_http, content=cuerpo)
    except Exception as e:
        logger.error("Error en armador al guardar o devolver la respuesta: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "resultado": False,
                "pregunta": solicitud.pregunta,
                "mensaje": "Error interno del servicio",
                "rendimiento": rendimiento,
                "salida": {},
            },
        )
