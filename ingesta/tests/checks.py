"""Pruebas de comportamiento y compatibilidad usando solamente la biblioteca estándar."""

from __future__ import annotations

import ast
import copy
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from carrerags_ingesta.adapters.http import HttpTransport
from carrerags_ingesta.adapters.memory import MemoryStore
from carrerags_ingesta.adapters.qdrant import QdrantStore
from carrerags_ingesta.catalog import prepare_catalog, read_catalog, write_json
from carrerags_ingesta.config import Settings, read_settings
from carrerags_ingesta.domain import Constraints, Point, normalize_offer
from carrerags_ingesta.excel import read_workbook, safe_path
from carrerags_ingesta.pipeline import analyze, ingest
from carrerags_ingesta.registry import create_adapter
from carrerags_ingesta.service import build_points
from support import TestEmbeddings, TestQdrantHTTP, offer_row, workbook

logger = logging.getLogger(__name__)


def check_excel() -> tuple[bool, str, dict[str, Any]]:
    try:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ok, message, row = offer_row(title="Tecnicatura en Diseño & Programación")
            assert ok, message
            for shared in (True, False):
                ok, message, path = workbook(root / "synthetic.xlsx", [row], reviewed=[row], shared=shared)
                assert ok and path is not None, message
                ok, message, content = read_workbook(path)
                assert ok and content["rows"][0]["cells"] == row and content["reviewed"] == [row], message
            broken = row.copy()
            broken[3] = ""
            assert workbook(root / "broken.xlsx", [broken])[0]
            assert not prepare_catalog(root / "broken.xlsx", {"offers": {}})[0]
            assert workbook(root / "formula.xlsx", [row], formula=True)[0]
            assert not read_workbook(root / "formula.xlsx")[0]
            assert workbook(root / "empty.xlsx", [])[0]
            assert not read_workbook(root / "empty.xlsx")[0]
            assert not safe_path(root / ".env" / "catalog.json", ".json")[0]
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_excel: %s", e)
        return False, "Lectura y validación de Excel", {}


def check_eligibility() -> tuple[bool, str, dict[str, Any]]:
    try:
        cases = [
            ("A distancia", "Pregrado", "Programación.", True),
            ("Online (sincrónica/asincrónica/mixta)", "Pregrado", "Programación.", True),
            ("A distancia; la universidad también ofrece opción semipresencial.", "Grado", "Programación.", True),
            ("Semipresencial", "Grado", "Programación.", False),
            ("Híbrida: virtual y presencial", "Grado", "Programación.", False),
            ("Mixta: online, con 4.º año presencial", "Grado", "Programación.", False),
            ("A distancia", "Grado (CCC)", "Programación.", False),
            ("A distancia", "Pregrado", "Acceso restringido a empleados públicos.", False),
        ]
        for mode, level, description, eligible in cases:
            ok, message, row = offer_row(mode=mode, level=level, description=description)
            assert ok, message
            ok, message, offer = normalize_offer(row, {"row": 2, "review_group": "heredado"})
            assert ok and offer is not None and offer.eligible is eligible, (mode, message)
        ok, message, row = offer_row(mode="A distancia; finales presenciales; prácticas por confirmar")
        assert ok, message
        ok, message, offer = normalize_offer(row, {})
        assert ok and offer is not None and offer.exams == "presencial" and offer.practices == "desconocido", message
        ok, message, row = offer_row(mode="100% online (final remoto o sede cercana)")
        assert ok, message
        ok, message, offer = normalize_offer(row, {})
        assert ok and offer is not None and offer.exams == "desconocido" and offer.practices == "desconocido", message
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_eligibility: %s", e)
        return False, "Elegibilidad y distinción de presencialidad", {}


def check_updates_and_cache() -> tuple[bool, str, dict[str, Any]]:
    try:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.xlsx"
            first = offer_row()[2]
            second = offer_row(title="Tecnicatura en Diseño")[2]
            assert workbook(path, [first, second], reviewed=[first])[0]
            ok, message, initial = prepare_catalog(path, {"offers": {}})
            assert ok and initial["report"]["rows"] == 2, message
            embedder = TestEmbeddings()
            assert build_points(initial, embedder)[0]
            assert embedder.count == 2
            assert workbook(path, [second, first], reviewed=[first])[0]
            ok, message, reordered = prepare_catalog(path, initial)
            assert ok and reordered["report"]["changes"]["unchanged"] == 2, message
            assert build_points(reordered, embedder)[0] and embedder.count == 2
            first[4] = "A distancia con exámenes finales presenciales"
            assert workbook(path, [first, second], reviewed=[first])[0]
            ok, message, metadata = prepare_catalog(path, reordered)
            assert ok and metadata["report"]["changes"]["modified"] == 1, message
            assert build_points(metadata, embedder)[0] and embedder.count == 2
            first[3] = "Programación, algoritmos y bases de datos."
            assert workbook(path, [first], reviewed=[first])[0]
            ok, message, changed = prepare_catalog(path, metadata)
            assert ok and changed["report"]["changes"]["retired"] == 1, message
            assert sum(entry["active"] for entry in changed["offers"].values()) == 1
            assert build_points(changed, embedder)[0] and embedder.count == 3
            replacement = TestEmbeddings(space="test:v2:2")
            assert build_points(changed, replacement)[0] and replacement.count == 1
            assert workbook(path, [first, first])[0]
            assert not prepare_catalog(path, initial)[0]
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_updates_and_cache: %s", e)
        return False, "Identidad estable, cambios, bajas y caché de vectores", {}


