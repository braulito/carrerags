"""Pruebas aisladas: python -I -S -X utf8 embedding/tests/run_tests.py.

Solo biblioteca estándar; modelo doble y servidor efímero en loopback.
"""

from __future__ import annotations

import ast
import copy
import json
import logging
import sys
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

COMPONENT = Path(__file__).resolve().parents[1]
ROOT = COMPONENT.parent
sys.path.insert(0, str(COMPONENT))
sys.path.insert(0, str(ROOT / "ingesta"))
sys.path.insert(0, str(ROOT / "consultador"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carrerags_embeddings.constants import DIMENSIONS, MAX_BODY_BYTES, MODEL_ID, REVISION, SPACE
from carrerags_embeddings.model import Embeddings, load_model
from carrerags_embeddings.server import Handler, main, validate_texts
from carrerags_ingesta.adapters.embeddings_http import HttpEmbeddings, create
from carrerags_ingesta.adapters.http import HttpTransport
from carrerags_ingesta.config import Settings, read_settings
from carrerags_ingesta.registry import create_adapter
from download_model import download

logger = logging.getLogger(__name__)


def ordered_vectors(texts: list[str]) -> tuple[bool, str, list[list[float]]]:
    try:
        vectors = []
        for text in texts:
            vector = [0.0] * DIMENSIONS
            vector[int(text) % DIMENSIONS] = 1.0
            vectors.append(vector)
        return True, "ok", vectors
    except Exception as e:
        logger.error("Error en ordered_vectors: %s", e)
        return False, "No se pudo generar el doble de vectores", []


def check_model_loading() -> tuple[bool, str, dict[str, Any]]:
    try:
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = {"model": MODEL_ID, "revision": REVISION, "space": SPACE, "dimensions": DIMENSIONS}
            (directory / "carrerags-model.json").write_text(json.dumps(manifest), encoding="utf-8")
            (directory / "model.safetensors").write_bytes(b"fake weights")
            sentence_module = ModuleType("sentence_transformers")
            model = MagicMock()
            model.get_sentence_embedding_dimension.return_value = DIMENSIONS
            model.encode.return_value.tolist.return_value = [[1.0] + [0.0] * (DIMENSIONS - 1)]
            constructor = MagicMock(return_value=model)
            sentence_module.SentenceTransformer = constructor
            torch_module = ModuleType("torch")
            torch_module.set_num_threads = MagicMock()
            torch_module.set_num_interop_threads = MagicMock()
            with patch.dict(sys.modules, {"torch": torch_module, "sentence_transformers": sentence_module}), \
                 patch("socket.create_connection", side_effect=AssertionError("Prohibida red externa")):
                ok, message, engine = load_model(directory)
                assert ok and engine is not None, message
                assert engine.encode(["uno"])[0] and engine.encode(["dos"])[0]
                constructor.assert_called_once()
                assert constructor.call_args.args == (str(directory.resolve()),)
                assert constructor.call_args.kwargs == {"device": "cpu", "local_files_only": True,
                    "token": False, "trust_remote_code": False, "model_kwargs": {"use_safetensors": True}}
                assert model.encode.call_args.kwargs["normalize_embeddings"] is True
                assert model.encode.call_args.kwargs["batch_size"] == 16
                assert model.encode.call_count == 2
                # Los datos inválidos del backend nunca llegan como éxito al cliente.
                for vector in [[0.0] * DIMENSIONS, [2.0] * DIMENSIONS,
                               [float("nan")] * DIMENSIONS, [True] * DIMENSIONS, [1.0]]:
                    model.encode.return_value.tolist.return_value = [vector]
                    assert engine.encode(["uno"])[0] is False
                model.encode.return_value.tolist.return_value = []
                assert not engine.encode(["uno"])[0]
                manifest["revision"] = "incompatible"
                (directory / "carrerags-model.json").write_text(json.dumps(manifest), encoding="utf-8")
                assert load_model(directory) == (False, "No se pudo cargar el modelo local; reconstruir la imagen", None)
                constructor.assert_called_once()
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_model_loading: %s", e)
        return False, "Falló carga local única, identidad o normalización: " + str(e), {}


def check_build_download() -> tuple[bool, str, dict[str, Any]]:
    try:
        module = ModuleType("huggingface_hub")
        module.snapshot_download = MagicMock()
        engine = MagicMock()
        engine.encode.return_value = (True, "ok", [[1.0] * DIMENSIONS])
        with TemporaryDirectory() as temporary, patch.dict(sys.modules, {"huggingface_hub": module}), \
             patch("carrerags_embeddings.model.load_model", return_value=(True, "ok", engine)):
            destination = Path(temporary)
            ok, message, output = download(destination)
            assert ok and output == str(destination), message
            kwargs = module.snapshot_download.call_args.kwargs
            assert kwargs["repo_id"] == MODEL_ID and kwargs["revision"] == REVISION
            assert kwargs["token"] is False and "model.safetensors" in kwargs["allow_patterns"]
            assert json.loads((destination / "carrerags-model.json").read_text())["space"] == SPACE
        with patch.dict(sys.modules, {"huggingface_hub": module}):
            module.snapshot_download.side_effect = OSError("Fallo de descarga simulado")
            assert download(Path("unused")) == (False, "No se pudo preparar el modelo fijado", "")
        with patch("carrerags_embeddings.server.load_model", return_value=(False, "No hay pesos", None)), \
             patch("carrerags_embeddings.server.ThreadingHTTPServer") as server:
            assert main() == (False, "No hay pesos", None)
            server.assert_not_called()
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_build_download: %s", e)
        return False, "Falló la descarga fijada o el cierre del arranque: " + str(e), {}


def check_validation() -> tuple[bool, str, dict[str, Any]]:
    try:
        for payload in [None, [], {"texts": []}, {"texts": "hola"}, {"texts": ["  "]},
                        {"texts": [None]}, {"texts": [1]}, {"texts": ["x"] * 129},
                        {"texts": ["x" * 16001]}, {"texts": ["x" * 16000] * 16},
                        {"texts": ["hola"], "extra": True}]:
            ok, message, data = validate_texts(payload)
            assert not ok and message != "ok" and data == []
        texts = ["  Texto sin modificar  ", "日本語", "Español", "Español"]
        assert validate_texts({"texts": texts}) == (True, "ok", texts)
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_validation: %s", e)
        return False, "Falló la validación de entrada: " + str(e), {}


def request(port: int, method: str, route: str, body: bytes | None = None,
            headers: dict[str, str] | None = None, omit_length: bool = False) -> tuple[bool, str, dict[str, Any]]:
    connection: HTTPConnection | None = None
    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=3)
        if omit_length:
            connection.putrequest(method, route)
            for name, value in (headers or {}).items():
                connection.putheader(name, value)
            connection.endheaders()
        else:
            connection.request(method, route, body=body, headers=headers or {})
        response = connection.getresponse()
        data = {"http_status": response.status, "body": json.loads(response.read())}
        return True, "ok", data
    except Exception as e:
        logger.error("Error en request: %s", e)
        return False, "Falló la llamada de prueba", {}
    finally:
        if connection is not None:
            connection.close()


def check_http_integration() -> tuple[bool, str, dict[str, Any]]:
    server: ThreadingHTTPServer | None = None
    thread: Thread | None = None
    try:
        model = MagicMock()
        engine = Embeddings(model)
        with patch.object(engine, "encode", side_effect=ordered_vectors), patch.object(Handler, "engine", engine):
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            port = server.server_port
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            address = f"http://127.0.0.1:{port}"
            settings = Settings(embedding_provider="http", embedding_url=address)
            ok, message, client = create_adapter("embedding", "http", settings)
            assert ok and client is not None and client.space == SPACE, message
            texts = [str(i) for i in range(38)]
            ok, message, vectors = client.embed(texts)
            assert ok and vectors == ordered_vectors(texts)[2], message
            assert engine.encode.call_count == 3
            assert [len(call.args[0]) for call in engine.encode.call_args_list] == [15, 15, 8]
            assert client.embed([]) == (True, "ok", [])
            assert not client.embed([" "])[0]
            ok, _, response = request(port, "POST", "/embeddings", json.dumps({"texts": ["2", "0", "2"]}).encode(), {"Content-Type": "application/json"})
            assert ok and response["http_status"] == 200
            assert response["body"]["salida"]["vectors"] == ordered_vectors(["2", "0", "2"])[2]
            cases = [("PUT", "/embeddings", None, {}, 405), ("GET", "/absent", None, {}, 404), ("GET", "/embeddings", None, {}, 405),
                     ("POST", "/health", None, {}, 405), ("POST", "/embeddings", b"{}", {}, 415),
                     ("POST", "/embeddings", b"broken", {"Content-Type": "application/json"}, 400),
                     ("POST", "/embeddings", b'{"texts": []}', {"Content-Type": "application/json"}, 422),
                     ("POST", "/embeddings", b"", {"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)}, 413),
                     ("POST", "/embeddings", b"", {"Content-Type": "application/json", "Content-Length": "-1"}, 400),
                     ("POST", "/embeddings", b"", {"Content-Type": "application/json", "Transfer-Encoding": "chunked"}, 400)]
            for method, route, body, headers, status in cases:
                ok, message, response = request(port, method, route, body, headers)
                assert ok and response["http_status"] == status, (status, response, message)
                assert response["body"]["resultado"] is False and response["body"]["salida"] == {}
            assert request(port, "POST", "/embeddings", headers={"Content-Type": "application/json"}, omit_length=True)[2]["http_status"] == 411
            engine.lock.acquire()
            try:
                ok, message, data = client.embed(["1"])
                assert not ok and "503" in message and data == []
            finally:
                engine.lock.release()
            with patch.object(engine, "encode", return_value=(False, "Fallo simulado", [])):
                ok, message, data = client.embed(["1"])
                assert not ok and "500" in message and data == []
            with patch.object(Handler, "engine", None):
                assert request(port, "GET", "/health")[2]["http_status"] == 503
                assert not create(settings)[0]
        return True, "ok", {"texts": 38, "batches": 3}
    except Exception as e:
        logger.error("Error en check_http_integration: %s", e)
        return False, "Falló HTTP, lotes, orden o estados: " + str(e), {}
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=3)


def check_client_rejections() -> tuple[bool, str, dict[str, Any]]:
    try:
        transport = MagicMock()
        health = {"resultado": True, "mensaje": "ok", "salida": {
            "model": MODEL_ID, "revision": REVISION, "space": SPACE, "dimensions": DIMENSIONS}}
        with patch("carrerags_ingesta.adapters.embeddings_http.HttpTransport", return_value=transport):
            transport.request.return_value = (True, "ok", {"body": health, "http_status": 200})
            assert create(Settings())[0]
            assert transport.request.call_args.args[1] == "http://macmini:8081/health"
            for changes in [{"embedding_model": "other"}, {"embedding_revision": "other"},
                            {"dimensions": 2}, {"embedding_url": "http://user:fake@server"},
                            {"embedding_url": "https://server/path"}, {"embedding_url": "file:///local"}]:
                assert not create(Settings(**changes))[0]
            for field in ["space", "dimensions", "revision", "model"]:
                invalid = copy.deepcopy(health)
                invalid["salida"][field] = "incompatible"
                transport.request.return_value = (True, "ok", {"body": invalid})
                assert not create(Settings())[0]
        client = HttpEmbeddings("http://fake.invalid", transport)
        valid = {"resultado": True, "mensaje": "ok", "salida": {
            "space": SPACE, "dimensions": DIMENSIONS, "vectors": [[1.0] + [0.0] * 383]}}
        invalid_bodies = [{**valid, "resultado": False}, {**valid, "salida": []}]
        for field, value in [("space", "other"), ("dimensions", 2), ("vectors", []),
                             ("vectors", [[float("nan")] * DIMENSIONS]),
                             ("vectors", [[0.0] * DIMENSIONS]), ("vectors", [[True] * DIMENSIONS])]:
            invalid = copy.deepcopy(valid)
            invalid["salida"][field] = value
            invalid_bodies.append(invalid)
        for invalid in invalid_bodies:
            transport.request.return_value = (True, "ok", {"body": invalid})
            assert client.embed(["1"])[0] is False
        transport.request.side_effect = [(True, "ok", {"body": {**valid, "salida": {
            **valid["salida"], "vectors": valid["salida"]["vectors"] * 15}}}),
            (False, "La API respondió con HTTP 503", {"http_status": 503, "body": {}})]
        assert client.embed(["1"] * 16) == (False, "La API respondió con HTTP 503", [])
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_client_rejections: %s", e)
        return False, "Falló rechazo de respuestas incompatibles o fallos parciales: " + str(e), {}


def check_consumers() -> tuple[bool, str, dict[str, Any]]:
    try:
        import run
        from carrerags_ingesta.bootstrap import RUNTIME_KEYS

        assert "EMBEDDING_URL" in RUNTIME_KEYS
        ok, message, settings = read_settings({"EMBEDDING_PROVIDER": "http", "EMBEDDING_URL": "http://macmini:8081"})
        assert ok and settings.embedding_url == "http://macmini:8081", message
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "config.json").write_text(json.dumps({"PREGUNTA": "profesorados",
                "VECTORIAL": "http://qdrant.invalid", "EMBEDDING_PROVIDER": "http",
                "EMBEDDING_URL": "http://macmini:8081"}), encoding="utf-8")
            ok, message, config = run.leer_configuracion(directory)
            assert ok and config["settings"].embedding_provider == "http", message
            with patch.object(run, "create_adapter", return_value=(False, "HTTP 503", None)) as factory:
                assert run.create_embeddings(config["settings"]) == (False, "HTTP 503", None)
                assert factory.call_args.args[:2] == ("embedding", "http")
            with patch.object(run, "create_embeddings", return_value=(False, "HTTP 503", None)), \
                 patch.object(run, "QdrantStore") as store:
                assert run.ejecutar(directory) == (False, "HTTP 503", {})
                store.assert_not_called()
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_consumers: %s", e)
        return False, "Falló integración con ingesta/consultador: " + str(e), {}


def check_published_port_verification() -> tuple[bool, str, dict[str, Any]]:
    try:
        import verify_ports

        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({"resultado": True, "salida": {"dimensions": 384}}).encode()
        published = json.dumps({"8081/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8081"}]})
        for ports, expected in [(json.dumps({"8081/tcp": None}), False), (published, True)]:
            with patch.object(verify_ports, "docker_command", side_effect=[(True, "ok", "ficticio"),
                                                                           (True, "ok", ports)]), \
                 patch.object(verify_ports, "HTTPConnection", return_value=connection) as constructor:
                ok, message, data = verify_ports.verify()
            assert ok is expected, message
            if expected:
                assert data == {"published_port": 8081, "health": True}
            else:
                assert data == {} and "no publicado" in message
                constructor.assert_not_called()
        response.status = 502
        with patch.object(verify_ports, "docker_command", side_effect=[(True, "ok", "ficticio"),
                                                                       (True, "ok", published)]), \
             patch.object(verify_ports, "HTTPConnection", return_value=connection):
            ok, message, data = verify_ports.verify()
            assert not ok and data == {} and "HTTP 200" in message
        process = MagicMock(returncode=0, stdout="ficticio\n")
        with patch.object(verify_ports.subprocess, "run", return_value=process) as execute:
            assert verify_ports.docker_command(["compose", "ps", "-q", "gateway"]) == (True, "ok", "ficticio")
            assert execute.call_args.kwargs["env"]["COMPOSE_DISABLE_ENV_FILE"] == "1"
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_published_port_verification: %s", e)
        return False, "Falló la detección de puertos no publicados: " + str(e), {}


