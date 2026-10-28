"""Búsqueda en campos originales con datos ficticios y TOTAL.json, sin Excel."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import run
from carrerags_ingesta.domain import HEADERS, Hit
from reglas import interpretar_pregunta
from relevancia import normalizar_texto, priorizar_carrera

logger = logging.getLogger(__name__)


def check_todos_los_campos() -> tuple[bool, str, dict[str, Any]]:
    try:
        from run_tests import ORIGINAL

        for campo in HEADERS:
            hit = Hit("campo", 0.0, {"original": {**ORIGINAL, campo: "Referencia ÁRBOLES"}})
            ajeno = Hit("ajeno", 0.99, {"original": ORIGINAL})
            ok, mensaje, salida = priorizar_carrera("arboles", [ajeno, hit], [ajeno], 100)
            assert ok and salida == [hit], (campo, mensaje)
        hit = Hit("mixto", 0.0, {"original": {**ORIGINAL, "Descripción": "Programación de aplicaciones",
                                             "Lugar donde se cursa": "Instituto — Quilmes"}})
        ok, mensaje, salida = priorizar_carrera("programacion quilmes", [hit], [], 100)
        assert ok and salida == [hit], mensaje
        ok, mensaje, salida = priorizar_carrera("programacion cordoba", [hit], [hit], 100)
        assert ok and salida == [], mensaje
        ok, mensaje, salida = priorizar_carrera("arbol", [hit], [hit], 100)
        assert ok and salida == [], mensaje
        for pregunta in ["online", "on line", "a distancia"]:
            ok, mensaje, consulta = interpretar_pregunta(pregunta)
            assert ok and consulta["constraints"].modality == "distancia" and consulta["solo_filtros"], mensaje
        return True, "ok", {"campos": len(HEADERS)}
    except Exception as e:
        logger.error("Error en check_todos_los_campos: %s", e)
        return False, "Falló la búsqueda en todos los campos: " + str(e), {}


def check_ubicaciones_y_catalogo() -> tuple[bool, str, dict[str, Any]]:
    try:
        datos = json.loads((Path(__file__).resolve().parents[1] / "TOTAL.json").read_text(encoding="utf-8"))
        catalogo = [Hit(str(i), 0.0, entrada) for i, entrada in enumerate(datos)]
        esperados: set[str] = set()
        for hit in catalogo:
            ok, mensaje, lugar = normalizar_texto(hit.payload["original"]["Lugar donde se cursa"])
            assert ok, mensaje
            if " quilmes " in " " + lugar + " ":
                esperados.add(hit.id)
        assert esperados
        for pregunta in ["¿qué puedo estudiar en Quilmes?", "¿Qué puedo estudiar en Quilmes online?"]:
            ok, mensaje, consulta = interpretar_pregunta(pregunta)
            assert ok and consulta["solo_lugar"], mensaje
            ok, mensaje, salida = priorizar_carrera(consulta["tema"], catalogo, [], 100,
                                                   consulta["solo_filtros"], consulta["solo_lugar"])
            assert ok and {hit.id for hit in salida} == esperados, mensaje
        for pregunta in ["ingeniería en informática en Quilmes", "turismo en Quilmes"]:
            ok, mensaje, consulta = interpretar_pregunta(pregunta)
            assert ok, mensaje
            ok, mensaje, salida = priorizar_carrera(consulta["tema"], catalogo, [], 100)
            assert ok, mensaje
            for hit in salida:
                assert hit.id in esperados
        return True, "ok", {"ofertas_quilmes": len(esperados)}
    except Exception as e:
        logger.error("Error en check_ubicaciones_y_catalogo: %s", e)
        return False, "Falló la búsqueda por ubicación con TOTAL.json: " + str(e), {}


def check_consulta_por_lugar() -> tuple[bool, str, dict[str, Any]]:
    try:
        from run_tests import ORIGINAL, FakeEmbeddings, FakeTransport, escribir_config

        puntos: list[dict[str, Any]] = []
        for i, (titulo, lugar, descripcion) in enumerate([
            ("Ingeniería en Informática", "Instituto — Quilmes", "Desarrollo de software"),
            ("Ingeniería en Informática", "Instituto — Córdoba", "Convenio con Quilmes"),
            ("Abogacía", "Instituto — Quilmes", "Formación jurídica"),
        ]):
            puntos.append({"id": str(i), "payload": {"active": True, "catalog_scope": "all_active_offers",
                "modality": "distancia", "management": "Privada", "admission": "desconocido",
                "original": {**ORIGINAL, "Título": titulo, "Lugar donde se cursa": lugar, "Descripción": descripcion}}})
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            for pregunta, cantidad in [("¿qué puedo estudiar en Quilmes?", 2),
                                       ("ingeniería en informática en Quilmes", 1),
                                       ("¿qué puedo estudiar en Atlantis?", 0),
                                       ("software", 1)]:
                ok, mensaje, _ = escribir_config(base, {"PREGUNTA": pregunta, "LIMITE": 100})
                assert ok, mensaje
                with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings())), \
                     patch.object(run, "HttpTransport", return_value=FakeTransport(paginas=[puntos])):
                    ok, mensaje, salida = run.ejecutar(base)
                assert ok and salida["cantidad"] == cantidad, (pregunta, mensaje, salida)
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_consulta_por_lugar: %s", e)
        return False, "Falló la consulta completa por lugar: " + str(e), {}
