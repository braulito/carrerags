"""Cliente remoto y carga dotenv simulada: nunca abre un .env real."""

from __future__ import annotations

import ast
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import run
import run_e
from carrerags_ingesta.adapters.embeddings_http import DIMENSIONS, SPACE
from carrerags_ingesta.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_REVISION
from carrerags_ingesta.domain import HEADERS, digest

logger = logging.getLogger(__name__)
VALORES = {"VECTORIAL": "http://qdrant.example:6333", "VECTORIAL_NAMESPACE": "carrerags",
           "EMBEDDING_URL": "http://embedding.example:8081", "HTTP_TIMEOUT": "20"}
ORIGINAL = dict(zip(HEADERS, (
    "Profesorado en Historia", "Institución ficticia — Argentina", "Grado",
    "Formación docente en historia.", "Online", "Pública", "https://example.org/historia",
)))


@dataclass
class FakeHttp:
    requests: list[dict[str, Any]] = field(default_factory=list)
    embedding_status: int = 200
    qdrant_status: int = 200
    incompatible: bool = False
    invalid_vector: bool = False
    logical_failure: bool = False
    empty: bool = False

    def request(self: FakeHttp, method: str, url: str, headers: dict[str, str],
                body: dict[str, Any] | None = None) -> tuple[bool, str, dict[str, Any]]:
        try:
            self.requests.append({"method": method, "url": url, "body": body})
            embedding = url.startswith(VALORES["EMBEDDING_URL"])
            status = self.embedding_status if embedding else self.qdrant_status
            if status != 200:
                return False, "La API respondió con HTTP " + str(status), {"http_status": status, "body": {}}
            if url.endswith("/health"):
                assert method == "GET"
                content = {"resultado": True, "mensaje": "ok", "salida": {
                    "model": DEFAULT_EMBEDDING_MODEL, "revision": DEFAULT_EMBEDDING_REVISION,
                    "dimensions": DIMENSIONS, "space": "incorrecto" if self.incompatible else SPACE}}
            elif url.endswith("/embeddings"):
                assert method == "POST" and body is not None
                vector = [0.0] * DIMENSIONS if self.invalid_vector else [1.0] + [0.0] * (DIMENSIONS - 1)
                content = {"resultado": not self.logical_failure, "mensaje": "ok", "salida": {
                    "space": SPACE, "dimensions": DIMENSIONS, "vectors": [vector for _ in body["texts"]]}}
            elif method == "GET" and url.endswith("/collections/carrerags"):
                ok, mensaje, huella = digest(SPACE)
                if not ok:
                    return False, mensaje, {}
                content = {"status": "ok", "result": {"config": {"params": {
                    "vectors": {"v_" + huella[:24]: {"size": DIMENSIONS}}}}}}
            else:
                assert method == "POST" and url.endswith(("/points/query", "/points/scroll"))
                payload = {"active": True, "eligible": False, "catalog_scope": "all_active_offers",
                           "modality": "distancia", "management": "Pública", "admission": "desconocido",
                           "independent_entry": True, "original": ORIGINAL}
                content = {"status": "ok", "result": {"points": [] if self.empty else [
                    {"id": "oferta-ficticia", "score": 0.9, "payload": payload}], "next_page_offset": None}}
            return True, "ok", {"http_status": 200, "body": content}
        except Exception as e:
            logger.error("Error en FakeHttp.request: %s", e)
            return False, "Fallo del transporte ficticio", {}


def preparar_pregunta(base_dir: Path, contenido: str = "") -> tuple[bool, str, str]:
    try:
        texto = contenido or json.dumps({"PREGUNTA": "¿Dónde puedo estudiar profesorado?", "LIMITE": 100}, ensure_ascii=False)
        (base_dir / "local_pregunta.json").write_text(texto, encoding="utf-8")
        return True, "ok", texto
    except Exception as e:
        logger.error("Error en preparar_pregunta: %s", e)
        return False, "No se pudo preparar la pregunta ficticia", ""