def check_memory_contract() -> tuple[bool, str, dict[str, Any]]:
    try:
        common = {"active": True, "eligible": True, "modality": "distancia", "admission": "desconocido"}
        points = [Point("private", [1.0, 0.0], {**common, "management": "Privada", "exams": "remoto", "practices": "remoto"}),
                  Point("public", [0.5, 0.5], {**common, "management": "Pública", "exams": "remoto", "practices": "remoto"}),
                  Point("uncertain", [1.0, 0.0], {**common, "management": "Pública", "exams": "desconocido", "practices": "desconocido"})]
        store = MemoryStore()
        assert store.health()[0] and store.replace(points, "test:v1:2", 2)[0]
        ok, message, hits = store.search([1.0, 0.0], Constraints("Pública", True), 1, "test:v1:2")
        assert ok and [hit.id for hit in hits] == ["public"], message
        assert store.fetch(["public"])[2][0]["management"] == "Pública"
        assert not store.search([1.0, 0.0], Constraints(), 1, "other")[0]
        assert not store.replace([Point("invalid", [float("nan"), 1.0], {})], "test:v1:2", 2)[0]
        assert store.fetch(["public"])[2]
        assert store.replace([points[0]], "test:v1:2", 2)[0]
        assert not store.fetch(["public"])[2]
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_memory_contract: %s", e)
        return False, "Contrato de recuperación y filtros antes del límite", {}


def check_qdrant_contract() -> tuple[bool, str, dict[str, Any]]:
    try:
        payload = {"active": True, "eligible": True, "modality": "distancia", "management": "Pública",
                   "admission": "desconocido", "exams": "remoto", "practices": "remoto"}
        point = Point("c9da604c-40fb-4fb2-ac91-569da8bccf82", [1.0, 0.5], payload)
        previous = "carrerags_g_" + "a" * 32
        older = "carrerags_g_" + "b" * 32
        initial = {previous: {"points": {}}, older: {"points": {}},
                   "otro_catalogo": {"points": {}}, "carrerags_g_manual": {"points": {}}}
        transport = TestQdrantHTTP(collections=copy.deepcopy(initial), aliases={"carrerags": previous})
        store = QdrantStore("http://vectorial.example:6333", transport=transport)
        ok, message, data = store.replace([point], "test:v1:2", 2)
        assert ok and data["collection"] == "carrerags", message
        assert set(transport.collections) == {"carrerags", "otro_catalogo", "carrerags_g_manual"}
        assert transport.aliases == {}
        assert set(data["removed_collections"]) == {previous, older}
        assert transport.collections["carrerags"]["points"][point.id]["payload"]["active"] is True
        assert not any("create_alias" in action for request in transport.requests
                       for action in (request.get("body") or {}).get("actions", []))
        assert not any(request["method"] == "PUT" and "/collections/carrerags_g_" in request["url"] for request in transport.requests)
        # Una segunda ejecución reemplaza los datos, sin añadir otra colección.
        assert store.replace([], "test:v1:2", 2)[0]
        assert set(transport.collections) == {"carrerags", "otro_catalogo", "carrerags_g_manual"}
        assert not transport.collections["carrerags"]["points"]
        assert store.replace([point], "test:v1:2", 2)[0]
        failed = TestQdrantHTTP(fail_on="/points?wait=true",
                                collections=copy.deepcopy(initial), aliases={"carrerags": previous})
        ok, message, data = QdrantStore("http://vectorial.example:6333", transport=failed).replace([point], "test:v1:2", 2)
        assert not ok and data["publication_state"] == "incomplete", message
        assert previous not in failed.collections and older not in failed.collections
        assert set(failed.collections) == {"carrerags", "otro_catalogo", "carrerags_g_manual"}
        assert failed.aliases == {}
        wrong_count = TestQdrantHTTP(wrong_count=True)
        assert not QdrantStore("http://vectorial.example:6333", transport=wrong_count).replace([point], "test:v1:2", 2)[0]
        assert wrong_count.collections["carrerags"]["points"][point.id]["payload"]["active"] is False
        activation = TestQdrantHTTP(fail_on="/points/payload?wait=true")
        activation_store = QdrantStore("http://vectorial.example:6333", transport=activation)
        ok, message, data = activation_store.replace([point], "test:v1:2", 2)
        assert not ok and data["publication_state"] == "unknown", message
        assert set(activation.collections) == {"carrerags"}
        assert activation.collections["carrerags"]["points"][point.id]["payload"]["active"] is False
        activation.fail_on = ""
        assert activation_store.replace([point], "test:v1:2", 2)[0]
        assert set(activation.collections) == {"carrerags"}
        # No borrar nada si los vectores son inválidos o el alias apunta fuera del catálogo.
        before = TestQdrantHTTP(collections=copy.deepcopy(initial), aliases={"carrerags": previous})
        assert not QdrantStore("http://vectorial.example:6333", transport=before).replace([Point(point.id, [0.0, 0.0], payload)], "test:v1:2", 2)[0]
        assert before.requests == [] and before.collections == initial
        foreign = TestQdrantHTTP(collections=copy.deepcopy(initial), aliases={"carrerags": "otro_catalogo"})
        assert not QdrantStore("http://vectorial.example:6333", transport=foreign).replace([point], "test:v1:2", 2)[0]
        assert foreign.collections == initial
        assert not any(request["method"] == "DELETE" for request in foreign.requests)
        deletion = TestQdrantHTTP(fail_on=previous, fail_method="DELETE",
                                  collections=copy.deepcopy(initial), aliases={"carrerags": previous})
        assert not QdrantStore("http://vectorial.example:6333", transport=deletion).replace([point], "test:v1:2", 2)[0]
        assert previous in deletion.collections and "carrerags" not in deletion.collections
        transport.query_points = [{"id": point.id, "score": 0.9, "payload": payload}]
        ok, message, hits = store.search([1.0, 0.5], Constraints("Pública", True), 1, "test:v1:2")
        assert ok and len(hits) == 1, message
        body = transport.requests[-1]["body"]
        assert body["limit"] == 1 and len(body["filter"]["must"]) == 5
        assert not store.search([1.0, 0.5], Constraints(), 1, "test:changed:2")[0]
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_qdrant_contract: %s", e)
        return False, "Colección única, eliminación de versiones, filtros y fallos simulados", {}


