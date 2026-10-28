"""Métricas y tiempos deterministas, sin secretos, esperas ni servicios reales.

Ejecutar desde llm: python -m tests.check_rendimiento
"""

import io
import json
import logging
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from helpers import llm_openai, llm_qewn
from helpers.rendimiento import medir_llamada
from routers import llmrag

logger = logging.getLogger(__name__)


def comprobar_rendimiento() -> tuple[bool, str, list[str]]:
    try:
        casos: list[str] = []
        verificador = TestCase()
        nativo = {
            "eval_count": 100, "total_duration": 7_000_000_000,
            "load_duration": 1_000_000_000, "prompt_eval_duration": 2_000_000_000,
            "eval_duration": 4_000_000_000,
        }
        ok, mensaje, qwen = medir_llamada("ollama", "modelo-ficticio", 8_000_000_000, nativo)
        assert ok and mensaje == "ok"
        assert qwen["tiempo_solicitud_segundos"] == 8
        assert qwen["tiempo_servidor_segundos"] == 7
        assert qwen["tiempo_carga_segundos"] == 1
        assert qwen["tiempo_prompt_segundos"] == 2
        assert qwen["tiempo_generacion_segundos"] == 4
        assert qwen["tokens_por_segundo_generacion"] == 25
        assert qwen["tokens_por_segundo_solicitud"] == 12.5
        assert qwen["metricas_proveedor"] == nativo
        casos.append("Ollama: nanosegundos originales, segundos y velocidades con denominadores separados")

        ok, _, openai = medir_llamada("openai", "modelo-ficticio", 8_000_000_000, {"usage": {"output_tokens": 100}}, "6000")
        assert ok and openai["tiempo_servidor_segundos"] == 6
        assert openai["tokens_por_segundo_solicitud"] == 12.5
        for campo in ("tiempo_carga_segundos", "tiempo_prompt_segundos", "tiempo_generacion_segundos", "tokens_por_segundo_generacion"):
            assert openai[campo] is None
        assert openai["metricas_proveedor"] == {"openai_processing_ms": 6000.0, "output_tokens": 100}
        casos.append("OpenAI: header en milisegundos y velocidad de solicitud sin inventar generación pura")

        for campo, valor in (("eval_duration", 0), ("eval_duration", None), ("eval_duration", -1), ("eval_duration", True), ("eval_duration", "4000000000")):
            ok, _, dato = medir_llamada("ollama", "ficticio", 0, {**nativo, campo: valor})
            assert ok and dato["tokens_por_segundo_generacion"] is None
            assert dato["tokens_por_segundo_solicitud"] is None
        for tokens in (None, True, -1, "100"):
            ok, _, dato = medir_llamada("ollama", "ficticio", 1_000_000_000, {**nativo, "eval_count": tokens})
            assert ok and dato["tokens_salida"] is None and dato["tokens_por_segundo_generacion"] is None
        ok, _, dato = medir_llamada("ollama", "ficticio", 1_000_000_000, {**nativo, "eval_count": 0})
        assert ok and dato["tokens_por_segundo_generacion"] == 0
        for header in ("inválido", "nan", "inf", "-1"):
            with verificador.assertLogs("uvicorn.error", level="ERROR"):
                ok, _, dato = medir_llamada("openai", "ficticio", 1_000_000_000, {"usage": {"output_tokens": 100}}, header)
            assert ok and dato["tiempo_servidor_segundos"] is None
        ok, _, dato = medir_llamada("openai", "ficticio", 1_000_000_000, {})
        assert ok and dato["tokens_salida"] is None and dato["tiempo_servidor_segundos"] is None
        casos.append("Ausencias, tipos inválidos y duración cero no fabrican tasas ni rompen la consulta")

        respuesta_qwen = {
            **nativo, "prompt_eval_count": 200,
            "done": True, "done_reason": "stop", "message": {"role": "assistant", "content": "OK"},
        }
        respuesta_openai = {
            "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}],
            "usage": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
        }
        for modulo, contenido, destino in (
            (llm_qewn, respuesta_qwen, "http://ollama.invalid/api/chat"),
            (llm_openai, respuesta_openai, "clave-ficticia"),
        ):
            flujo = io.BytesIO(json.dumps(contenido).encode())
            flujo.headers = {"openai-processing-ms": "1500"}
            with (
                patch.object(modulo, "load_dotenv", side_effect=AssertionError("Configuración real bloqueada")),
                patch.object(modulo, "urlopen", return_value=flujo) as red,
                patch.object(modulo, "perf_counter_ns", side_effect=[0, 8_000_000_000]),
            ):
                ok, _, datos = modulo._llamar_llm({"model": "modelo-ficticio"}, destino, "prueba")
            assert ok and datos["rendimiento"]["tiempo_solicitud_segundos"] == 8
            assert datos["rendimiento"]["tokens_por_segundo_solicitud"] == 12.5
            red.assert_called_once()
            if modulo is llm_qewn:
                assert datos["rendimiento"]["tokens_por_segundo_generacion"] == 25
            else:
                assert datos["rendimiento"]["tiempo_servidor_segundos"] == 1.5
            for error, status in (
                (TimeoutError("fallo simulado"), 502),
                (HTTPError("http://servicio.invalid", 429, "fallo simulado", None, None), 429),
            ):
                with (
                    patch.object(modulo, "urlopen", side_effect=error) as red,
                    patch.object(modulo, "perf_counter_ns", side_effect=[0, 3_000_000_000]),
                    verificador.assertLogs("uvicorn.error", level="ERROR"),
                ):
                    ok, _, datos = modulo._llamar_llm({"model": "modelo-ficticio"}, destino, "prueba")
                assert not ok and datos["http_status"] == status
                assert datos["rendimiento"]["tiempo_solicitud_segundos"] == 3
                assert datos["rendimiento"]["tokens_salida"] is None
                red.assert_called_once()
            with (
                patch.object(modulo, "urlopen", return_value=io.BytesIO(b"{json-invalido")),
                patch.object(modulo, "perf_counter_ns", side_effect=[0, 2_000_000_000]),
                verificador.assertLogs("uvicorn.error", level="ERROR"),
            ):
                ok, _, datos = modulo._llamar_llm({"model": "modelo-ficticio"}, destino, "prueba")
            assert not ok and datos["rendimiento"]["tiempo_solicitud_segundos"] == 2
        casos.append("Ambos transportes cronometran lectura completa, timeout, HTTP 429 y JSON inválido sin reintentos")

        consumo = {"entrada": 200, "salida": 100, "total": 300, "entrada_cache": None, "razonamiento": None}
        filtros = {"carrera": "Sistemas", "nivel_educativo": None, "institucion": None, "ubicacion": None, "modalidad": None}
        datos_filtros = {**filtros, "consumo_tokens": consumo, "rendimiento": qwen}
        datos_respuesta = {"respuesta": "Oferta ficticia", "consumo_tokens": consumo, "rendimiento": openai}
        with (
            patch.object(llmrag, "crea_prompt_pre_rag", return_value=(True, "ok", datos_filtros)) as normalizar,
            patch.object(llmrag, "buscar_ofertas", return_value=(True, "ok", {"ofertas": [], "cantidad": 0})) as rag,
            patch.object(llmrag, "genera_respuesta_usuario", return_value=(True, "ok", datos_respuesta)) as redactar,
            patch.object(llmrag, "guardar_respuesta_json", return_value=(True, "ok", "ficticio.json")) as guardar,
            patch.object(llmrag, "perf_counter_ns") as reloj,
        ):
            reloj.side_effect = [0, 0, 2_000_000_000, 2_000_000_000, 5_000_000_000, 5_000_000_000, 9_000_000_000, 9_000_000_000]
            respuesta = llmrag.armador(llmrag.SolicitudTitulos(pregunta="Sistemas"))
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 200
            assert list(cuerpo) == ["resultado", "pregunta", "mensaje", "rendimiento", "salida"]
            assert cuerpo["rendimiento"] == {
                "tiempo_total_segundos": 9,
                "tiempos_etapas_segundos": {"normalizacion": 2, "rag": 3, "respuesta_usuario": 4},
                "llamadas_llm": {"normalizacion": qwen, "respuesta_usuario": openai},
            }
            assert "rendimiento" not in cuerpo["salida"]
            assert datos_filtros["rendimiento"] == qwen and datos_respuesta["rendimiento"] == openai
            guardar.assert_called_once_with(cuerpo)
            rag.assert_called_once_with(filtros)

            normalizar.return_value = False, "Sin filtros", {**datos_filtros, "http_status": 404}
            reloj.side_effect = [0, 0, 2_000_000_000, 2_000_000_000]
            respuesta = llmrag.armador(llmrag.SolicitudTitulos(pregunta="otra"))
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 404
            assert cuerpo["rendimiento"]["tiempos_etapas_segundos"] == {"normalizacion": 2, "rag": None, "respuesta_usuario": None}
            assert cuerpo["rendimiento"]["llamadas_llm"] == {"normalizacion": qwen}

            normalizar.return_value = True, "ok", datos_filtros
            rag.side_effect = RuntimeError("RAG ficticio fallido")
            reloj.side_effect = [0, 0, 2_000_000_000, 2_000_000_000, 5_000_000_000, 5_000_000_000]
            with verificador.assertLogs("uvicorn.error", level="ERROR"):
                respuesta = llmrag.armador(llmrag.SolicitudTitulos(pregunta="Sistemas"))
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 500
            assert cuerpo["rendimiento"]["tiempo_total_segundos"] == 5
            assert cuerpo["rendimiento"]["tiempos_etapas_segundos"] == {"normalizacion": 2, "rag": 3, "respuesta_usuario": None}
            rag.side_effect = None
            redactar.return_value = False, "Truncada", {**datos_respuesta, "http_status": 502}
            reloj.side_effect = [0, 0, 2_000_000_000, 2_000_000_000, 5_000_000_000, 5_000_000_000, 9_000_000_000, 9_000_000_000]
            respuesta = llmrag.armador(llmrag.SolicitudTitulos(pregunta="Sistemas"))
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 502
            assert cuerpo["rendimiento"]["llamadas_llm"] == {"normalizacion": qwen, "respuesta_usuario": openai}
        casos.append("Router: tiempos por etapa, orden debajo de mensaje, guardado idéntico y métricas parciales en errores")
        return True, "ok", casos
    except Exception as e:
        logger.error("Error en comprobar_rendimiento: %s", e)
        return False, "Falló la verificación aislada de rendimiento", []


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    resultado, mensaje, casos = comprobar_rendimiento()
    print(json.dumps({"resultado": resultado, "mensaje": mensaje, "casos": casos}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
