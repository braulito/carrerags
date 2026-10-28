"""Procesamiento del catálogo con parámetros tipados, sin argumentos de consola."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from .catalog import write_json
from .config import read_settings
from .pipeline import analyze, ingest
from .registry import create_adapter

logger = logging.getLogger(__name__)


def process_workbook(excel: Path, state_dir: Path, report_path: Path,
                     publish_catalog: bool, values: Mapping[str, str]) -> tuple[bool, str, dict[str, Any]]:
    try:
        if not publish_catalog:
            ok, message, data = analyze(excel, state_dir)
            if not ok:
                return False, message, data
            ok, message, saved = write_json(report_path, data)
            if not ok:
                return False, message, {}
            summary = {key: value for key, value in data["report"].items() if key not in {"exclusions", "change_ids"}}
            return True, "ok", {"preview": True, "file": data["file"], "report": summary,
                                 "report_path": saved}
        ok, message, settings = read_settings(values)
        if not ok or settings is None:
            return False, message, {}
        ok, message, _ = analyze(excel, state_dir)
        if not ok:
            return False, message, {}
        ok, message, store = create_adapter("vector", settings.vector_provider, settings)
        if not ok:
            return False, message, {}
        if settings.vector_provider == "memory":
            return False, "El motor de memoria no persiste entre ejecuciones; usarlo desde Python o las pruebas", {}
        ok, message, embedder = create_adapter("embedding", settings.embedding_provider, settings)
        if not ok:
            return False, message, {}
        ok, message, data = ingest(excel, state_dir, embedder, store)
        if not ok:
            return False, message, data
        ok, message, _ = write_json(report_path, {"report": data["report"], "publication": data["publication"]})
        if not ok:
            return False, "Catálogo publicado; no se pudo escribir el reporte solicitado", {}
        data["report"] = {key: value for key, value in data["report"].items() if key not in {"exclusions", "change_ids"}}
        return True, "ok", data
    except Exception as e:
        logger.error("Error en process_workbook: %s", e)
        return False, "No se pudo procesar el catálogo", {}
