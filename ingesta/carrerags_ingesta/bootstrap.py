"""Arranque del usuario. Las pruebas inyectan valores y nunca leen archivos .env."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Mapping

from .application import process_workbook

logger = logging.getLogger(__name__)
RUNTIME_KEYS = (
    "VECTORIAL", "VECTORIAL_PROVIDER", "VECTORIAL_NAMESPACE", "VECTORIAL_API_KEY",
    "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_REVISION", "EMBEDDING_DIMENSIONS", "EMBEDDING_URL",
    "HTTP_TIMEOUT", "EXCEL", "INGESTA_MODO", "INGESTA_ESTADO",
)


def read_dotenv(component_dir: Path) -> tuple[bool, str, dict[str, str]]:
    try:
        from dotenv import dotenv_values

        # Solo lo ejecuta el usuario. Ruta explícita: sin buscar archivos en otras carpetas.
        loaded = dotenv_values(dotenv_path=component_dir / ".env", encoding="utf-8-sig", interpolate=False)
        return True, "ok", {key: value for key, value in loaded.items() if key in RUNTIME_KEYS and value is not None}
    except ModuleNotFoundError as e:
        logger.error("Error en read_dotenv, dependencia faltante: %s", e)
        return False, "Instalar dependencias con python -m pip install -r reqs.txt", {}
    except Exception as e:
        logger.error("Error en read_dotenv: %s", e)
        return False, "No se pudo cargar la configuración del componente", {}


def load_runtime_values(component_dir: Path, process_values: Mapping[str, str] | None = None) -> tuple[bool, str, dict[str, str]]:
    try:
        ok, message, file_values = read_dotenv(component_dir)
        if not ok:
            return False, message, {}
        process_source = os.environ if process_values is None else process_values
        values: dict[str, str] = {}
        for key in RUNTIME_KEYS:
            if key in process_source:
                values[key] = process_source[key]
        # La configuración explícita del usuario en .env tiene prioridad.
        values.update(file_values)
        return True, "ok", values
    except Exception as e:
        logger.error("Error en load_runtime_values: %s", e)
        return False, "No se pudo preparar la configuración de ejecución", {}


def execute(component_dir: Path, values: Mapping[str, str] | None = None) -> tuple[bool, str, dict[str, Any]]:
    try:
        if values is None:
            ok, message, runtime_values = load_runtime_values(component_dir)
            if not ok:
                return False, message, {}
        else:
            runtime_values = dict(values)
        mode = runtime_values.get("INGESTA_MODO", "publicar").strip().lower()
        if mode not in {"publicar", "analizar"}:
            return False, "INGESTA_MODO debe ser publicar o analizar", {}
        configured_excel = runtime_values.get("EXCEL", "").strip()
        if configured_excel:
            excel = Path(configured_excel)
            if not excel.is_absolute():
                excel = component_dir / excel
        else:
            candidates = [path for path in component_dir.glob("*.xlsx") if not re.search(r"^\.env(?:\.|$)|\.env$", path.name, re.IGNORECASE)]
            if len(candidates) != 1:
                return False, "Definir EXCEL: debe haber exactamente un archivo .xlsx en ingesta para seleccionarlo automáticamente", {}
            excel = candidates[0]
        state = Path(runtime_values.get("INGESTA_ESTADO", ".state").strip() or ".state")
        if not state.is_absolute():
            state = component_dir / state
        return process_workbook(excel=excel, state_dir=state,
                                report_path=component_dir / ".artifacts" / "revision_catalogo.json",
                                publish_catalog=(mode == "publicar"), values=runtime_values)
    except Exception as e:
        logger.error("Error en execute: %s", e)
        return False, "No se pudo iniciar la ingesta", {}