def check_pipeline_failure() -> tuple[bool, str, dict[str, Any]]:
    try:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "input.xlsx"
            state = root / "state"
            row = offer_row()[2]
            assert workbook(path, [row])[0]
            assert ingest(path, state, TestEmbeddings(), MemoryStore())[0]
            previous = (state / "catalog.json").read_bytes()
            row[3] = "Una descripción nueva."
            assert workbook(path, [row])[0]
            failing = QdrantStore("http://vectorial.example:6333", transport=TestQdrantHTTP(fail_on="/points?wait=true"))
            assert not ingest(path, state, TestEmbeddings(), failing)[0]
            assert (state / "catalog.json").read_bytes() == previous
            assert not (state / "ingest.lock").exists()
            (state / "ingest.lock").write_text("simulado", encoding="utf-8")
            assert not ingest(path, state, TestEmbeddings(), MemoryStore())[0]
            assert (state / "ingest.lock").exists()
            (state / "ingest.lock").unlink()
            assert workbook(path, [])[0]
            assert not ingest(path, state, TestEmbeddings(), MemoryStore())[0]
            assert (state / "catalog.json").read_bytes() == previous
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_pipeline_failure: %s", e)
        return False, "Fallos de carga, bloqueo y protección ante Excel vacío", {}


def check_processing_offline() -> tuple[bool, str, dict[str, Any]]:
    try:
        from carrerags_ingesta.application import process_workbook

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "input.xlsx"
            assert workbook(path, [offer_row()[2]])[0]
            with patch("carrerags_ingesta.application.read_settings", side_effect=AssertionError("No debe convertir configuración")), patch("carrerags_ingesta.application.create_adapter", side_effect=AssertionError("No debe crear adaptadores")):
                assert process_workbook(path, root / "state", root / "report.json", False, {})[0]
            with patch("carrerags_ingesta.application.read_settings", return_value=(True, "ok", Settings(vectorial="http://vectorial.example", embedding_provider=""))), patch("carrerags_ingesta.application.ingest") as publication:
                ok, message, data = process_workbook(path, root / "state", root / "report.json", True, {})
                assert not ok and "EMBEDDING_PROVIDER" in message
                publication.assert_not_called()
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_processing_offline: %s", e)
        return False, "Preparación sin configuración y validación del módulo de embeddings", {}


