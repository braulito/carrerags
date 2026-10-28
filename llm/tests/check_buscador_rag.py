"""Pruebas del código trasladado de consultador, sin archivos de secretos ni red."""

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from helpers import buscador_rag
from helpers.rag.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_REVISION
from helpers.rag.domain import HEADERS, digest
from helpers.rag.embeddings_http import DIMENSIONS, SPACE

logger = logging.getLogger(__name__)
VALORES = {
    "VECTORIAL": "http://qdrant.example:6333", "VECTORIAL_NAMESPACE": "carrerags",
    "EMBEDDING_URL": "http://embedding.example:8081", "HTTP_TIMEOUT": "20",
}
CONSULTA = {
    "carrera": "Profesorado", "nivel_educativo": "Grado", "institucion": "Institución ficticia",
    "ubicacion": "Quilmes", "modalidad": "distancia",
}


@dataclass
class FakeHttp:
    """Simula los contratos HTTP del servicio existente y de Qdrant."""

    timeout: float = 20.0
    last_http_status: int | None = None
    modo: str = "ok"
    fallo_ruta: str = ""
    fallo_http: int = 503
    requests: list[dict[str, Any]] = field(default_factory=list)

    def request(self: "FakeHttp", method: str, url: str, headers: dict[str, str],
                body: dict[str, Any] | None = None) -> tuple[bool, str, dict[str, Any]]:
        try:
            self.requests.append({"method": method, "url": url, "body": copy.deepcopy(body)})
            if self.fallo_ruta and url.endswith(self.fallo_ruta):
                self.last_http_status = self.fallo_http
                return False, f"HTTP {self.fallo_http}", {"http_status": self.fallo_http, "body": {}}
            if self.modo == "conexion":
                self.last_http_status = None
                return False, "Conexión fallida simulada", {"http_status": None, "body": {}}
            self.last_http_status = 200
            if url.endswith("/health"):
                contenido = {"resultado": True, "mensaje": "ok", "salida": {
                    "model": DEFAULT_EMBEDDING_MODEL, "revision": DEFAULT_EMBEDDING_REVISION,
                    "space": "incompatible" if self.modo == "espacio" else SPACE, "dimensions": DIMENSIONS,
                }}
            elif url.endswith("/embeddings"):
                assert method == "POST" and body is not None and len(body["texts"]) == 1
                vector = [1.0] + [0.0] * (DIMENSIONS - 1)
                if self.modo == "vector":
                    vector = [0.0] * DIMENSIONS
                contenido = {"resultado": True, "mensaje": "ok", "salida": {
                    "space": SPACE, "dimensions": DIMENSIONS, "vectors": [vector],
                }}
            elif url.endswith("/collections/carrerags"):
                ok, mensaje, huella = digest(SPACE)
                assert ok, mensaje
                contenido = {"status": "ok", "result": {"config": {"params": {"vectors": {
                    "v_" + huella[:24]: {"size": 12 if self.modo == "dimension" else DIMENSIONS},
                }}}}}
            else:
                assert method == "POST" and body is not None
                assert url.endswith(("/points/query", "/points/scroll"))
                puntos = []
                for identificador, titulo in [("historia", "Profesorado en Historia"),
                                               ("geografia", "Profesorado en Geografía"),
                                               ("abogacia", "Abogacía")]:
                    original = dict(zip(HEADERS, (
                        titulo, "Institución ficticia — Quilmes", "Grado", "Descripción de " + titulo,
                        "Online", "Pública", "https://example.org/" + identificador,
                    )))
                    payload = {"active": True, "eligible": False, "catalog_scope": "all_active_offers",
                               "title": titulo, "institution": "Institución ficticia", "location": "Quilmes",
                               "level": "Grado", "modality": "distancia", "original": original}
                    if self.modo == "original":
                        payload["original"] = {}
                    condiciones = body["filter"]["must"]
                    if all(payload.get(c["key"]) == c["match"]["value"] for c in condiciones):
                        puntos.append({"id": identificador, "score": 0.9, "payload": payload})
                if self.modo == "vacio":
                    puntos = []
                offset = None
                if url.endswith("/points/query"):
                    puntos = [p for p in puntos if p["id"] != "geografia"]
                elif self.modo in {"paginado", "cursor"}:
                    offset = "pagina2" if "offset" not in body or self.modo == "cursor" else None
                    puntos = puntos[:1] if "offset" not in body else puntos[1:]
                contenido = {"status": "ok", "result": {"points": puntos, "next_page_offset": offset}}
            return True, "ok", {"http_status": 200, "body": contenido}
        except Exception as e:
            logger.error("Error en FakeHttp.request: %s", e)
            return False, "Fallo en la simulación HTTP", {"http_status": 502, "body": {}}