def check_run_e_configuracion() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            ok, mensaje, _ = preparar_pregunta(base_dir)
            assert ok, mensaje
            modulo = ModuleType("dotenv")
            parser = MagicMock(return_value={**VALORES, "IGNORADA": "ficticio", "EMBEDDING_PROVIDER": "local"})
            modulo.dotenv_values = parser
            with patch.dict("sys.modules", {"dotenv": modulo}):
                ok, mensaje, config = run_e.leer_configuracion(base_dir)
            assert ok and mensaje == "ok", mensaje
            parser.assert_called_once_with(dotenv_path=base_dir / ".env", encoding="utf-8-sig", interpolate=False)
            assert config["pregunta"] == "¿Dónde puedo estudiar profesorado?" and config["limite"] == 100
            settings = config["settings"]
            assert settings.embedding_provider == "http" and settings.embedding_url == VALORES["EMBEDDING_URL"]
            assert settings.vectorial == VALORES["VECTORIAL"] and settings.timeout == 20
            with patch.object(run_e, "leer_variables", side_effect=AssertionError("No cargar configuración real")) as loader:
                ok, mensaje, config = run_e.leer_configuracion(base_dir, VALORES)
                assert ok, mensaje
                loader.assert_not_called()
            with patch.dict("sys.modules", {"dotenv": None}):
                ok, mensaje, config = run_e.leer_configuracion(base_dir)
                assert not ok and config == {} and "reqs_e.txt" in mensaje
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_run_e_configuracion: %s", e)
        return False, "Falló la configuración remota simulada: " + str(e), {}


def check_run_e_consulta() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            ok, mensaje, _ = preparar_pregunta(base_dir)
            assert ok, mensaje
            (base_dir / "respuesta.json").write_text('["conservar"]', encoding="utf-8")
            transporte = FakeHttp()
            with patch.object(run, "HttpTransport", return_value=transporte), \
                 patch("carrerags_ingesta.adapters.embeddings_http.HttpTransport", return_value=transporte), \
                 patch("carrerags_ingesta.adapters.local.create", side_effect=AssertionError("No usar modelo local")), \
                 patch.object(run_e, "leer_variables", side_effect=AssertionError("No cargar configuración real")):
                ok, mensaje, salida = run_e.ejecutar(base_dir, VALORES)
            assert ok and mensaje == "ok", mensaje
            destino = base_dir / "salidas/local/Dónde puedo estudiar profesorado.json"
            assert salida == {"archivo": str(destino), "cantidad": 1}
            assert json.loads(destino.read_text(encoding="utf-8")) == [{"original": ORIGINAL}]
            assert json.loads((base_dir / "respuesta.json").read_text(encoding="utf-8")) == ["conservar"]
            assert len(transporte.requests) == 5
            assert transporte.requests[0]["url"].endswith("/health")
            assert transporte.requests[1]["body"] == {"texts": ["¿Dónde puedo estudiar profesorado?"]}
            assert len(transporte.requests[3]["body"]["query"]) == 384
            assert transporte.requests[3]["body"]["filter"] == {"must": [{"key": "active", "match": {"value": True}}]}
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_run_e_consulta: %s", e)
        return False, "Falló la consulta HTTP de run_e.py: " + str(e), {}


def check_run_e_fallos() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            ok, mensaje, _ = preparar_pregunta(base_dir)
            assert ok, mensaje
            destino = base_dir / "salidas/local/Dónde puedo estudiar profesorado.json"
            destino.parent.mkdir(parents=True)
            for transporte in [FakeHttp(embedding_status=503), FakeHttp(qdrant_status=404),
                               FakeHttp(incompatible=True), FakeHttp(invalid_vector=True),
                               FakeHttp(logical_failure=True), FakeHttp(empty=True)]:
                destino.write_text('["resultado anterior"]', encoding="utf-8")
                with patch.object(run, "HttpTransport", return_value=transporte), \
                     patch("carrerags_ingesta.adapters.embeddings_http.HttpTransport", return_value=transporte):
                    ok, mensaje, salida = run_e.ejecutar(base_dir, VALORES)
                if transporte.empty:
                    assert ok and salida["cantidad"] == 0, mensaje
                    assert json.loads(destino.read_text(encoding="utf-8")) == []
                else:
                    assert not ok and salida == {} and mensaje != "ok"
                    assert json.loads(destino.read_text(encoding="utf-8")) == ["resultado anterior"]
                    if transporte.embedding_status != 200:
                        assert "503" in mensaje and "EMBEDDING_URL" in mensaje
                    if transporte.qdrant_status != 200:
                        assert "404" in mensaje and "VECTORIAL" in mensaje
            with patch.object(run.os, "replace", side_effect=OSError("Fallo simulado")):
                ok, mensaje, salida = run.guardar_respuesta(base_dir, [], "local_salida.json")
                assert not ok and salida == "" and mensaje != "ok"
                assert not list(base_dir.glob("*.tmp"))
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_run_e_fallos: %s", e)
        return False, "Falló la propagación de errores del cliente remoto: " + str(e), {}


