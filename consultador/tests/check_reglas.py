"""Reglas y filtros de consulta con modelo, transporte y datos ficticios."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import run
from reglas import interpretar_pregunta

logger = logging.getLogger(__name__)


def check_interpretacion() -> tuple[bool, str, dict[str, Any]]:
    try:
        casos = [
            ("Dónde puedo estudiar profesorado", "profesorado", None, None, False, False),
            ("Dónde puedo estudiar profesorados online", "profesorado", None, "distancia", False, False),
            ("profesorados públicos y online", "profesorado", "Pública", "distancia", False, False),
            ("profesorados online y públicos", "profesorado", "Pública", "distancia", False, False),
            ("profesorado en una universidad privada", "profesorado", "Privada", None, False, False),
            ("profesorado semipresencial", "profesorado", None, "semipresencial", False, False),
            ("profesorado híbrido", "profesorado", None, "hibrida", False, False),
            ("profesorado presencial", "profesorado", None, "presencial", False, False),
            ("profesorado sin título previo", "profesorado", None, None, True, False),
            ("profesorado, tengo solo secundario", "profesorado", None, None, True, False),
            ("Tengo solo secundario, dónde puedo estudiar profesorado", "profesorado", None, None, True, False),
            ("profesorado sin viajar", "profesorado", None, None, False, True),
            ("profesorado no puedo viajar", "profesorado", None, None, False, True),
            ("públicas y online", "", "Pública", "distancia", False, False),
            ("online y públicas", "", "Pública", "distancia", False, False),
            ("Dónde puedo estudiar online", "", None, "distancia", False, False),
            ("Licenciatura en Administración Pública", "licenciatura en administracion publica", None, None, False, False),
            ("Contador Público", "contador publico", None, None, False, False),
        ]
        for pregunta, tema, gestion, modalidad, secundario, viajes in casos:
            ok, mensaje, datos = interpretar_pregunta(pregunta)
            assert ok, (pregunta, mensaje)
            constraints = datos["constraints"]
            assert datos["tema"] == tema, (pregunta, datos["tema"])
            assert constraints.management == gestion and constraints.modality == modalidad, pregunta
            assert constraints.secondary_only is secundario and constraints.no_travel is viajes, pregunta
            assert datos["solo_filtros"] is (not tema), pregunta
        for pregunta in ["profesorado online presencial", "profesorado sin viajar semipresencial",
                         "profesorado no online", "profesorado en universidad pública y en universidad privada", ""]:
            ok, mensaje, datos = interpretar_pregunta(pregunta)
            assert not ok and datos == {} and mensaje != "ok", pregunta
        return True, "ok", {"casos": len(casos)}
    except Exception as e:
        logger.error("Error en check_interpretacion: %s", e)
        return False, "Falló la interpretación por reglas: " + str(e), {}


def check_filtros_en_consulta() -> tuple[bool, str, dict[str, Any]]:
    try:
        from run_tests import FakeEmbeddings, FakeTransport, ORIGINAL, escribir_config

        puntos: list[dict[str, Any]] = []
        combinaciones = [
            ("distancia", "Pública", "desconocido", True, "desconocido", "desconocido"),
            ("distancia", "Privada", "titulo_superior_previo", True, "remoto", "remoto"),
            ("hibrida", "Pública", "desconocido", True, "remoto", "remoto"),
            ("semipresencial", "Privada", "desconocido", True, "presencial", "presencial"),
            ("presencial", "Pública", "restringido", True, "presencial", "presencial"),
            ("distancia", "Pública", "desconocido", False, "remoto", "remoto"),
            ("distancia", "Pública", "desconocido", True, "remoto", "no_aplica"),
        ]
        for numero, (modalidad, gestion, ingreso, independiente, examenes, practicas) in enumerate(combinaciones):
            puntos.append({"id": str(numero), "score": 0.9, "payload": {
                "active": True, "eligible": False, "catalog_scope": "all_active_offers",
                "modality": modalidad, "management": gestion, "admission": ingreso,
                "independent_entry": independiente, "exams": examenes, "practices": practicas,
                "original": {**ORIGINAL, "Título": "Profesorado de prueba " + str(numero),
                             "Pública/Privada": gestion}}})
        casos = [
            ("Dónde puedo estudiar profesorado", {"0", "1", "2", "3", "4", "5", "6"}),
            ("profesorados online", {"0", "1", "5", "6"}),
            ("profesorados públicos y online", {"0", "5", "6"}),
            ("profesorados online y públicos", {"0", "5", "6"}),
            ("profesorado sin título previo", {"0", "2", "3", "6"}),
            ("profesorados públicos online sin título previo", {"0", "6"}),
            ("profesorado sin viajar", {"1", "5", "6"}),
            ("profesorado semipresencial", {"3"}),
            ("profesorado presencial", {"4"}),
            ("públicas y online", {"0", "5", "6"}),
            ("Dónde puedo estudiar medicina", set()),
        ]
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            for pregunta, esperados in casos:
                ok, mensaje, _ = escribir_config(base_dir, {"PREGUNTA": pregunta, "LIMITE": 100})
                assert ok, mensaje
                transporte = FakeTransport(paginas=[puntos[:3], puntos[3:]])
                with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings())), \
                     patch.object(run, "HttpTransport", return_value=transporte):
                    ok, mensaje, salida = run.ejecutar(base_dir)
                assert ok and salida["cantidad"] == len(esperados), (pregunta, mensaje, salida)
                respuesta = json.loads((base_dir / "respuesta.json").read_text(encoding="utf-8"))
                assert {r["original"]["Título"].split()[-1] for r in respuesta} == esperados, pregunta
                vector_filter = transporte.calls[1]["body"]["filter"]
                assert all(c["key"] != "eligible" for c in vector_filter["must"])
                assert all(c["body"]["filter"] == vector_filter for c in transporte.calls[2:])
        return True, "ok", {"casos": len(casos)}
    except Exception as e:
        logger.error("Error en check_filtros_en_consulta: %s", e)
        return False, "Falló la aplicación de filtros en la consulta: " + str(e), {}


def check_reindexacion() -> tuple[bool, str, dict[str, Any]]:
    try:
        from reindexar import actualizar_catalogo
        from run_tests import escribir_config

        with tempfile.TemporaryDirectory() as carpeta:
            raiz = Path(carpeta)
            base_dir = raiz / "consultador"
            base_dir.mkdir()
            ingesta = raiz / "ingesta"
            ingesta.mkdir()
            excel = ingesta / "catalogo.xlsx"
            excel.write_bytes(b"libro ficticio: el procesamiento se simula")
            ok, mensaje, _ = escribir_config(base_dir, {})
            assert ok, mensaje
            with patch("reindexar.process_workbook", return_value=(True, "ok", {"publication": {"points": 574}})) as procesar:
                ok, mensaje, salida = actualizar_catalogo(base_dir)
            assert ok and salida["publication"]["points"] == 574, mensaje
            argumentos = procesar.call_args.kwargs
            assert argumentos["excel"] == excel and argumentos["publish_catalog"] is True
            assert argumentos["state_dir"] == ingesta / ".state"
            assert argumentos["values"]["VECTORIAL"] == "http://example.invalid:6333"
            assert "LIMITE" not in argumentos["values"]
            (ingesta / "otro.xlsx").write_bytes(b"otro libro ficticio")
            with patch("reindexar.process_workbook") as procesar:
                ok, mensaje, salida = actualizar_catalogo(base_dir)
                assert not ok and salida == {} and mensaje != "ok"
                procesar.assert_not_called()
        return True, "ok", {}
    except Exception as e:
        logger.error("Error en check_reindexacion: %s", e)
        return False, "Falló la reindexación con configuración JSON: " + str(e), {}


def check_profesorados_json() -> tuple[bool, str, dict[str, Any]]:
    try:
        from dataclasses import asdict
        from carrerags_ingesta.domain import HEADERS, normalize_offer
        from run_tests import FakeEmbeddings, FakeTransport, escribir_config

        entradas = json.loads((Path(__file__).resolve().parents[1] / "TOTAL.json").read_text(encoding="utf-8"))
        puntos: list[dict[str, Any]] = []
        for entrada in entradas:
            ok, mensaje, oferta = normalize_offer([entrada["original"][campo] for campo in HEADERS], {})
            assert ok and oferta is not None, mensaje
            puntos.append({"id": oferta.id, "payload": {**asdict(oferta), "active": True,
                           "catalog_scope": "all_active_offers"}})
        cantidades: dict[str, int] = {}
        with tempfile.TemporaryDirectory() as carpeta:
            base_dir = Path(carpeta)
            for pregunta, esperado in [("Dónde puedo estudiar profesorado", 51),
                                        ("profesorados online", None),
                                        ("profesorados online sin título previo", 6)]:
                ok, mensaje, _ = escribir_config(base_dir, {"PREGUNTA": pregunta, "LIMITE": 100})
                assert ok, mensaje
                transporte = FakeTransport(paginas=[puntos[:400], puntos[400:]])
                with patch.object(run, "create_embeddings", return_value=(True, "ok", FakeEmbeddings())), \
                     patch.object(run, "HttpTransport", return_value=transporte):
                    ok, mensaje, salida = run.ejecutar(base_dir)
                assert ok, mensaje
                cantidades[pregunta] = salida["cantidad"]
                assert (salida["cantidad"] == esperado if esperado is not None else 5 < salida["cantidad"] < 50), salida
                if esperado == 51:
                    respuesta = json.loads((base_dir / "respuesta.json").read_text(encoding="utf-8"))
                    assert len({r["original"]["Título"] for r in respuesta}) == 39
        return True, "ok", cantidades
    except Exception as e:
        logger.error("Error en check_profesorados_json: %s", e)
        return False, "Falló la consulta de TOTAL.json con filtros simulados: " + str(e), {}