def ejecutar_simulado(consulta: dict[str, Any], transporte: FakeHttp,
                     valores: dict[str, str]) -> tuple[bool, str, dict[str, Any]]:
    try:
        with (
            patch.object(buscador_rag, "load_dotenv"),
            patch.object(buscador_rag.os, "getenv", side_effect=valores.get),
            patch.object(buscador_rag, "HttpTransport", return_value=transporte) as fabrica,
        ):
            salida = buscador_rag.buscar_ofertas(consulta)
            if fabrica.called:
                assert fabrica.call_args.kwargs["timeout"] == float(valores.get("HTTP_TIMEOUT", "60"))
            return salida
    except Exception as e:
        logger.error("Error en ejecutar_simulado: %s", e)
        return False, "Falló la ejecución simulada", {}


def comprobar_buscador() -> tuple[bool, str, list[str]]:
    try:
        casos: list[str] = []
        transporte = FakeHttp(modo="paginado")
        ok, mensaje, salida = ejecutar_simulado(CONSULTA, transporte, VALORES)
        assert ok and mensaje == "ok", mensaje
        assert salida["cantidad"] == 2
        assert [p["original"]["Título"] for p in salida["ofertas"]] == ["Profesorado en Historia", "Profesorado en Geografía"]
        assert all(set(p["original"]) == set(HEADERS) for p in salida["ofertas"])
        assert transporte.requests[0]["url"].endswith("/health")
        assert transporte.requests[1]["body"]["texts"][0].startswith("Carrera: Profesorado")
        assert len(transporte.requests[3]["body"]["query"]) == DIMENSIONS
        must = transporte.requests[3]["body"]["filter"]["must"]
        assert {item["key"]: item["match"]["value"] for item in must} == {
            "active": True, "institution": "Institución ficticia", "location": "Quilmes",
            "level": "Grado", "modality": "distancia",
        }
        assert all(item["method"] in {"GET", "POST"} for item in transporte.requests)
        casos.append("Embeddings propios, vector compatible, filtros y rescate paginado del consultador")
        for consulta, cantidad in [({**CONSULTA, "carrera": None}, 3),
                                  ({**CONSULTA, "carrera": "Medicina"}, 0),
                                  ({**CONSULTA, "ubicacion": "Otra localidad"}, 0),
                                  ({**CONSULTA, "modalidad": "Modalidad inexistente"}, 0)]:
            ok, mensaje, salida = ejecutar_simulado(consulta, FakeHttp(), VALORES)
            assert salida["cantidad"] == cantidad
            assert ok if cantidad else not ok and salida["http_status"] == 404
        casos.append("Búsqueda solo por filtros y 404 sin relajar condiciones")
        for ruta, codigo in [("/health", 503), ("/embeddings", 500),
                             ("/collections/carrerags", 404), ("/points/query", 429),
                             ("/points/scroll", 503)]:
            ok, mensaje, salida = ejecutar_simulado(CONSULTA, FakeHttp(fallo_ruta=ruta, fallo_http=codigo), VALORES)
            assert not ok and salida["http_status"] == codigo, (ruta, mensaje, salida)
        casos.append("Conserva códigos HTTP de embeddings y Qdrant")
        for modo in ("espacio", "vector", "dimension", "cursor", "original", "conexion"):
            ok, mensaje, salida = ejecutar_simulado(CONSULTA, FakeHttp(modo=modo), VALORES)
            assert not ok and salida["http_status"] == 502, (modo, mensaje, salida)
        casos.append("Rechaza espacios, vectores, dimensiones, cursores y originales inválidos")
        for valores in [{}, {**VALORES, "HTTP_TIMEOUT": "0"}, {**VALORES, "EMBEDDING_URL": ""}]:
            transporte = FakeHttp()
            ok, mensaje, salida = ejecutar_simulado(CONSULTA, transporte, valores)
            assert not ok and salida["http_status"] == 500
            assert not transporte.requests
        alias = {**VALORES, "VECTORIAL_NAMESPACE": "", "VECOTRIAL_NAMESPACE": "carrerags"}
        ok, mensaje, salida = ejecutar_simulado(CONSULTA, FakeHttp(), alias)
        assert ok, mensaje
        casos.append("Valida configuración y admite el alias VECOTRIAL_NAMESPACE")
        for consulta in ({}, {**CONSULTA, "carrera": ["Profesorado"]}):
            transporte = FakeHttp()
            ok, mensaje, salida = ejecutar_simulado(consulta, transporte, VALORES)
            assert not ok and salida["http_status"] == 422 and not transporte.requests
        casos.append("Valida el contrato antes de consultar servicios")
        return True, "ok", casos
    except Exception as e:
        logger.error("Error en comprobar_buscador: %s", e)
        return False, "Falló la verificación del buscador RAG", []


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    resultado, mensaje, casos = comprobar_buscador()
    print(json.dumps({"resultado": resultado, "mensaje": mensaje, "casos": casos}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado else 1)