def check_run_e_entradas() -> tuple[bool, str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            for texto in ['[]', '{JSON inválido', '{"PREGUNTA":""}', '{"PREGUNTA":"turismo","LIMITE":true}',
                          '{"PREGUNTA":"turismo","LIMITE":101}', 'raise RuntimeError("no ejecutar")']:
                ok, mensaje, _ = preparar_pregunta(base_dir, texto)
                assert ok, mensaje
                with patch.object(run, "create_embeddings") as factory:
                    ok, mensaje, salida = run_e.ejecutar(base_dir, VALORES)
                assert not ok and salida == {} and mensaje != "ok"
                factory.assert_not_called()
            ok, mensaje, _ = preparar_pregunta(base_dir)
            assert ok, mensaje
            for valores in [{}, {**VALORES, "VECTORIAL": ""}, {**VALORES, "EMBEDDING_URL": ""},
                            {**VALORES, "EMBEDDING_URL": "http://embedding.example:8081/embeddings"},
                            {**VALORES, "HTTP_TIMEOUT": "0"}]:
                ok, mensaje, salida = run_e.leer_configuracion(base_dir, valores)
                assert not ok and salida == {} and mensaje != "ok"
            for ruta in [Path(run.__file__), Path(run_e.__file__)]:
                arbol = ast.parse(ruta.read_text(encoding="utf-8"))
                for nodo in ast.walk(arbol):
                    if isinstance(nodo, ast.FunctionDef):
                        assert nodo.returns is not None and ast.unparse(nodo.returns).startswith("tuple[bool, str,")
                        assert all(arg.annotation is not None for arg in nodo.args.args)
                    if isinstance(nodo, ast.ExceptHandler):
                        assert nodo.name == "e"
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_run_e_entradas: %s", e)
        return False, "Falló la validación de las entradas de run_e.py: " + str(e), {}


def check_run_e_nombres_y_reemplazo() -> tuple[bool, str, dict[str, Any]]:
    try:
        casos = [
            ("¿qué puedo estudiar en Quilmes?", "qué puedo estudiar en Quilmes.json"),
            ("Ingeniería en Informática", "Ingeniería en Informática.json"),
            ('turismo: online/virtual?', "turismo onlinevirtual.json"),
            ("CON", "_CON.json"), ("NUL.oferta", "_NUL.oferta.json"),
            ("???", "consulta.json"), ("../afuera", "afuera.json"),
        ]
        for pregunta, esperado in casos:
            ok, mensaje, nombre = run_e.nombre_archivo(pregunta)
            assert ok and nombre == esperado, (pregunta, mensaje, nombre)
        ok, mensaje, largo = run_e.nombre_archivo("Ingeniería " * 100)
        assert ok and len(largo.encode("utf-16-le")) <= 190, mensaje
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            nombre = "salidas/local/Ingeniería.json"
            ok, mensaje, _ = run.guardar_respuesta(base, [{"original": ORIGINAL}], nombre)
            assert ok, mensaje
            ok, mensaje, _ = run.guardar_respuesta(base, [], nombre)
            assert ok and json.loads((base / nombre).read_text(encoding="utf-8")) == [], mensaje
            assert not list((base / "salidas/local").glob("*.tmp"))
            for inseguro in ["../afuera.json", "salidas/local/../afuera.json", "otra.json"]:
                ok, mensaje, salida = run.guardar_respuesta(base, [], inseguro)
                assert not ok and salida == "", inseguro
        return True, "ok", {"nombres": len(casos)}
    except Exception as e:
        logger.error("Error en check_run_e_nombres_y_reemplazo: %s", e)
        return False, "Falló el nombre o reemplazo de la salida: " + str(e), {}
