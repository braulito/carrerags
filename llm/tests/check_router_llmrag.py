"""Verifica el adaptador HTTP sin cargar configuración ni contactar servicios."""

import json
import logging
import re
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from routers import llmrag
from helpers import respuesta_json

logger = logging.getLogger(__name__)


def comprobar_router() -> tuple[bool, str, list[str]]:
    """Comprueba la llamada al proveedor y la conservación de códigos HTTP."""
    try:
        solicitud = llmrag.SolicitudTitulos(pregunta="¿Dónde estudio Informática?")
        consumo = {"entrada": 100, "salida": 20, "total": 120, "entrada_cache": 0, "razonamiento": 0}
        datos = {
            "carrera": "Informática", "nivel_educativo": None, "institucion": None,
            "ubicacion": None, "modalidad": None, "consumo_tokens": consumo,
        }
        casos: list[str] = []
        assert any(ruta.path == "/llmrag/armador" and "POST" in ruta.methods for ruta in llmrag.router.routes)
        with (
            patch.object(llmrag, "crea_prompt_pre_rag") as proveedor,
            patch.object(llmrag, "buscar_ofertas") as rag,
            patch.object(llmrag, "genera_respuesta_usuario") as redactor,
            patch.object(llmrag, "guardar_respuesta_json", return_value=(True, "ok", "JSON/20261026-160802.json")) as guardar_json,
        ):
            consumo_respuesta = {"entrada": 50, "salida": 10, "total": 60, "entrada_cache": 40, "razonamiento": 2}
            consumo_total = {clave: consumo[clave] + consumo_respuesta[clave] for clave in consumo}
            detalle_consumos = {"normalizacion": consumo, "respuesta_usuario": consumo_respuesta}
            texto_usuario = "Podés estudiar Informática en la institución de la oferta."
            redactor.return_value = True, "ok", {"respuesta": texto_usuario, "consumo_tokens": consumo_respuesta}
            ofertas = {"ofertas": [{"original": {"Título": "Informática"}}], "cantidad": 1}
            rag.return_value = True, "ok", ofertas
            proveedor.return_value = True, "ok", datos
            respuesta = llmrag.armador(solicitud)
            proveedor.assert_called_once_with(solicitud.pregunta)
            assert respuesta.status_code == 200
            assert json.loads(respuesta.body) == {
                "resultado": True, "pregunta": solicitud.pregunta, "mensaje": "ok",
                "rendimiento": json.loads(respuesta.body)["rendimiento"], "salida": {
                    **datos, "respuesta": texto_usuario,
                    "consumo_tokens": consumo_total, "consumos_llm": detalle_consumos,
                },
            }
            rag.assert_called_once_with({campo: valor for campo, valor in datos.items() if campo != "consumo_tokens"})
            redactor.assert_called_once_with(solicitud.pregunta, ofertas["ofertas"])
            guardar_json.assert_called_once_with(json.loads(respuesta.body))
            assert list(json.loads(respuesta.body)) == ["resultado", "pregunta", "mensaje", "rendimiento", "salida"]
            casos.append("Normaliza, busca y redacta con consumos por llamada y total")
            consumo_qwen = {**consumo, "entrada_cache": None, "razonamiento": None}
            proveedor.return_value = True, "ok", {**datos, "consumo_tokens": consumo_qwen}
            respuesta = llmrag.armador(solicitud)
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 200
            assert cuerpo["salida"]["consumo_tokens"] == {
                **consumo_total, "entrada_cache": None, "razonamiento": None,
            }
            assert cuerpo["salida"]["consumos_llm"]["normalizacion"] == consumo_qwen
            redactor.return_value = False, "Respuesta truncada", {
                "http_status": 502, "consumo_tokens": {**consumo_respuesta, "entrada_cache": None, "razonamiento": None},
            }
            respuesta = llmrag.armador(solicitud)
            assert respuesta.status_code == 502
            assert json.loads(respuesta.body)["salida"]["consumo_tokens"]["razonamiento"] is None
            proveedor.return_value = True, "ok", datos
            redactor.return_value = True, "ok", {"respuesta": texto_usuario, "consumo_tokens": consumo_respuesta}
            casos.append("Desgloses desconocidos quedan null al sumar, también en respuestas fallidas")
            rag.reset_mock()
            redactor.reset_mock()
            sin_filtros = {clave: None for clave in datos if clave != "consumo_tokens"}
            sin_filtros["consumo_tokens"] = consumo
            proveedor.return_value = (
                False,
                "No se identificaron criterios de búsqueda en la pregunta",
                {**sin_filtros, "http_status": 404},
            )
            respuesta = llmrag.armador(llmrag.SolicitudTitulos(pregunta="qué hora es"))
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 404 and cuerpo["resultado"] is False
            assert cuerpo["mensaje"] == "No se identificaron criterios de búsqueda en la pregunta"
            assert cuerpo["salida"] == {**sin_filtros, "http_status": 404, "consumos_llm": {"normalizacion": consumo}}
            assert cuerpo["pregunta"] == "qué hora es"
            assert guardar_json.call_args.args[0] == cuerpo
            rag.assert_not_called()
            redactor.assert_not_called()
            casos.append("Propaga el 404 del helper conservando filtros y consumos")
            for campo in ("carrera", "nivel_educativo", "institucion", "ubicacion", "modalidad"):
                proveedor.return_value = True, "ok", {**sin_filtros, campo: "valor de prueba"}
                assert llmrag.armador(solicitud).status_code == 200
            casos.append("Cualquier filtro identificado permite continuar con HTTP 200")
            redactor.reset_mock()
            proveedor.return_value = True, "ok", datos
            for codigo in (404, 503):
                rag.return_value = False, "Fallo simulado del RAG", {"http_status": codigo, "ofertas": [], "cantidad": 0}
                respuesta = llmrag.armador(solicitud)
                assert respuesta.status_code == codigo
                assert json.loads(respuesta.body)["salida"]["consumo_tokens"] == consumo
                assert not {"ofertas", "cantidad"} & set(json.loads(respuesta.body)["salida"])
            casos.append("Propaga errores del RAG conservando consumos de la LLM")
            redactor.assert_not_called()
            rag.return_value = True, "ok", ofertas
            redactor.return_value = False, "Respuesta incompleta", {"http_status": 502, "consumo_tokens": consumo_respuesta}
            respuesta = llmrag.armador(solicitud)
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 502 and cuerpo["resultado"] is False
            assert not {"ofertas", "cantidad"} & set(cuerpo["salida"])
            assert cuerpo["salida"]["consumo_tokens"] == consumo_total
            assert cuerpo["salida"]["consumos_llm"] == detalle_consumos
            redactor.return_value = False, "Conexión fallida", {"http_status": 502}
            respuesta = llmrag.armador(solicitud)
            assert json.loads(respuesta.body)["salida"]["consumo_tokens"] == consumo
            casos.append("Fallo de redacción conserva consumos sin publicar ofertas ni cantidad")
            redactor.side_effect = RuntimeError("fallo inesperado de redacción")
            with TestCase().assertLogs(llmrag.logger, level="ERROR"):
                respuesta = llmrag.armador(solicitud)
            cuerpo = json.loads(respuesta.body)
            assert respuesta.status_code == 500
            assert not {"ofertas", "cantidad"} & set(cuerpo["salida"])
            assert cuerpo["salida"]["consumo_tokens"] == consumo
            redactor.side_effect = None
            redactor.reset_mock()
            rag.reset_mock()
            for codigo in (401, 422, 429, 500, 502):
                proveedor.return_value = False, "Error simulado", {"http_status": codigo, "consumo_tokens": consumo}
                respuesta = llmrag.armador(solicitud)
                assert respuesta.status_code == codigo
                assert json.loads(respuesta.body)["salida"]["consumo_tokens"] == consumo
            casos.append("Conserva HTTP 401, 422, 429, 500 y 502 y consumos de errores")
            rag.assert_not_called()
            redactor.assert_not_called()
            proveedor.return_value = False, "Error simulado", {"http_status": 200}
            assert llmrag.armador(solicitud).status_code == 500
            casos.append("No transforma un fallo en HTTP 200")
            proveedor.side_effect = RuntimeError("fallo simulado")
            with TestCase().assertLogs(llmrag.logger, level="ERROR") as registros:
                respuesta = llmrag.armador(solicitud)
            assert respuesta.status_code == 500
            assert json.loads(respuesta.body)["resultado"] is False
            assert "fallo simulado" in "\n".join(registros.output)
            assert guardar_json.call_args.args[0] == json.loads(respuesta.body)
            casos.append("Excepción inesperada registrada y devuelta como HTTP 500")
        with tempfile.TemporaryDirectory() as carpeta:
            cuerpo = {
                "resultado": True, "pregunta": "¿Qué puedo estudiar?", "mensaje": "ok",
                "rendimiento": {
                    "tiempo_total_segundos": 2.5,
                    "tiempos_etapas_segundos": {"normalizacion": 2.5, "rag": None, "respuesta_usuario": None},
                    "llamadas_llm": {},
                },
                "salida": {"respuesta": "Primera línea\n\nSegunda línea", "consumo_tokens": consumo},
            }
            with patch.object(respuesta_json, "DIRECTORIO_JSON", Path(carpeta)):
                ok, mensaje, archivo = respuesta_json.guardar_respuesta_json(cuerpo)
            assert ok and mensaje == "ok"
            assert re.fullmatch(r"\d{8}-\d{6}\.json", Path(archivo).name)
            assert json.loads(Path(archivo).read_text(encoding="utf-8")) == cuerpo
            assert list(json.loads(Path(archivo).read_text(encoding="utf-8"))) == list(cuerpo)
        casos.append("Guarda el JSON completo en UTF-8 con el nombre y el orden solicitados")
        return True, "ok", casos
    except Exception as e:
        logger.error("Error en comprobar_router: %s", e)
        return False, "Falló la verificación aislada del router", []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    resultado, mensaje, casos = comprobar_router()
    print(json.dumps({"resultado": resultado, "mensaje": mensaje, "casos": casos}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
