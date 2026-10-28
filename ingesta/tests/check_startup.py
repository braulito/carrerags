"""Arranque y modelo local simulados: nunca abre configuración ni descarga pesos."""

from __future__ import annotations

import logging
import runpy
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock, patch

from carrerags_ingesta.bootstrap import execute, load_runtime_values, read_dotenv
from carrerags_ingesta.config import DEFAULT_EMBEDDING_REVISION, Settings
from carrerags_ingesta.registry import create_adapter
from support import TestQdrantHTTP, offer_row, workbook

logger = logging.getLogger(__name__)


def check_default_startup() -> tuple[bool, str, dict[str, Any]]:
    try:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "catalog.xlsx"
            assert workbook(path, [offer_row()[2]])[0]
            values = {"INGESTA_MODO": "analizar", "VECTORIAL": "http://archivo.example"}
            with patch("carrerags_ingesta.bootstrap.read_dotenv", side_effect=AssertionError("No abrir configuración")), patch("carrerags_ingesta.application.create_adapter", side_effect=AssertionError("No crear adaptadores")):
                ok, message, data = execute(root, values)
                assert ok and data["report"]["rows"] == 1, message
                assert (root / ".artifacts" / "revision_catalogo.json").is_file()
            with patch("carrerags_ingesta.bootstrap.read_dotenv", return_value=(True, "ok", values)):
                ok, message, merged = load_runtime_values(root, {"VECTORIAL": "http://proceso.example"})
                assert ok and merged["VECTORIAL"] == "http://archivo.example" and merged["INGESTA_MODO"] == "analizar", message
            with patch("carrerags_ingesta.bootstrap.process_workbook", return_value=(True, "ok", {})) as process, patch("carrerags_ingesta.bootstrap.load_runtime_values", return_value=(True, "ok", {"VECTORIAL": "http://vectorial.example"})):
                assert execute(root)[0]
                passed = process.call_args.kwargs
                assert passed["excel"] == path and passed["publish_catalog"] is True
                assert passed["values"]["VECTORIAL"] == "http://vectorial.example"
            assert workbook(root / "other.xlsx", [offer_row()[2]])[0]
            assert not execute(root, values)[0]
            ok, message, data = execute(root, {**values, "EXCEL": "catalog.xlsx"})
            assert ok and data["file"] == "catalog.xlsx", message
            assert not execute(root, {"INGESTA_MODO": "desconocido"})[0]
            # La biblioteca es un doble. No existe ni se abre un archivo de configuración.
            dotenv_module = ModuleType("dotenv")
            parser = MagicMock(return_value={"VECTORIAL": "http://ficticio.example", "IGNORADA": "ficticio"})
            dotenv_module.dotenv_values = parser
            with patch.dict(sys.modules, {"dotenv": dotenv_module}):
                ok, message, loaded = read_dotenv(root)
                assert ok and loaded == {"VECTORIAL": "http://ficticio.example"}, message
                assert parser.call_args.kwargs["interpolate"] is False
                assert parser.call_args.kwargs["dotenv_path"] == root / ".env"
        component = Path(__file__).resolve().parents[1]
        with patch("carrerags_ingesta.bootstrap.execute", return_value=(True, "ok", {})) as launcher, patch("sys.stdout", new_callable=StringIO), TestCase().assertRaises(SystemExit) as ended:
            runpy.run_path(str(component / "run.py"), run_name="__main__")
        assert ended.exception.code == 0
        launcher.assert_called_once_with(component)
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_default_startup: %s", e)
        return False, "Arranque sin argumentos y configuración simulada", {}


def check_local_embeddings() -> tuple[bool, str, dict[str, Any]]:
    try:
        module = ModuleType("sentence_transformers")
        model = MagicMock()
        model.get_sentence_embedding_dimension.return_value = 2
        model.encode.return_value.tolist.return_value = [[0.6, 0.8], [0.8, 0.6]]
        constructor = MagicMock(return_value=model)
        module.SentenceTransformer = constructor
        with patch.dict(sys.modules, {"sentence_transformers": module}):
            ok, message, adapter = create_adapter("embedding", "local", Settings(dimensions=2))
            assert ok and adapter is not None, message
            assert constructor.call_args.kwargs["device"] == "cpu"
            assert constructor.call_args.kwargs["token"] is False
            assert constructor.call_args.kwargs["trust_remote_code"] is False
            assert constructor.call_args.kwargs["revision"] == DEFAULT_EMBEDDING_REVISION
            ok, message, vectors = adapter.embed(["Programación", "Diseño"])
            assert ok and vectors == [[0.6, 0.8], [0.8, 0.6]], message
            assert model.encode.call_args.kwargs["normalize_embeddings"] is True
            assert adapter.embed([]) == (True, "ok", [])
            assert not adapter.embed([""])[0]
            model.encode.return_value.tolist.return_value = [[float("nan"), 0.1]]
            assert not adapter.embed(["Texto"])[0]
            assert not create_adapter("embedding", "local", Settings(dimensions=3))[0]
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            ok, message, adapter = create_adapter("embedding", "local", Settings())
            assert not ok and "pip install" in message and adapter is None
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_local_embeddings: %s", e)
        return False, "Modelo local, validación de vectores y dependencias simuladas", {}


