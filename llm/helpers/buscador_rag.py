"""Búsqueda adaptada de consultador/run.py usando solo embeddings HTTP."""

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from helpers.contratos_llm import ConsultaPreRag
from helpers.rag.config import read_settings
from helpers.rag.domain import HEADERS, Constraints, Hit
from helpers.rag.embeddings_http import create as crear_embeddings_http
from helpers.rag.http import HttpTransport
from helpers.rag.qdrant import QdrantStore
from helpers.rag.relevancia import priorizar_carrera, recuperar_catalogo

logger = logging.getLogger("uvicorn.error")


def extraer_originales(hits: list[Hit]) -> tuple[bool, str, list[dict[str, Any]]]:
    """Conserva los siete campos originales, como consultador/run.py."""
    try:
        salida: list[dict[str, Any]] = []
        for hit in hits:
            original = hit.payload.get("original")
            if not isinstance(original, dict) or any(
                not isinstance(original.get(campo), str) or not original[campo].strip()
                for campo in HEADERS
            ):
                raise ValueError("Una carrera no contiene los siete campos originales completos")
            salida.append({"original": {campo: original[campo] for campo in HEADERS}})
        return True, "ok", salida
    except Exception as e:
        logger.error("Error en extraer_originales: %s", e)
        return False, "Qdrant devolvió una carrera sin los campos originales esperados", []


def _fallo_servicio(mensaje: str, transporte: HttpTransport) -> tuple[bool, str, dict[str, Any]]:
    """Conserva el HTTP del transporte; un fallo sin respuesta se publica como 502."""
    try:
        codigo = transporte.last_http_status
        if type(codigo) is not int or not 400 <= codigo <= 599:
            codigo = 502
        return False, mensaje, {"http_status": codigo, "ofertas": [], "cantidad": 0}
    except Exception as e:
        logger.error("Error en _fallo_servicio: %s", e)
        return False, "No se pudo completar la búsqueda", {"http_status": 502, "ofertas": [], "cantidad": 0}


def buscar_ofertas(consulta: dict[str, Any], limite: int = 10) -> tuple[bool, str, dict[str, Any]]:
    """Busca los filtros normalizados con el flujo trasladado del consultador.

    Usa el servicio propio de embeddings, verifica su identidad y la dimensión
    del índice, aplica los filtros y rescata coincidencias fuera del top vectorial.
    No carga modelos ML, no escribe archivos y no modifica Qdrant.
    """
    codigo_error = 500
    try:
        if type(limite) is not int or not 1 <= limite <= 100:
            return False, "El límite debe ser un entero entre 1 y 100", {"http_status": 422}
        filtros = ConsultaPreRag.model_validate(consulta)
        valores = filtros.model_dump()
        if any(isinstance(valor, str) and not valor.strip() for valor in valores.values()):
            return False, "Los filtros no pueden contener textos vacíos", {"http_status": 422}
        if all(valor is None for valor in valores.values()):
            return False, "No se identificaron criterios de búsqueda", {"http_status": 404, "ofertas": [], "cantidad": 0}

        load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)
        namespace = os.getenv("VECTORIAL_NAMESPACE", "").strip()
        if not namespace:
            namespace = os.getenv("VECOTRIAL_NAMESPACE", "").strip()
        configuracion = {
            "VECTORIAL": os.getenv("VECTORIAL", "").strip(),
            "VECTORIAL_NAMESPACE": namespace,
            "EMBEDDING_URL": os.getenv("EMBEDDING_URL", "").strip(),
            "HTTP_TIMEOUT": os.getenv("HTTP_TIMEOUT", "60").strip(),
            "EMBEDDING_PROVIDER": "http",
        }
        if not all(configuracion[clave] for clave in ("VECTORIAL", "VECTORIAL_NAMESPACE", "EMBEDDING_URL")):
            raise ValueError("Se requieren VECTORIAL, VECTORIAL_NAMESPACE y EMBEDDING_URL")
        ok, mensaje, settings = read_settings(configuracion)
        if not ok or settings is None:
            return False, mensaje, {"http_status": 500}

        transporte = HttpTransport(timeout=settings.timeout)
        codigo_error = 502
        logger.info("Inicio de búsqueda RAG con embeddings HTTP")
        try:
            ok, mensaje, modelo = crear_embeddings_http(settings, transport=transporte)
            if not ok or modelo is None:
                return _fallo_servicio(mensaje, transporte)
            # Embedding solo de los filtros interpretados; no reenviar instrucciones
            # de la pregunta original ni el prompt de la LLM a la búsqueda.
            etiquetas = {
                "carrera": "Carrera", "nivel_educativo": "Nivel",
                "institucion": "Institución", "ubicacion": "Ubicación", "modalidad": "Modalidad",
            }
            texto = ". ".join(f"{etiquetas[campo]}: {valor}" for campo, valor in valores.items() if valor is not None)
            ok, mensaje, vectores = modelo.embed([texto])
            if not ok:
                return _fallo_servicio(mensaje, transporte)
            condiciones = Constraints(
                institution=filtros.institucion, location=filtros.ubicacion,
                level=filtros.nivel_educativo, modality=filtros.modalidad,
            )
            motor = QdrantStore(settings.vectorial, settings.namespace, transport=transporte)
            ok, mensaje, hits = motor.search(vectores[0], condiciones, limite, modelo.space)
            if not ok:
                return _fallo_servicio(mensaje, transporte)
            ok, mensaje, catalogo = recuperar_catalogo(motor, condiciones)
            if not ok:
                return _fallo_servicio(mensaje, transporte)
            ok, mensaje, hits = priorizar_carrera(
                filtros.carrera or "", catalogo, hits, limite, solo_filtros=filtros.carrera is None,
            )
            if not ok:
                return _fallo_servicio(mensaje, transporte)
            ok, mensaje, ofertas = extraer_originales(hits)
            if not ok:
                return _fallo_servicio(mensaje, transporte)
            if not ofertas:
                return False, "No se encontraron ofertas para los criterios indicados", {
                    "http_status": 404, "ofertas": [], "cantidad": 0,
                }
            return True, "ok", {"ofertas": ofertas, "cantidad": len(ofertas)}
        finally:
            logger.info("Fin de búsqueda RAG con embeddings HTTP")
    except ValidationError as e:
        logger.error("Error en buscar_ofertas: %s", e.errors(include_input=False, include_url=False))
        return False, "Los filtros de búsqueda no cumplen el contrato", {"http_status": 422}
    except Exception as e:
        logger.error("Error en buscar_ofertas: %s", e)
        return False, "No se pudo completar la búsqueda de ofertas", {
            "http_status": codigo_error, "ofertas": [], "cantidad": 0,
        }
