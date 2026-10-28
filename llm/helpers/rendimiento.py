"""Métricas comparables sin confundir tiempo de solicitud con generación."""

import logging
import math
import re
from typing import Any

logger = logging.getLogger("uvicorn.error")


def medir_llamada(
    proveedor: str, modelo: str, duracion_ns: int,
    contenido: dict[str, Any], procesamiento_ms: str | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Adapta métricas opcionales; nunca estima tiempos internos ausentes."""
    try:
        if proveedor not in {"ollama", "openai"}:
            raise ValueError("Proveedor de rendimiento desconocido")
        if type(duracion_ns) is not int or duracion_ns < 0:
            raise ValueError("La duración de la solicitud debe ser un entero no negativo")

        tiempos: dict[str, int | None] = dict.fromkeys(("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"))
        if proveedor == "ollama":
            tokens = contenido.get("eval_count")
            for campo in tiempos:
                valor = contenido.get(campo)
                if type(valor) is int and valor >= 0:
                    tiempos[campo] = valor
                elif valor is not None:
                    logger.warning("Métrica de rendimiento Ollama inválida: %s", campo)
            metricas: dict[str, Any] = dict(tiempos)
            tiempo_servidor = tiempos["total_duration"] / 1_000_000_000 if tiempos["total_duration"] is not None else None
        else:
            uso = contenido.get("usage")
            tokens = uso.get("output_tokens") if isinstance(uso, dict) else None
            milisegundos = None
            if procesamiento_ms is not None:
                try:
                    if not isinstance(procesamiento_ms, str) or not re.fullmatch(r"\d+(?:\.\d+)?", procesamiento_ms.strip()):
                        raise ValueError("El header de tiempo debe ser un número decimal no negativo")
                    valor_ms = float(procesamiento_ms)
                    if not math.isfinite(valor_ms) or valor_ms < 0:
                        raise ValueError("Tiempo de procesamiento inválido")
                    milisegundos = valor_ms
                except Exception as e:
                    # No registrar el valor del header ni la configuración.
                    logger.error("Error en medir_llamada, header de tiempo OpenAI: %s", e)
            metricas = {"openai_processing_ms": milisegundos}
            tiempo_servidor = milisegundos / 1000 if milisegundos is not None else None

        tokens = tokens if type(tokens) is int and tokens >= 0 else None
        metricas["eval_count" if proveedor == "ollama" else "output_tokens"] = tokens
        generacion_ns = tiempos["eval_duration"]
        return True, "ok", {
            "proveedor": proveedor,
            "modelo": modelo,
            "tiempo_solicitud_segundos": duracion_ns / 1_000_000_000,
            "tiempo_servidor_segundos": tiempo_servidor,
            "tiempo_carga_segundos": tiempos["load_duration"] / 1_000_000_000 if tiempos["load_duration"] is not None else None,
            "tiempo_prompt_segundos": tiempos["prompt_eval_duration"] / 1_000_000_000 if tiempos["prompt_eval_duration"] is not None else None,
            "tiempo_generacion_segundos": generacion_ns / 1_000_000_000 if generacion_ns is not None else None,
            "tokens_salida": tokens,
            "tokens_por_segundo_generacion": round(tokens * 1_000_000_000 / generacion_ns, 6) if tokens is not None and generacion_ns else None,
            "tokens_por_segundo_solicitud": round(tokens * 1_000_000_000 / duracion_ns, 6) if tokens is not None and duracion_ns else None,
            "metricas_proveedor": metricas,
        }
    except Exception as e:
        logger.error("Error en medir_llamada: %s", e)
        return False, "No se pudo calcular el rendimiento de la llamada", {}