def check_env_configuration_flow() -> tuple[bool, str, dict[str, Any]]:
    try:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            assert workbook(root / "seleccionado.xlsx", [offer_row()[2]])[0]
            assert workbook(root / "otro.xlsx", [offer_row(title="Tecnicatura en Diseño")[2]])[0]
            configured = {
                "VECTORIAL": "http://motor-configurado.example:6333",
                "VECTORIAL_PROVIDER": "carrerags_ingesta.adapters.factories:qdrant",
                "VECTORIAL_NAMESPACE": "catalogo_configurado",
                "VECTORIAL_API_KEY": "clave-del-archivo-ficticia",
                "EXCEL": "seleccionado.xlsx",
                "INGESTA_MODO": "publicar",
                "INGESTA_ESTADO": "estado_configurado",
                "EMBEDDING_PROVIDER": "carrerags_ingesta.adapters.local:create",
                "EMBEDDING_MODEL": "modelo-local-ficticio",
                "EMBEDDING_REVISION": "revision-ficticia",
                "EMBEDDING_DIMENSIONS": "2",
                "HTTP_TIMEOUT": "17",
            }
            dotenv_module = ModuleType("dotenv")
            parser = MagicMock(return_value=configured)
            dotenv_module.dotenv_values = parser
            model_module = ModuleType("sentence_transformers")
            model = MagicMock()
            model.get_sentence_embedding_dimension.return_value = 2
            model.encode.return_value.tolist.return_value = [[0.6, 0.8]]
            constructor = MagicMock(return_value=model)
            model_module.SentenceTransformer = constructor
            process_environment = SimpleNamespace(environ={
                "VECTORIAL": "http://ignorado.example",
                "VECTORIAL_PROVIDER": "memory",
                "VECTORIAL_NAMESPACE": "ignorado",
                "VECTORIAL_API_KEY": "clave-de-proceso-ficticia",
                "EXCEL": "inexistente.xlsx",
                "INGESTA_MODO": "analizar",
                "EMBEDDING_PROVIDER": "no_disponible",
                "HTTP_TIMEOUT": "999",
            })
            server = TestQdrantHTTP()
            with patch.dict(sys.modules, {"dotenv": dotenv_module, "sentence_transformers": model_module}), patch("carrerags_ingesta.bootstrap.os", process_environment), patch("carrerags_ingesta.adapters.factories.HttpTransport", return_value=server) as transport, patch.object(server, "request", wraps=server.request) as request:
                ok, message, result = execute(root)
                assert ok and result["publication"]["collection"] == "catalogo_configurado", message
                assert set(server.collections) == {"catalogo_configurado"}
                assert result["report"]["rows"] == 1 and result["report"]["embedded"] == 1
                assert constructor.call_args.args == ("modelo-local-ficticio",)
                assert constructor.call_args.kwargs["revision"] == "revision-ficticia"
                transport.assert_called_once_with(17.0)
                assert all(call.args[1].startswith(configured["VECTORIAL"] + "/") for call in request.call_args_list)
                assert all(call.args[2]["api-key"] == configured["VECTORIAL_API_KEY"] for call in request.call_args_list)
                saved = root / "estado_configurado" / "catalog.json"
                assert saved.is_file()
                serialized = saved.read_text(encoding="utf-8")
                assert "clave-del-archivo-ficticia" not in serialized
                assert "clave-de-proceso-ficticia" not in serialized
                assert (root / ".artifacts" / "revision_catalogo.json").is_file()
                # Cambiar solamente el modo en la configuración evita tocar modelo y motor.
                configured["INGESTA_MODO"] = "analizar"
                requests_before = request.call_count
                encodings_before = model.encode.call_count
                ok, message, result = execute(root)
                assert ok and result["preview"] is True, message
                assert request.call_count == requests_before and model.encode.call_count == encodings_before
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_env_configuration_flow: %s", e)
        return False, "Aplicación de todas las variables de configuración sin abrir archivos protegidos", {}