def check_contracts() -> tuple[bool, str, dict[str, Any]]:
    try:
        paths = [*COMPONENT.glob("*.py"), *(COMPONENT / "carrerags_embeddings").glob("*.py"),
                 *(COMPONENT / "tests").glob("*.py"), ROOT / "ingesta/carrerags_ingesta/adapters/embeddings_http.py"]
        for file in paths:
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.returns is not None and ast.unparse(node.returns).startswith("tuple[bool, str,"), (file, node.name)
                    assert all(a.annotation for a in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]), node.name
                    assert any(isinstance(s, ast.Try) for s in node.body), node.name
                if isinstance(node, ast.ExceptHandler):
                    assert node.name == "e", (file, "Excepción sin capturar como e")
        from carrerags_ingesta.adapters.local import create as local_create
        fake_module = ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = MagicMock()
        fake_module.SentenceTransformer.return_value.get_sentence_embedding_dimension.return_value = DIMENSIONS
        with patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            ok, message, local = local_create(Settings())
            assert ok and local.space == SPACE, message
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_contracts: %s", e)
        return False, "Falló contrato de funciones o compatibilidad de espacio: " + str(e), {}


def run_suite() -> tuple[bool, str, dict[str, int]]:
    try:
        checks = [check_model_loading, check_build_download, check_validation, check_http_integration,
                  check_client_rejections, check_consumers, check_published_port_verification, check_contracts]
        from check_install import check_installer
        checks.append(check_installer)
        failures = []
        for check in checks:
            ok, message, data = check()
            print(("PASS " if ok else "FAIL ") + check.__name__ + (" " + str(data) if data else ""))
            if not ok:
                failures.append(message)
        return not failures, "; ".join(failures) if failures else "ok", {"passed": len(checks) - len(failures), "failed": len(failures)}
    except Exception as e:
        logger.error("Error en run_suite: %s", e)
        return False, "No se pudieron ejecutar las pruebas", {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)
    success, message, data = run_suite()
    print(message, data)
    raise SystemExit(0 if success else 1)