def check_http_transport() -> tuple[bool, str, dict[str, Any]]:
    try:
        with patch("carrerags_ingesta.adapters.http.HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 403
            ok, message, data = HttpTransport().request("POST", "http://vectorial.example/test", {"api-key": "clave-ficticia"}, {})
            assert not ok and data["http_status"] == 403 and "403" in message
            response.read.assert_not_called()
            response.status = 200
            response.read.return_value = json.dumps({"status": "ok", "result": True}).encode()
            ok, message, data = HttpTransport().request("GET", "http://vectorial.example/test", {})
            assert ok and data["body"]["result"] is True, message
            response.status = 302
            assert not HttpTransport().request("GET", "http://vectorial.example/test", {})[0]
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_http_transport: %s", e)
        return False, "Estados HTTP y rechazo de redirecciones", {}


def check_configuration_and_extension() -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, message, settings = read_settings({"VECTORIAL": "vectorial.example:6333", "VECTORIAL_API_KEY": "clave-ficticia"})
        assert ok and settings is not None and settings.vectorial == "http://vectorial.example:6333", message
        assert "clave-ficticia" not in repr(settings)
        assert create_adapter("vector", "memory", settings)[0]
        assert create_adapter("vector", "carrerags_ingesta.adapters.factories:memory", settings)[0]
        assert not create_adapter("vector", "desconocido", settings)[0]
        assert not read_settings({"EMBEDDING_DIMENSIONS": "no-numérico"})[0]
        assert not read_settings({"VECTORIAL": "http://usuario:clave-ficticia@vectorial.example"})[0]
        assert not create_adapter("embedding", "", Settings())[0]
        assert settings.embedding_provider == "local" and settings.dimensions is None
        ok, message, external = create_adapter("embedding", "support:create_test_embeddings", settings)
        assert ok and external is not None and external.dimensions == 2, message
        assert external.embed(["Texto ficticio"])[0]
        assert not create_adapter("embedding", "support:create_test_embeddings", Settings(dimensions=3))[0]
        assert not create_adapter("conversation", "no-disponible", settings)[0]
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_configuration_and_extension: %s", e)
        return False, "Configuración por VECTORIAL y extensión sin modificar el núcleo", {}


def check_actual_catalog() -> tuple[bool, str, dict[str, Any]]:
    try:
        root = Path(__file__).resolve().parents[1]
        path = root / "carreras_a_distancia_argentina_2026_profesorados_artes.xlsx"
        with TemporaryDirectory() as temporary:
            ok, message, data = analyze(path, Path(temporary))
            assert ok and data["report"]["rows"] == 574, message
            assert data["report"]["review_groups"] == {"heredado": 527, "alta_revision": 47}
            ok, message, catalog = prepare_catalog(path, {"offers": {}})
            assert ok, message
            tagu = [entry["offer"] for entry in catalog["offers"].values() if "(TAGU)" in entry["offer"]["title"]]
            assert tagu and not tagu[0]["eligible"]
            assert all(not entry["offer"]["eligible"] for entry in catalog["offers"].values() if entry["offer"]["level"] == "Grado (CCC)")
            assert all(entry["offer"]["source"]["verified_at"] is None for entry in catalog["offers"].values())
            ok, message, points = build_points(catalog, TestEmbeddings())
            assert ok and len(points) == 574 and catalog["report"]["indexed"] == 574, message
            assert all(point.payload["catalog_scope"] == "all_active_offers" for point in points)
            profesorados = [point for point in points if "profesorado" in point.payload["title"].casefold()]
            assert len(profesorados) == 50
            assert any(not point.payload["eligible"] for point in profesorados)
            assert any(point.payload["admission"] == "titulo_superior_previo" for point in profesorados)
            assert any(point.payload["modality"] == "semipresencial" for point in profesorados)
            assert any(point.payload["modality"] == "hibrida" for point in profesorados)
            return True, "ok", {"rows": 574, "eligible": data["report"]["eligible"], "excluded": data["report"]["excluded"]}
    except Exception as e:
        logger.error("Error en check_actual_catalog: %s", e)
        return False, "Validación del Excel real sin acceso a configuración o fuentes externas", {}


def check_function_contracts() -> tuple[bool, str, dict[str, Any]]:
    try:
        root = Path(__file__).resolve().parents[1] / "carrerags_ingesta"
        for path in [*root.glob("*.py"), *(root / "adapters").glob("*.py")]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.returns is not None and ast.unparse(node.returns).startswith("tuple[bool, str,"), (path.name, node.name)
                    assert all(arg.annotation is not None for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]), (path.name, node.name)
                    protocol = len(node.body) == 1 and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and node.body[0].value.value is Ellipsis
                    assert protocol or any(isinstance(statement, ast.Try) for statement in node.body), (path.name, node.name)
                if isinstance(node, ast.ExceptHandler):
                    assert node.name == "e", (path.name, "Excepción sin capturar como e")
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_function_contracts: %s", e)
        return False, "Contrato de funciones tipadas y manejo de excepciones", {}
